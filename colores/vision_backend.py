import cv2
import numpy as np
import time
import math

# ==============================================================================
# CONFIGURACION LIGERA
# ==============================================================================
LIMITES_PELOTAS = {'Rojo': 20, 'Negro': 20, 'Blanco': 20}
MESH_FRACTION = 0.38

HSV_RANGOS = {
    'Rojo': [
        (np.array([0,   50, 40]),  np.array([12,  255, 255])),
        (np.array([160, 50, 40]),  np.array([180, 255, 255])),
    ],
    'Blanco': [
        (np.array([0,   0,  160]), np.array([180, 60, 255])),
    ],
    'Negro': [
        # Rango principal: negro puro, oscuro y semi-oscuro
        (np.array([0,  0,   0]),   np.array([180, 255, 110])),
        # Rango secundario: negro brillante con reflejo de luz fuerte
        (np.array([0,  0,  86]),   np.array([180, 90,  170])),
    ],
}
UMBRAL_VALIDACION_COLOR = {
    'Rojo':   0.12,
    'Blanco': 0.18,   # Pelotas grises-blancas tienen menos píxeles "blancos puros"
    'Negro':  0.18,   # Umbral más bajo para no descartar pelotas negras con reflejo
}

def get_color_bgr(nombre):
    n = nombre.lower()
    if 'rojo'   in n: return (0,   0, 220)
    if 'blanco' in n: return (200, 200, 200)
    if 'negro'  in n: return (80,  80,  80)
    return (0, 220, 220)

# ==============================================================================
# UTILS WEB OPTIMIZADOS (CPU O(1))
# ==============================================================================
def estimar_z_fast(radio_px, frame_shape):
    fh, fw = frame_shape[:2]
    if radio_px <= 0: return 15.0
    frac = (math.pi * radio_px * radio_px) / (fh * fw)
    z = 1.0 / (frac * 10 + 0.01)
    return round(max(0.1, min(15.0, z)), 2)

def get_zona_deteccion(frame_shape):
    fh, fw = frame_shape[:2]
    return fw // 2, fh // 2, int(min(fw, fh) * MESH_FRACTION)

def dentro_del_circulo(px, py, cx, cy, radio, r_obj=0):
    return math.hypot(px - cx, py - cy) <= radio + (r_obj * 0.8)

def es_forma_pelota(x1, y1, x2, y2, frame_shape, nombre=None, max_aspect=1.6, min_frac=0.0003, max_frac=0.20):
    w, h = x2 - x1, y2 - y1
    if w <= 0 or h <= 0: return False
    
    # Para pelotas negras, ser permisivos con el aspect ratio 
    # por si YOLO agrupa dos pelotas que se tocan en un solo bounding box
    if nombre == 'Negro':
        max_aspect = 3.0
        
    if max(w, h) / (min(w, h) + 1e-9) > max_aspect: return False
    # Filtro de circularidad: el área del bounding box debe ser similar al área de un círculo
    # Para una pelota real, el círculo inscrito ocupa ~78% del cuadrado
    # Si es un objeto rectangular (ratón, teclado), esta fracción baja mucho
    area_ratio = (w * h) / (frame_shape[1] * frame_shape[0])
    return min_frac <= area_ratio <= max_frac

