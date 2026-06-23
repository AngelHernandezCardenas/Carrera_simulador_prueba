import cv2
import numpy as np
import time

# ─── Rangos HSV (H: 0-179, S: 0-255, V: 0-255) ───────────────────────────────
RANGO_ROJO_1 = (np.array([  0, 150,  80]), np.array([  8, 255, 255]))
RANGO_ROJO_2 = (np.array([172, 150,  80]), np.array([180, 255, 255]))
RANGO_BLANCO = (np.array([  0,   0, 200]), np.array([180,  40, 255]))
RANGO_NEGRO  = (np.array([  0,   0,   0]), np.array([180, 255,  50]))


RATIO_COB_MIN = 0.25
FRAC_AREA_MIN = 0.005

KERNEL_OPEN  = np.ones((5, 5), np.uint8)
KERNEL_CLOSE = np.ones((7, 7), np.uint8)
KERNEL_ERODE = np.ones((3, 3), np.uint8)

# ─── Cache de kernels para el optimizador GP ──────────────────────────────────
_kernel_cache = {}

def _get_kernel(size):
    if size not in _kernel_cache:
        _kernel_cache[size] = np.ones((size, size), np.uint8)
    return _kernel_cache[size]


# ─── TrackerColor ─────────────────────────────────────────────────────────────
class TrackerColor:
    """Estabiliza el bounding-box con EMA adaptativo y zona muerta."""
    def __init__(self, alpha_min=0.30, alpha_max=0.75, umbral_px=8, dist_max_px=80, frames_conf=2, frames_perdida=4):
        self.alpha_min      = alpha_min
        self.alpha_max      = alpha_max
        self.umbral_px      = umbral_px
        self.dist_max_px    = dist_max_px
        self.frames_conf    = frames_conf
        self.frames_perdida = frames_perdida
        self.reiniciar()

    def reiniciar(self):
        self.bbox_suave  = None
        self.conteo_det  = 0
        self.conteo_perd = 0
        self.visible     = False

    def actualizar(self, bbox_raw, frame_shape):
        h_f, w_f = frame_shape[:2]
        escala   = max(h_f, w_f) / 640.0
        umbral   = self.umbral_px   * escala
        dist_max = self.dist_max_px * escala

        if bbox_raw is None:
            self.conteo_det  = 0
            self.conteo_perd = min(self.conteo_perd + 1, self.frames_perdida + 1)
            if self.conteo_perd >= self.frames_perdida:
                self.visible    = False
                self.bbox_suave = None
            return self._int() if self.visible else None

        self.conteo_perd = 0
        self.conteo_det  = min(self.conteo_det + 1, self.frames_conf + 10)
        if self.conteo_det < self.frames_conf:
            return None
        if self.bbox_suave is None:
            self.bbox_suave = [float(v) for v in bbox_raw]
            self.visible    = True
            return self._int()

        self.visible = True
        cx_r = bbox_raw[0] + bbox_raw[2] / 2.0
        cy_r = bbox_raw[1] + bbox_raw[3] / 2.0
        cx_s = self.bbox_suave[0] + self.bbox_suave[2] / 2.0
        cy_s = self.bbox_suave[1] + self.bbox_suave[3] / 2.0
        dist = ((cx_r - cx_s)**2 + (cy_r - cy_s)**2)**0.5

        if dist < umbral:
            a = self.alpha_min * 0.4
            self.bbox_suave[2] = a * bbox_raw[2] + (1-a) * self.bbox_suave[2]
            self.bbox_suave[3] = a * bbox_raw[3] + (1-a) * self.bbox_suave[3]
        else:
            t     = min(1.0, dist / dist_max)
            alpha = self.alpha_min + t * (self.alpha_max - self.alpha_min)
            for i in range(4):
                self.bbox_suave[i] = alpha * bbox_raw[i] + (1-alpha) * self.bbox_suave[i]

        return self._int()

    def _int(self):
        if self.bbox_suave is None: return None
        return tuple(int(round(v)) for v in self.bbox_suave)

