import cv2
import numpy as np
import time
import math

# ==============================================================================
# CONFIGURACION LIGERA
# ==============================================================================
LIMITES_PELOTAS = {'Rojo': 10, 'Negro': 2, 'Blanco': 3}
MESH_FRACTION = 0.38

HSV_RANGOS = {
    'Rojo': [
        (np.array([0,   50, 40]),  np.array([12,  255, 255])),
        (np.array([160, 50, 40]),  np.array([180, 255, 255])),
    ],
    'Blanco': [
        (np.array([0,   0,  180]), np.array([180, 55, 255])),
    ],
    'Negro': [
        (np.array([0,  0,   0]),   np.array([180, 255,  75])),
    ],
}
UMBRAL_VALIDACION_COLOR = {
    'Rojo':   0.08,
    'Blanco': 0.25,
    'Negro':  0.08,
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

def dentro_del_circulo(px, py, cx, cy, radio):
    return math.hypot(px - cx, py - cy) <= radio

def es_forma_pelota(x1, y1, x2, y2, frame_shape, max_aspect=1.25, min_frac=0.0003, max_frac=0.50):
    w, h = x2 - x1, y2 - y1
    if w <= 0 or h <= 0: return False
    if max(w, h) / (min(w, h) + 1e-9) > max_aspect: return False
    return min_frac <= ((w * h) / (frame_shape[1] * frame_shape[0])) <= max_frac

def validar_color_en_roi(frame, x1, y1, x2, y2, nombre, umbral_frac=None):
    if umbral_frac is None: umbral_frac = UMBRAL_VALIDACION_COLOR.get(nombre, 0.08)
    fh, fw = frame.shape[:2]
    x1c, y1c = max(0, int(x1)), max(0, int(y1))
    x2c, y2c = min(fw, int(x2)), min(fh, int(y2))
    roi = frame[y1c:y2c, x1c:x2c]
    if roi.size == 0: return False
    
    rh, rw = roi.shape[:2]
    # Usar máscara circular estática simplificada en lugar de dibujar circulos per-frame
    # Aproximamos el cálculo creando una rápida en memoria
    Y, X = np.ogrid[:rh, :rw]
    dist_from_center = np.sqrt((X - rw//2)**2 + (Y - rh//2)**2)
    mask = dist_from_center <= min(rw, rh)//2
    
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    color_mask = np.zeros((rh, rw), dtype=bool)
    
    for lo, hi in HSV_RANGOS.get(nombre, []):
        color_mask |= (cv2.inRange(hsv, lo, hi) > 0)
        
    color_mask &= mask
    total_px = np.count_nonzero(mask)
    if total_px == 0: return False
    
    return (np.count_nonzero(color_mask) / total_px) >= umbral_frac

def nms_mismo_color(detecciones, factor_radio=0.4):
    if len(detecciones) <= 1: return detecciones
    ordenadas = sorted(detecciones, key=lambda d: d[2], reverse=True)
    resultado = []
    for cx, cy, r in ordenadas:
        if not any(math.hypot(cx - fx, cy - fy) < (r + fr) * factor_radio for fx, fy, fr in resultado):
            resultado.append((cx, cy, r))
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

# ==============================================================================
# ENTRY POINT API
# ==============================================================================
def procesar_frame_yolo_api(frame, estado, modelo_yolo, mobile_mode=False):
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

    # Dibujar retícula central
    c = (255, 255, 255)
    cv2.rectangle(frame, (cx_scr-radio_zona, cy_scr-radio_zona), (cx_scr+radio_zona, cy_scr+radio_zona), c, 1)
    cv2.circle(frame, (cx_scr, cy_scr), radio_zona, c, 1)

    detecciones_brutas = {'Rojo': [], 'Blanco': [], 'Negro': []}

    # Inferencia Directa YOLO Ultrarrápida (imgsz pequeño para +FPS)
    if modelo_yolo is not None:
        resultados = modelo_yolo.predict(frame, conf=0.80, imgsz=320, verbose=False) 
        if len(resultados) > 0 and resultados[0].boxes is not None:
            cajas = resultados[0].boxes
            for i in range(len(cajas)):
                cls_id = int(cajas.cls[i].item())
                nombre = {0: 'Rojo', 1: 'Blanco', 2: 'Negro'}.get(cls_id)
                if not nombre: continue
                
                x1, y1, x2, y2 = cajas.xyxy[i].tolist()
                cx, cy = int((x1+x2)/2), int((y1+y2)/2)
                
                # Descartar temprano (O(1)) antes de procesar imagen
                if not dentro_del_circulo(cx, cy, cx_scr, cy_scr, radio_zona): continue
                if not es_forma_pelota(x1, y1, x2, y2, frame.shape): continue
                if not validar_color_en_roi(frame, x1, y1, x2, y2, nombre): continue
                
                r = int((x2-x1 + y2-y1)/4)
                
                # Filtrar EXCLUSIVAMENTE PELOTAS: descartamos si la estimación de tamaño (z)
                # indica que es un artefacto enano (más allá de 10m)
                z_estimado = estimar_z_fast(r, frame.shape)
                if z_estimado > 10.0: continue
                
                detecciones_brutas[nombre].append((cx, cy, r))
                
        for nombre in detecciones_brutas:
            detecciones_brutas[nombre] = nms_mismo_color(detecciones_brutas[nombre])

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
                cx, cy, r = det
                color_bgr = get_color_bgr(nombre)
                cv2.circle(frame, (cx, cy), r, color_bgr, 3)
                lbl = f'{nombre} #{idx+1}'
                cv2.putText(frame, lbl, (cx-r, cy-r-5), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color_bgr, 2)
                
                all_balls.append({
                    "color": nombre,
                    "x_norm": round(cx / fw, 3),
                    "y_norm": round(cy / fh, 3),
                    "r_norm": round(r / fw, 3)
                })
                
                # Reportar detectado instantáneo
                mapa_cargas = {"Rojo": 1.0, "Blanco": 3.0, "Negro": 5.0}
                
                if not detectado_result:
                    detectado_result = {
                        "color": nombre,
                        "carga_kg": mapa_cargas.get(nombre, 0.0),
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
        
        for idx, det in enumerate(asignaciones):
            tr = trackers[nombre][idx]
            result = tr.actualizar(det)
            if result is None:
                temporizadores[nombre][idx] = 0.0
                continue
            
            cx, cy, r = result
            if temporizadores[nombre][idx] == 0.0: temporizadores[nombre][idx] = t_act
            
            color_bgr = get_color_bgr(nombre)
            x_norm = round(cx / fw * 2 - 1, 2)
            y_norm = round(1 - cy / fh * 2, 2)
            
            # Anotar Frame
            cv2.circle(frame, (cx, cy), r, color_bgr, 3)
            lbl = f'{nombre} #{idx+1}'
            cv2.putText(frame, lbl, (cx-r, cy-r-5), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color_bgr, 2)
            
            # Registrar Detección y Puntos
            if (t_act - ultimo_intento.get(nombre, 0.0)) >= COOLDOWN and not detectado_result:
                ultimo_intento[nombre] = t_act
                mapa_cargas = {"Rojo": 15.0, "Blanco": 25.0, "Negro": 40.0}
                detectado_result = {
                    "color": nombre,
                    "carga_kg": mapa_cargas.get(nombre, 0.0),
                    "orientacion": "EMA_Tracked",
                    "x_norm": x_norm,
                    "y_norm": y_norm,
                    "counts": counts
                }

    return detectado_result, frame