def validar_color_en_roi(frame, x1, y1, x2, y2, nombre, umbral_frac=None):
    if umbral_frac is None: umbral_frac = UMBRAL_VALIDACION_COLOR.get(nombre, 0.08)
    fh, fw = frame.shape[:2]
    x1c, y1c = max(0, int(x1)), max(0, int(y1))
    x2c, y2c = min(fw, int(x2)), min(fh, int(y2))
    roi = frame[y1c:y2c, x1c:x2c]
    if roi.size == 0: return False
    
    # --- MEJORA ESTRICTA CON CLAHE LOCAL ---
    # Normalizamos la iluminación aislando la luminancia en espacio LAB
    lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(4,4))
    l = clahe.apply(l)
    roi_clahe = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    
    rh, rw = roi.shape[:2]
    Y, X = np.ogrid[:rh, :rw]
    dist_from_center = np.sqrt((X - rw//2)**2 + (Y - rh//2)**2)
    mask = dist_from_center <= min(rw, rh)//2
    
    hsv = cv2.cvtColor(roi_clahe, cv2.COLOR_BGR2HSV)
    color_mask = np.zeros((rh, rw), dtype=bool)
    
    for lo, hi in HSV_RANGOS.get(nombre, []):
        color_mask |= (cv2.inRange(hsv, lo, hi) > 0)
        
    color_mask &= mask
    total_px = np.count_nonzero(mask)
    if total_px == 0: return False
    
    return (np.count_nonzero(color_mask) / total_px) >= umbral_frac

def nms_global(detecciones_dict, factor_radio=0.5):
    # Agrupar todas las detecciones: (color, cx, cy, r, contour (opcional))
    todas = []
    for color, lista in detecciones_dict.items():
        for det in lista:
            todas.append((color, *det))
            
    if len(todas) <= 1: return detecciones_dict
    
    # Ordenar por tamaño (radio) de mayor a menor para priorizar las cajas más precisas
    ordenadas = sorted(todas, key=lambda d: d[3], reverse=True)
    
    resultado = {k: [] for k in detecciones_dict.keys()}
    aceptadas = []
    
    for item in ordenadas:
        color, cx, cy, r = item[0:4]
        contour = item[4] if len(item) > 4 else None
        
        # Si NO choca con ninguna aceptada, la agregamos
        if not any(math.hypot(cx - fx, cy - fy) < (r + fr) * factor_radio for fx, fy, fr in aceptadas):
            aceptadas.append((cx, cy, r))
            if contour is not None:
                resultado[color].append((cx, cy, r, contour))
            else:
                resultado[color].append((cx, cy, r))
            
    return resultado

class TrackerLigero:
    """Tracker EMA ultraligero que reemplaza el Gaussian Process."""
    def __init__(self, alpha=0.6, frames_conf=1, frames_perdida=2):
        self.alpha = alpha
        self.frames_conf = frames_conf
        self.frames_perdida = frames_perdida
        self.reiniciar()

    def reiniciar(self):
        self.suave = None
        self.conteo_det = 0
        self.conteo_perd = 0
        self.visible = False

    def actualizar(self, deteccion):
        if deteccion is None:
            self.conteo_det = 0
            self.conteo_perd += 1
            if self.conteo_perd >= self.frames_perdida:
                self.visible = False
                self.suave = None
            return tuple(int(round(v)) for v in self.suave) if self.visible and self.suave else None

        self.conteo_perd = 0
        self.conteo_det = min(self.conteo_det + 1, self.frames_conf + 10)

        if self.conteo_det < self.frames_conf:
            if self.suave is None:
                self.suave = tuple(float(v) for v in deteccion[:3])
            return None

        if self.suave is None:
            self.suave = tuple(float(v) for v in deteccion[:3])
            self.visible = True
            return tuple(int(round(v)) for v in deteccion[:3])

        sx = self.alpha * deteccion[0] + (1.0 - self.alpha) * self.suave[0]
        sy = self.alpha * deteccion[1] + (1.0 - self.alpha) * self.suave[1]
        sr = self.alpha * deteccion[2] + (1.0 - self.alpha) * self.suave[2]
        self.suave = (sx, sy, sr)
        self.visible = True
        return (int(round(sx)), int(round(sy)), int(round(sr)))

def emparejar_detecciones(trackers, detecciones):
    asignaciones = [None] * len(trackers)
    if not detecciones: return asignaciones
    det_usadas = set()
    for i, tr in enumerate(trackers):
        if tr.suave is not None and tr.visible:
            mejor_det, mejor_dist = None, float('inf')
            for j, d in enumerate(detecciones):
                if j in det_usadas: continue
                dist = math.hypot(tr.suave[0] - d[0], tr.suave[1] - d[1])
                if dist < mejor_dist and dist < 100:
                    mejor_dist, mejor_det = dist, j
            if mejor_det is not None:
                asignaciones[i] = detecciones[mejor_det]
                det_usadas.add(mejor_det)
    for j, d in enumerate(detecciones):
        if j not in det_usadas:
            for i, tr in enumerate(trackers):
                if asignaciones[i] is None and (tr.suave is None or not tr.visible):
                    asignaciones[i] = d; break
    return asignaciones

def es_falso_positivo_ligero(frame, x1, y1, x2, y2, nombre):
    roi = frame[max(0, int(y1)):int(y2), max(0, int(x1)):int(x2)]
    if roi.size == 0: return False
    
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    v_mean = np.mean(hsv[:,:,2])
    s_mean = np.mean(hsv[:,:,1])
    
    if nombre == 'Blanco':
        # Las sombras o pelotas negras tienen v_mean bajo. Una pelota blanca real es muy brillante.
        if v_mean < 120: return True  # Filtra pelotas negras (aún con reflejos) o sombras
        if s_mean > 120: return True # Tiene demasiado color para ser blanco puro
        
    elif nombre == 'Rojo':
        # Los fondos oscuros que YOLO confunde con rojo suelen tener poca saturación
        if v_mean < 40: return True
        if s_mean < 50: return True  # Un rojo vivo tiene saturación alta
        
    # Negro: sin filtro heurístico — confiamos 100% en YOLO para detectar pelotas negras.
    # Las pelotas negras brillosas o bajo iluminación variable tienen valores HSV muy distintos
    # y cualquier filtro de brillo/saturación termina descartando detecciones válidas.
        
    return False

# ==============================================================================
# PROCESAMIENTO PRINCIPAL
# ==============================================================================
def procesar_frame_yolo_api(frame, estado, modelo_yolo, mobile_mode=False, calibrate_mode=False):
    """
    Ruta optimizada para detección en tiempo real.
    - Se elimina CLAHE pesado global.
    - Se elimina Estabilizador EIS y cálculos de Blur.
    - Trackeo por EMA ultraligero.
    """
    if 'trackers_ligero' not in estado:
        estado['trackers_ligero'] = {
            'Rojo': [TrackerLigero() for _ in range(LIMITES_PELOTAS['Rojo'])],
            'Blanco': [TrackerLigero() for _ in range(LIMITES_PELOTAS['Blanco'])],
            'Negro': [TrackerLigero() for _ in range(LIMITES_PELOTAS['Negro'])]
        }
        estado['temporizadores'] = {'Rojo': [0.0]*LIMITES_PELOTAS['Rojo'], 'Blanco': [0.0]*LIMITES_PELOTAS['Blanco'], 'Negro': [0.0]*LIMITES_PELOTAS['Negro']}

    trackers = estado['trackers_ligero']
    temporizadores = estado['temporizadores']
    counts = estado.setdefault('counts', {'Rojo': 0, 'Blanco': 0, 'Negro': 0})
    ultimo_intento = estado.setdefault('ultimo_intento', {})
    
    t_act = time.time()
    fh, fw = frame.shape[:2]
    cx_scr, cy_scr, radio_zona = get_zona_deteccion(frame.shape)

    background_profile = estado.get('background_profile')

    # Dibujar retícula central
    c = (255, 255, 255)
    # --- Malla Ligera (Grid overlay) ---
    step = 40
    overlay = frame.copy()
    for x in range(0, fw, step):
        cv2.line(overlay, (x, 0), (x, fh), (200, 255, 200), 1)
    for y in range(0, fh, step):
        cv2.line(overlay, (0, y), (fw, y), (200, 255, 200), 1)
    # Hacerla semi-transparente
    cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)
    # -----------------------------------

    cv2.rectangle(frame, (cx_scr-radio_zona, cy_scr-radio_zona), (cx_scr+radio_zona, cy_scr+radio_zona), c, 1)
    cv2.circle(frame, (cx_scr, cy_scr), radio_zona, c, 1)

    detecciones_brutas = {'Rojo': [], 'Blanco': [], 'Negro': []}

    # Inferencia Directa YOLO — dos pasadas para no sacrificar negro
    # Pasada 1: conf=0.80 para Rojo y Blanco (alta precisión, sin cambios)
    # Pasada 2: conf=0.45 exclusivamente para Negro (mayor sensibilidad, pelotas oscuras)
    if modelo_yolo is not None:
        def _procesar_cajas(cajas, masks, solo_negro=False):
            """Procesa las cajas de YOLO y agrega detecciones válidas a detecciones_brutas."""
            if cajas is None: return
            
            # --- ON-THE-FLY BACKGROUND ESTIMATION (solo en primera pasada) ---
            if not solo_negro:
                mask_bg = np.zeros((fh, fw), dtype=np.uint8)
                cv2.circle(mask_bg, (cx_scr, cy_scr), radio_zona, 255, -1)
                for i in range(len(cajas)):
                    x1, y1, x2, y2 = map(int, cajas.xyxy[i].tolist())
                    cv2.rectangle(mask_bg, (x1, y1), (x2, y2), 0, -1)
                bg_pixels = cv2.bitwise_and(frame, frame, mask=mask_bg)
                hsv_bg = cv2.cvtColor(bg_pixels, cv2.COLOR_BGR2HSV)
                v_channel = hsv_bg[:,:,2]
                valid_v = v_channel[mask_bg == 255]
                if len(valid_v) > 0:
                    bg_v = np.median(valid_v)
                    estado['background_profile'] = {'v_mean': bg_v}
            # ----------------------------------------
            
            for i in range(len(cajas)):
                cls_id = int(cajas.cls[i].item())
                # Nuevo modelo (entrenamiento_seg): 0=Pelota blanca, 1=Pelota negra, 2=Pelota roja
                nombre = {0: 'Blanco', 1: 'Negro', 2: 'Rojo'}.get(cls_id)
                if not nombre: continue
                
                # Pasada exclusiva negro: ignorar Rojo y Blanco
                if solo_negro and nombre != 'Negro': continue
                # Pasada normal: ignorar Negro (lo procesa la segunda pasada)
                if not solo_negro and nombre == 'Negro': continue
                
                x1, y1, x2, y2 = cajas.xyxy[i].tolist()
                cx, cy = int((x1+x2)/2), int((y1+y2)/2)
                r_box = int((x2-x1 + y2-y1)/4)
                
                # Permitimos que la pelota esté parcialmente fuera del círculo si su centro está cerca del borde
                if not dentro_del_circulo(cx, cy, cx_scr, cy_scr, radio_zona, r_box): continue
                if not es_forma_pelota(x1, y1, x2, y2, frame.shape, nombre): continue
                if es_falso_positivo_ligero(frame, x1, y1, x2, y2, nombre): continue
                
                r = r_box
                z_estimado = estimar_z_fast(r, frame.shape)
                # Para pelotas negras no aplicar el filtro de distancia: son difíciles de detectar
                # y el modelo ya es suficientemente selectivo con conf=0.30
                if nombre != 'Negro' and z_estimado > 10.0: continue
                
                # --- Separación nativa para pelotas negras agrupadas ---
                w, h = x2 - x1, y2 - y1
                aspect = max(w, h) / (min(w, h) + 1e-9)
                
                # Si YOLO fusionó dos pelotas negras, el aspect ratio será > 1.5
                if nombre == 'Negro' and aspect > 1.5:
                    if w > h:
                        # Horizontal split
                        cx1, cy1 = int(x1 + w/4), cy
                        cx2, cy2 = int(x2 - w/4), cy
                        r_split = int(h/2)
                    else:
                        # Vertical split
                        cx1, cy1 = cx, int(y1 + h/4)
                        cx2, cy2 = cx, int(y2 - h/4)
                        r_split = int(w/2)
                        
                    detecciones_brutas[nombre].append((cx1, cy1, r_split))
                    detecciones_brutas[nombre].append((cx2, cy2, r_split))
                    continue
                # ---------------------------------------------------------
                
                contour = None
                if masks is not None and masks.xy is not None and len(masks.xy) > i:
                    seg = masks.xy[i]
                    if len(seg) > 0:
                        contour = np.array(seg, dtype=np.int32).reshape((-1, 1, 2))
                        (fx, fy), fr = cv2.minEnclosingCircle(contour)
                        r_max = r_box
                        cx, cy, r = int(fx), int(fy), min(int(fr), r_max)
                
                if contour is not None:
                    detecciones_brutas[nombre].append((cx, cy, r, contour))
                else:
                    detecciones_brutas[nombre].append((cx, cy, r))

        # --- Pasada 1: Rojo + Blanco con conf=0.75, iou=0.30 para mejor separación ---
        res1 = modelo_yolo.predict(frame, conf=0.75, iou=0.30, imgsz=640, verbose=False)
        if len(res1) > 0 and res1[0].boxes is not None:
            _procesar_cajas(res1[0].boxes, res1[0].masks if hasattr(res1[0], 'masks') else None, solo_negro=False)

        # --- Pasada 2: Solo Negro con conf=0.15, iou=0.30 para máxima sensibilidad y separación ---
        # Aumentamos imgsz a 640 para no perder resolución en pelotas pequeñas/oscuras
        res2 = modelo_yolo.predict(frame, conf=0.15, iou=0.30, imgsz=640, verbose=False)
        if len(res2) > 0 and res2[0].boxes is not None:
            _procesar_cajas(res2[0].boxes, res2[0].masks if hasattr(res2[0], 'masks') else None, solo_negro=True)

        # NMS Global para no marcar el mismo objeto 2 veces con colores distintos o cajas repetidas
        # factor_radio 0.45: dos pelotas que se toquen lateralmente NO se fusionan
        detecciones_brutas = nms_global(detecciones_brutas, factor_radio=0.45)

    detectado_result = None
    COOLDOWN = 1.5
    
    # Contabilizar la cantidad real actual de objetos detectados (no histórico)
    counts = {'Rojo': len(detecciones_brutas['Rojo']), 
              'Blanco': len(detecciones_brutas['Blanco']), 
              'Negro': len(detecciones_brutas['Negro'])}
    estado['counts'] = counts

    # Si es mobile, saltamos el tracker pesado y reportamos directo
    if mobile_mode:
        all_balls = []
        for nombre in ['Negro', 'Rojo', 'Blanco']:
            for idx, det in enumerate(detecciones_brutas[nombre]):
                if len(det) > 3 and det[3] is not None:
                    cx, cy, r, contour = det
                    color_bgr = get_color_bgr(nombre)
                    cv2.circle(frame, (cx, cy), r, color_bgr, 2)
                else:
                    cx, cy, r = det[:3]
                    color_bgr = get_color_bgr(nombre)
                    cv2.circle(frame, (cx, cy), r, color_bgr, 2)
                    
                lbl = f'{idx+1}'
                cv2.putText(frame, lbl, (cx-r, cy-r-5), cv2.FONT_HERSHEY_COMPLEX, 0.5, color_bgr, 1)
                
                all_balls.append({
                    "color": nombre,
                    "x_norm": round(cx / fw, 3),
                    "y_norm": round(cy / fh, 3),
                    "r_norm": round(r / fw, 3)
                })
                
                # Reportar detectado instantáneo
                mapa_cargas = {"Rojo": 1.0, "Blanco": 3.0, "Negro": 5.0}
                
                if not detectado_result:
                    total_carga = sum([counts.get(k, 0) * mapa_cargas.get(k, 0.0) for k in mapa_cargas])
                    detectado_result = {
                        "color": "Mixto" if sum(counts.values()) > 1 else nombre,
                        "carga_kg": total_carga,
                        "orientacion": "No calculado (Optimizado)",
                        "x_norm": round(cx / fw * 2 - 1, 2),
                        "y_norm": round(1 - cy / fh * 2, 2),
                        "counts": counts,
                        "balls": all_balls
                    }
                else:
                    detectado_result["balls"] = all_balls
                    
        return detectado_result, frame

    for nombre in ['Negro', 'Rojo', 'Blanco']:
        lista = sorted(detecciones_brutas[nombre], key=lambda d: (d[1]//80, d[0]//80))
        asignaciones = emparejar_detecciones(trackers[nombre], lista)
        
        visible_count = 0
        for idx, det in enumerate(asignaciones):
            tr = trackers[nombre][idx]
            result = tr.actualizar(det)
            if result is None:
                temporizadores[nombre][idx] = 0.0
                continue
            
            visible_count += 1
            cx, cy, r = result
            if temporizadores[nombre][idx] == 0.0: temporizadores[nombre][idx] = t_act
            
            color_bgr = get_color_bgr(nombre)
            x_norm = round(cx / fw * 2 - 1, 2)
            y_norm = round(1 - cy / fh * 2, 2)
            
            # Anotar Frame
            if det is not None and len(det) > 3 and det[3] is not None:
                # Dibujar círculo ajustado en lugar del contorno poligonal crudo
                cv2.circle(frame, (cx, cy), r, color_bgr, 2)
            else:
                cv2.circle(frame, (cx, cy), r, color_bgr, 2)
                
            lbl = f'{visible_count}'
            cv2.putText(frame, lbl, (cx-r, cy-r-5), cv2.FONT_HERSHEY_COMPLEX, 0.5, color_bgr, 1)
            
            # Registrar Detección y Puntos
            if (t_act - ultimo_intento.get(nombre, 0.0)) >= COOLDOWN and not detectado_result:
                ultimo_intento[nombre] = t_act
                mapa_cargas = {"Rojo": 1.0, "Blanco": 3.0, "Negro": 5.0}
                total_carga = sum([counts.get(k, 0) * mapa_cargas.get(k, 0.0) for k in mapa_cargas])
                detectado_result = {
                    "color": "Mixto" if sum(counts.values()) > 1 else nombre,
                    "carga_kg": total_carga,
                    "orientacion": "EMA_Tracked",
                    "x_norm": x_norm,
                    "y_norm": y_norm,
                    "counts": counts
                }

    return detectado_result, frame