def calcular_orientacion(w, h):
    if h == 0 or w == 0: return 'Desconocido', 1.0
    ratio = h / w
    if   ratio > 1.3:  return 'Vertical',   ratio
    elif ratio < 0.77: return 'Horizontal',  ratio
    else:              return 'Cuadrado',    ratio

def calcular_huella_hsv(frame_hsv, mascara, bbox):
    """
    Histograma 2D H x S sobre los píxeles enmascarados del bbox.
    Captura tono + saturación = 'firma' del color del objeto.
    Retorna histograma normalizado, o None si hay pocos píxeles.
    """
    x, y, w, h  = bbox
    roi_hsv     = frame_hsv[y:y+h, x:x+w]
    roi_mask    = mascara[y:y+h, x:x+w]
    if cv2.countNonZero(roi_mask) < 50:
        return None
    hist = cv2.calcHist(
        [roi_hsv], [0, 1], roi_mask,
        [30, 32], [0, 180, 0, 256]
    )
    cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
    return hist

def es_mismo_objeto(huella_nueva, huellas_guardadas, umbral=0.82):
    """True si la huella_nueva supera el umbral de similitud con alguna guardada."""
    if huella_nueva is None or not huellas_guardadas:
        return False
    for ref in huellas_guardadas:
        if cv2.compareHist(huella_nueva, ref, cv2.HISTCMP_CORREL) >= umbral:
            return True
    return False

def estimar_z(area_px, frame_shape):
    frac = area_px / (frame_shape[0] * frame_shape[1])
    return round(max(0.1, min(5.0, 1.0 / (frac * 10 + 0.01))), 2)

