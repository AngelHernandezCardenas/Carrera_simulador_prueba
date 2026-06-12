import cv2
import numpy as np
import time

# ─── Rangos HSV (H: 0-179, S: 0-255, V: 0-255) ───────────────────────────────
RANGO_ROJO_1 = (np.array([  0, 150,  80]), np.array([  8, 255, 255]))
RANGO_ROJO_2 = (np.array([172, 150,  80]), np.array([180, 255, 255]))
RANGO_VERDE  = (np.array([ 45, 140,  80]), np.array([ 78, 255, 255]))
RANGO_AZUL   = (np.array([108, 150,  60]), np.array([128, 255, 255]))

RATIO_COB_MIN = 0.25
FRAC_AREA_MIN = 0.005

KERNEL_OPEN  = np.ones((5, 5), np.uint8)
KERNEL_CLOSE = np.ones((7, 7), np.uint8)
KERNEL_ERODE = np.ones((3, 3), np.uint8)

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

def procesar_frame_vision_servidor(frame, trackers):
    """
    Detecta Rojo/Verde/Azul devolviendo el objeto detectado de mayor área o prioridad.
    En un flujo cliente-servidor devolvemos sólo JSON con la detección principal.
    """
    blurred = cv2.GaussianBlur(frame, (5, 5), 0)
    hsv     = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
    
    area_min = max(1000, int(frame.shape[0] * frame.shape[1] * FRAC_AREA_MIN))

    m_rojo  = cv2.add(cv2.inRange(hsv, *RANGO_ROJO_1), cv2.inRange(hsv, *RANGO_ROJO_2))
    m_verde = cv2.inRange(hsv, *RANGO_VERDE)
    m_azul  = cv2.inRange(hsv, *RANGO_AZUL)

    colores = [
        ('Rojo',  m_rojo),
        ('Verde', m_verde),
        ('Azul',  m_azul),
    ]

    detectado = None

    for nombre, mascara in colores:
        mascara  = cv2.morphologyEx(mascara, cv2.MORPH_OPEN,  KERNEL_OPEN)
        mascara  = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, KERNEL_CLOSE)
        m_ref    = cv2.erode(mascara, KERNEL_ERODE, iterations=1)
        m_ref    = cv2.dilate(m_ref,  KERNEL_ERODE, iterations=2)

        contornos, _ = cv2.findContours(m_ref, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_TC89_KCOS)

        bbox_raw = None
        if contornos:
            c = max(contornos, key=cv2.contourArea)
            area = cv2.contourArea(c)
            if area >= area_min:
                x, y, w, h = cv2.boundingRect(c)
                px_c = cv2.countNonZero(mascara[y:y+h, x:x+w])
                if px_c / (w * h) >= RATIO_COB_MIN:
                    bbox_raw = (x, y, w, h)

        if nombre not in trackers:
            trackers[nombre] = TrackerColor()
            
        bbox_e = trackers[nombre].actualizar(bbox_raw, frame.shape)

        if bbox_e is not None:
            x, y, w, h  = bbox_e
            orient, _  = calcular_orientacion(w, h)
            # Calculamos las normadas (sólo para referencia, ya que no son de ArcGIS directamente)
            fh, fw = frame.shape[:2]
            x_norm = round((x + w/2.0)/fw * 2 - 1, 2)
            y_norm = round(1 - (y + h/2.0)/fh * 2, 2)
            
            # Map pesos (Carga)
            mapa_cargas = { "Rojo": 15.0, "Verde": 25.0, "Azul": 40.0 }
            carga_kg = mapa_cargas.get(nombre, 0.0)

            # Para simplificar el servidor solo devolvemos 1 color (prioridad el último que actualice, o el primero)
            detectado = {
                "color": nombre,
                "carga_kg": carga_kg,
                "orientacion": orient,
                "x_norm": x_norm,
                "y_norm": y_norm
            }

    return detectado