def procesar_frame_vision_servidor(frame, estado, gp_params=None):
    """
    Detecta Rojo/Blanco/Negro devolviendo el objeto detectado.
    Dibuja la malla de calibración, contornos y etiquetas sobre el frame.
    
    gp_params: dict opcional del optimizador GP con:
        blur_k, morph_open_k, morph_close_k, area_min_frac
    """
    trackers = estado['trackers']
    huellas = estado['huellas']
    counts = estado['counts']
    ultimo_intento = estado['ultimo_intento']
    temporizadores = estado.setdefault('temporizadores', {})

    # ── Parámetros dinámicos del GP (o defaults) ──────────────────────────────
    if gp_params:
        blur_k      = gp_params.get('blur_k', 5)
        open_k      = gp_params.get('morph_open_k', 5)
        close_k     = gp_params.get('morph_close_k', 7)
        frac_min    = gp_params.get('area_min_frac', FRAC_AREA_MIN)
    else:
        blur_k, open_k, close_k, frac_min = 5, 5, 7, FRAC_AREA_MIN

    k_open  = _get_kernel(open_k)
    k_close = _get_kernel(close_k)

    blurred = cv2.GaussianBlur(frame, (blur_k, blur_k), 0)
    hsv     = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
    t_act   = time.time()
    
    area_min = max(800, int(frame.shape[0] * frame.shape[1] * frac_min))

    m_rojo   = cv2.add(cv2.inRange(hsv, *RANGO_ROJO_1), cv2.inRange(hsv, *RANGO_ROJO_2))
    m_blanco = cv2.inRange(hsv, *RANGO_BLANCO)
    m_negro  = cv2.inRange(hsv, *RANGO_NEGRO)

    colores = [
        ('Rojo',   m_rojo,   (0,   0, 255)),
        ('Blanco', m_blanco, (255, 255, 255)),
        ('Negro',  m_negro,  (80,  80,  80)),
    ]

    detectado = None
    COOLDOWN_INTENTO = 1.5

    for nombre, mascara, color_bgr in colores:
        mascara  = cv2.morphologyEx(mascara, cv2.MORPH_OPEN,  k_open)
        mascara  = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, k_close)
        m_ref    = cv2.erode(mascara, KERNEL_ERODE, iterations=1)
        m_ref    = cv2.dilate(m_ref,  KERNEL_ERODE, iterations=2)

        contornos, _ = cv2.findContours(m_ref, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_TC89_KCOS)

        bbox_raw = None
        c_valido = None
        if contornos:
            c = max(contornos, key=cv2.contourArea)
            area = cv2.contourArea(c)
            if area >= area_min:
                x, y, w, h = cv2.boundingRect(c)
                px_c = cv2.countNonZero(mascara[y:y+h, x:x+w])
                if px_c / (w * h) >= RATIO_COB_MIN:
                    bbox_raw = (x, y, w, h)
                    c_valido = c

        if nombre not in trackers:
            trackers[nombre] = TrackerColor()
            
        bbox_e = trackers[nombre].actualizar(bbox_raw, frame.shape)

        if bbox_e is None:
            temporizadores[nombre] = 0.0
            continue

        x, y, w, h  = bbox_e
        if temporizadores.setdefault(nombre, 0.0) == 0.0:
            temporizadores[nombre] = t_act
            
        en_calib = (t_act - temporizadores[nombre]) <= 3.0
        
        orient, _  = calcular_orientacion(w, h)
        fh, fw = frame.shape[:2]
        x_norm = round((x + w/2.0)/fw * 2 - 1, 2)
        y_norm = round(1 - (y + h/2.0)/fh * 2, 2)
        z_est  = estimar_z(w * h, frame.shape)
        
        label_y = max(18, y - 12)
        
        # Color de dibujo: para Negro usar gris claro para que sea visible
        draw_color = (120, 120, 120) if nombre == 'Negro' else color_bgr
        
        if en_calib:
            paso = 15
            for i in range(x, x + w, paso):
                cv2.line(frame, (i, y), (i, y+h), draw_color, 1)
            for j in range(y, y + h, paso):
                cv2.line(frame, (x, j), (x+w, j), draw_color, 1)
            cv2.putText(frame, 'Calibrando...', (x, label_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, draw_color, 2)
        else:
            if c_valido is not None:
                eps  = 0.008 * cv2.arcLength(c_valido, True)
                c_s  = cv2.approxPolyDP(c_valido, eps, True)
                cv2.drawContours(frame, [c_s], -1, draw_color, 2)
                cv2.rectangle(frame, (x, y), (x+w, y+h), draw_color, 1)
            else:
                cv2.rectangle(frame, (x, y), (x+w, y+h), draw_color, 2)

            arrow  = '↕' if orient == 'Vertical' else ('↔' if orient == 'Horizontal' else '⊙')
            lbl_p  = f'{nombre} {arrow}'
            lbl_c  = f'X:{x_norm:+.1f} Y:{y_norm:+.1f} Z:{z_est}m'

            (tw, th), _ = cv2.getTextSize(lbl_p, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            cv2.rectangle(frame, (x, label_y-th-4), (x+tw+4, label_y+4), (30,30,30), -1)
            cv2.putText(frame, lbl_p, (x+2, label_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, draw_color, 2)

            cy2 = label_y + th + 6
            (cw, ch), _ = cv2.getTextSize(lbl_c, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
            cv2.rectangle(frame, (x, cy2-ch-2), (x+cw+4, cy2+2), (30,30,30), -1)
            cv2.putText(frame, lbl_c, (x+2, cy2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (220,220,220), 1)

            # Lógica de cooldown y registro
            huella = calcular_huella_hsv(hsv, mascara, (x, y, w, h))
            
            if (t_act - ultimo_intento.get(nombre, 0.0)) >= COOLDOWN_INTENTO:
                ultimo_intento[nombre] = t_act
                if not es_mismo_objeto(huella, huellas[nombre]):
                    if huella is not None:
                        huellas[nombre].append(huella)
                    counts[nombre] += 1
            
            # Map pesos (Carga)
            mapa_cargas = { "Rojo": 15.0, "Blanco": 25.0, "Negro": 40.0 }
            carga_kg = mapa_cargas.get(nombre, 0.0)

            detectado = {
                "color": nombre,
                "carga_kg": carga_kg,
                "orientacion": orient,
                "x_norm": x_norm,
                "y_norm": y_norm,
                "counts": counts
            }

    if detectado is None:
        return {"counts": counts}, frame

    return detectado, frame
