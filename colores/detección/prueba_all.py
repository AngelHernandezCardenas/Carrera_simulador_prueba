# Celda 1 - Librerias  [V15 - Anti-Ghost + GP Depth + GP White + EIS]
import cv2
import numpy as np
import time
import math
import threading
import collections
import customtkinter as ctk
from PIL import Image
from ultralytics import YOLO
import os
import operator

# Librerias para Optimizador DEAP (GP Profundidad + GP White)
import random
from deap import base, creator, tools, algorithms, gp

ctk.set_appearance_mode('dark')
print('Celda 1 V15: lista.')

# Celda 2 - Mini-Caché de Calidad Visual (Temporal Denoising)
import cv2
import numpy as np
import collections

class FrameQualityCache:
    def __init__(self, history_size=3):
        self.history_size = history_size
        self.frames = collections.deque(maxlen=history_size)
        
    def aplicar_cache(self, frame):
        self.frames.append(frame)
        if len(self.frames) < 2:
            return frame
        avg_frame = np.zeros_like(frame, dtype=np.float32)
        for i, f in enumerate(self.frames):
            peso = (i + 1)
            cv2.accumulateWeighted(f, avg_frame, alpha=peso/sum(range(1, len(self.frames)+1)))
        frame_filtrado = cv2.convertScaleAbs(avg_frame)
        kernel = np.array([[0, -0.3, 0], [-0.3, 2.2, -0.3], [0, -0.3, 0]])
        return cv2.filter2D(frame_filtrado, -1, kernel)

print('Celda 2: Mini-Caché Visual activado.')

# Celda 2 - Motor de Vision V15 [Anti-Ghost + Blur + GP Depth + GP White + EIS + Circulo]
from pygrabber.dshow_graph import FilterGraph
import cv2
import numpy as np
import time
import math
import collections

def detectar_camaras_sistema():
    try:
        graph = FilterGraph()
        return [(i, n) for i, n in enumerate(graph.get_input_devices())]
    except Exception as e:
        print(f'Error al buscar camaras: {e}')
        return []

LIMITES_PELOTAS = {'Rojo': 10, 'Negro': 2, 'Blanco': 3}
MAX_PELOTAS_TOTAL = 10

# Radio del circulo de deteccion como fraccion del lado menor
MESH_FRACTION = 0.38

# Tiempo de calibracion por pelota (segundos)
TIEMPO_CALIBRACION = 3.0

# ─────────────────────────────────────────────────────────────
# 1. DETECCION DE MOVIMIENTO BRUSCO (BLUR) - PARAMETROS REALES
# ─────────────────────────────────────────────────────────────
class DetectorMovimiento:
    """
    Detecta frames borrosos (movimiento brusco de camara) usando
    la varianza del Laplaciano. Si la varianza cae por debajo
    del umbral, el frame se considera borroso y se salta la
    deteccion para evitar fantasmas.
    
    Tambien detecta movimiento excesivo entre frames consecutivos
    comparando diferencia absoluta promedio.
    
    V15: Parametros calibrados para estabilizacion REAL:
      - umbral_blur=35.0 (rechaza frames genuinamente borrosos)
      - umbral_movimiento=18.0 (rechaza sacudidas bruscas)
      - ventana_estabilidad=3 (requiere 3 frames estables seguidos)
    """
    def __init__(self, umbral_blur=35.0, umbral_movimiento=18.0, 
                 ventana_estabilidad=3):
        self.umbral_blur        = umbral_blur
        self.umbral_movimiento  = umbral_movimiento
        self.ventana_estabilidad = ventana_estabilidad
        self.prev_gray          = None
        self.frames_estables    = 0
    
    def frame_valido(self, frame):
        """Retorna True si el frame es estable y nitido."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Test 1: Nitidez (Laplaciano)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        nitido = laplacian_var >= self.umbral_blur
        
        # Test 2: Movimiento entre frames consecutivos
        movimiento_ok = True
        if self.prev_gray is not None:
            diff = cv2.absdiff(gray, self.prev_gray)
            mov_promedio = diff.mean()
            movimiento_ok = mov_promedio < self.umbral_movimiento
        self.prev_gray = gray.copy()
        
        # Requiere N frames estables consecutivos antes de detectar
        if nitido and movimiento_ok:
            self.frames_estables = min(self.frames_estables + 1, 
                                       self.ventana_estabilidad + 5)
        else:
            self.frames_estables = 0
        
        return self.frames_estables >= self.ventana_estabilidad

# ─────────────────────────────────────────────────────────────
# 1b. ESTABILIZACION ELECTRONICA DE IMAGEN (EIS)
# ─────────────────────────────────────────────────────────────
class EstabilizadorEIS:
    """
    Estabilizacion electronica ligera usando estimacion de
    transformacion afin parcial entre frames consecutivos.
    Compensa micro-movimientos de camara sin perder nitidez.
    
    Usa un buffer de transformaciones para suavizar el movimiento
    con media movil (rolling average).
    """
    def __init__(self, suavizado=5, max_correccion=15.0):
        self.suavizado = suavizado
        self.max_correccion = max_correccion
        self.prev_gray = None
        self.transforms = collections.deque(maxlen=suavizado)
        self.acumulado_dx = 0.0
        self.acumulado_dy = 0.0
    
    def estabilizar(self, frame):
        """Aplica estabilizacion electronica al frame."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        if self.prev_gray is None:
            self.prev_gray = gray.copy()
            return frame
        
        # Detectar puntos de interes en frame anterior
        prev_pts = cv2.goodFeaturesToTrack(
            self.prev_gray, maxCorners=200, qualityLevel=0.01,
            minDistance=30, blockSize=3
        )
        
        if prev_pts is None or len(prev_pts) < 10:
            self.prev_gray = gray.copy()
            return frame
        
        # Rastrear puntos al frame actual
        curr_pts, status, _ = cv2.calcOpticalFlowPyrLK(
            self.prev_gray, gray, prev_pts, None
        )
        
        # Filtrar solo buenos
        idx = np.where(status == 1)[0]
        if len(idx) < 6:
            self.prev_gray = gray.copy()
            return frame
        
        prev_good = prev_pts[idx]
        curr_good = curr_pts[idx]
        
        # Estimar transformacion afin parcial (traslacion + rotacion + escala)
        m, inliers = cv2.estimateAffinePartial2D(prev_good, curr_good)
        
        if m is None:
            self.prev_gray = gray.copy()
            return frame
        
        # Extraer traslacion
        dx = m[0, 2]
        dy = m[1, 2]
        
        self.transforms.append((dx, dy))
        
        # Calcular media movil de transformaciones
        if len(self.transforms) > 0:
            avg_dx = np.mean([t[0] for t in self.transforms])
            avg_dy = np.mean([t[1] for t in self.transforms])
        else:
            avg_dx, avg_dy = dx, dy
        
        # Correccion: diferencia entre movimiento real y suavizado
        corr_dx = avg_dx - dx
        corr_dy = avg_dy - dy
        
        # Limitar correccion maxima
        corr_dx = np.clip(corr_dx, -self.max_correccion, self.max_correccion)
        corr_dy = np.clip(corr_dy, -self.max_correccion, self.max_correccion)
        
        # Aplicar correccion
        M_corr = np.float32([[1, 0, corr_dx], [0, 1, corr_dy]])
        fh, fw = frame.shape[:2]
        frame_estabilizado = cv2.warpAffine(frame, M_corr, (fw, fh),
                                             borderMode=cv2.BORDER_REPLICATE)
        
        self.prev_gray = gray.copy()
        return frame_estabilizado


# ─────────────────────────────────────────────────────────────
# 2. NMS INTRA-COLOR (evita duplicados del mismo color)
# ─────────────────────────────────────────────────────────────
def nms_mismo_color(detecciones, factor_radio=0.4):
    """
    Si dos detecciones del MISMO color tienen centros mas cercanos
    que factor_radio * (r1 + r2), son la misma pelota.
    Conserva la de mayor radio (mas confiable).
    """
    if len(detecciones) <= 1:
        return detecciones
    # Ordenar por radio descendente (mas grande primero)
    ordenadas = sorted(detecciones, key=lambda d: d[2], reverse=True)
    resultado = []
    for d in ordenadas:
        cx, cy, r = d
        es_duplicado = False
        for f in resultado:
            fx, fy, fr = f
            dist = math.hypot(cx - fx, cy - fy)
            umbral = (r + fr) * factor_radio
            if dist < umbral:
                es_duplicado = True
                break
        if not es_duplicado:
            resultado.append(d)
    return resultado

# ─────────────────────────────────────────────────────────────
# 3. GP PARA ESTIMACION DE PROFUNDIDAD (DEAP)
# ─────────────────────────────────────────────────────────────
def _div_protegida(a, b):
    return a / b if abs(b) > 1e-6 else a

def _sqrt_protegida(a):
    return math.sqrt(abs(a))

def _log_protegido(a):
    return math.log(abs(a) + 1e-6)

def evolucionar_estimador_profundidad():
    """
    Usa Programacion Genetica (DEAP) para evolucionar una formula
    optima de estimacion de profundidad z = f(radio_px, frame_h, frame_w).
    
    Datos de calibracion sinteticos basados en modelo pinhole:
        z = (f_focal * D_real) / (2 * radio_px)
    
    Para una pelota de ~6.5cm de diametro, camara 640x480, FOV ~60 grados:
        f_focal ≈ fw / (2 * tan(FOV/2)) ≈ 554 px
        
    Distancia real -> radio esperado en pixels:
        0.3m -> ~60px,  0.5m -> ~36px,  1.0m -> ~18px,
        1.5m -> ~12px,  2.0m -> ~9px,   3.0m -> ~6px
    """
    # Datos de calibracion: (radio_px, frame_h, frame_w, z_real)
    datos = [
        (80,  480, 640, 0.22),
        (60,  480, 640, 0.30),
        (45,  480, 640, 0.40),
        (36,  480, 640, 0.50),
        (27,  480, 640, 0.67),
        (18,  480, 640, 1.00),
        (14,  480, 640, 1.29),
        (12,  480, 640, 1.50),
        (9,   480, 640, 2.00),
        (7,   480, 640, 2.57),
        (6,   480, 640, 3.00),
        (4,   480, 640, 4.50),
        # Resolucion 1280x720
        (120, 720, 1280, 0.30),
        (72,  720, 1280, 0.50),
        (36,  720, 1280, 1.00),
        (18,  720, 1280, 2.00),
        (12,  720, 1280, 3.00),
    ]
    
    # Configurar GP
    if hasattr(creator, 'FitnessMinDepth'):
        del creator.FitnessMinDepth
    if hasattr(creator, 'IndividualDepth'):
        del creator.IndividualDepth
    
    creator.create('FitnessMinDepth', base.Fitness, weights=(-1.0,))
    creator.create('IndividualDepth', gp.PrimitiveTree, fitness=creator.FitnessMinDepth)
    
    pset = gp.PrimitiveSet('DEPTH', 3)  # radio, fh, fw
    pset.renameArguments(ARG0='r', ARG1='fh', ARG2='fw')
    
    pset.addPrimitive(operator.add, 2)
    pset.addPrimitive(operator.sub, 2)
    pset.addPrimitive(operator.mul, 2)
    pset.addPrimitive(_div_protegida, 2)
    pset.addPrimitive(_sqrt_protegida, 1)
    pset.addPrimitive(_log_protegido, 1)
    pset.addPrimitive(operator.neg, 1)
    pset.addPrimitive(abs, 1)
    
    for c in [0.01, 0.065, 0.1, 0.5, 1.0, 2.0, 3.14, 10.0, 100.0, 554.0]:
        pset.addTerminal(c)
    
    toolbox_gp = base.Toolbox()
    toolbox_gp.register('expr', gp.genHalfAndHalf, pset=pset, min_=2, max_=5)
    toolbox_gp.register('individual', tools.initIterate, creator.IndividualDepth, toolbox_gp.expr)
    toolbox_gp.register('population', tools.initRepeat, list, toolbox_gp.individual)
    toolbox_gp.register('compile', gp.compile, pset=pset)
    
    def evaluar(individuo):
        func = toolbox_gp.compile(expr=individuo)
        error_total = 0.0
        for r_px, fh, fw, z_real in datos:
            try:
                z_pred = func(float(r_px), float(fh), float(fw))
                z_pred = max(0.05, min(10.0, float(z_pred)))
            except:
                return (1e6,)
            error_total += (z_pred - z_real) ** 2
        return (error_total / len(datos),)
    
    toolbox_gp.register('evaluate', evaluar)
    toolbox_gp.register('select', tools.selTournament, tournsize=4)
    toolbox_gp.register('mate', gp.cxOnePoint)
    toolbox_gp.register('expr_mut', gp.genFull, min_=1, max_=3)
    toolbox_gp.register('mutate', gp.mutUniform, expr=toolbox_gp.expr_mut, pset=pset)
    
    # Limitar profundidad del arbol para evitar bloat
    toolbox_gp.decorate('mate', gp.staticLimit(key=operator.attrgetter('height'), max_value=8))
    toolbox_gp.decorate('mutate', gp.staticLimit(key=operator.attrgetter('height'), max_value=8))
    
    random.seed(42)
    pop = toolbox_gp.population(n=300)
    hof = tools.HallOfFame(1)
    
    algorithms.eaSimple(pop, toolbox_gp,
                         cxpb=0.6, mutpb=0.3, ngen=50,
                         halloffame=hof, verbose=False)
    
    mejor = hof[0]
    func_mejor = toolbox_gp.compile(expr=mejor)
    fitness_mejor = evaluar(mejor)[0]
    print(f'GP Depth: MSE={fitness_mejor:.4f}, expr={str(mejor)[:80]}')
    return func_mejor

# Ejecutar GP al cargar la celda
print('Evolucionando estimador de profundidad con GP...')
_GP_DEPTH_FUNC = evolucionar_estimador_profundidad()

def estimar_z_gp(radio_px, frame_shape):
    """Usa la funcion evolucionada por GP para estimar Z."""
    fh, fw = frame_shape[:2]
    try:
        z = _GP_DEPTH_FUNC(float(radio_px), float(fh), float(fw))
        return round(max(0.1, min(5.0, float(z))), 2)
    except:
        # Fallback simple
        frac = (math.pi * radio_px * radio_px) / (fh * fw)
        return round(max(0.1, min(5.0, 1.0 / (frac * 10 + 0.01))), 2)


# ─────────────────────────────────────────────────────────────
# 3b. GP PARA OPTIMIZAR UMBRALES HSV DE BLANCO (DEAP)
# ─────────────────────────────────────────────────────────────
def evolucionar_umbral_blanco():
    """
    Usa GP (DEAP) para evolucionar los umbrales HSV optimos para
    detectar pelotas blancas sin falsos positivos en superficies blancas.
    
    Datos sinteticos:
      - Pelotas blancas reales: S bajo (0-40), V alto (190-255)
      - Superficies blancas falsas (mesas, paredes): S muy bajo (0-15), V medio-alto (150-230)
      - Pelotas con reflejos especulares: S variable, V muy alto
    
    Fitness: maximizar deteccion de pelotas reales, minimizar falsos positivos.
    
    Evoluciona una funcion f(S, V) -> score. Si score > 0, es pelota blanca.
    """
    # Datos: (S, V, es_pelota_real)
    # Pelotas blancas reales (deben ser aceptadas -> label=1)
    datos_positivos = [
        (5,   240, 1), (10,  235, 1), (15,  220, 1), (20,  210, 1),
        (8,   250, 1), (12,  230, 1), (25,  200, 1), (30,  195, 1),
        (3,   245, 1), (18,  215, 1), (35,  190, 1), (40,  185, 1),
        (7,   255, 1), (22,  205, 1), (28,  198, 1), (14,  225, 1),
    ]
    # Superficies blancas falsas (deben ser rechazadas -> label=0)
    datos_negativos = [
        (5,   170, 0), (3,   155, 0), (8,   160, 0), (2,   145, 0),
        (10,  140, 0), (4,   130, 0), (12,  165, 0), (6,   150, 0),
        (15,  120, 0), (7,   110, 0), (1,   175, 0), (9,   135, 0),
        # Reflejos especulares falsos (S alto, V alto -> no es blanco mate)
        (80,  240, 0), (100, 220, 0), (120, 200, 0), (90,  230, 0),
        (70,  210, 0), (60,  250, 0), (150, 190, 0), (110, 215, 0),
        # Grises claros (no son pelotas blancas)
        (5,    90, 0), (3,   100, 0), (8,    85, 0), (10,   95, 0),
    ]
    datos = datos_positivos + datos_negativos
    
    if hasattr(creator, 'FitnessMaxWhite'):
        del creator.FitnessMaxWhite
    if hasattr(creator, 'IndividualWhite'):
        del creator.IndividualWhite
    
    creator.create('FitnessMaxWhite', base.Fitness, weights=(1.0,))
    creator.create('IndividualWhite', gp.PrimitiveTree, fitness=creator.FitnessMaxWhite)
    
    pset = gp.PrimitiveSet('WHITE', 2)  # S, V
    pset.renameArguments(ARG0='S', ARG1='V')
    
    pset.addPrimitive(operator.add, 2)
    pset.addPrimitive(operator.sub, 2)
    pset.addPrimitive(operator.mul, 2)
    pset.addPrimitive(_div_protegida, 2)
    pset.addPrimitive(operator.neg, 1)
    pset.addPrimitive(abs, 1)
    
    for c in [0.0, 1.0, 5.0, 10.0, 50.0, 55.0, 100.0, 180.0, 200.0, 255.0]:
        pset.addTerminal(c)
    
    toolbox_w = base.Toolbox()
    toolbox_w.register('expr', gp.genHalfAndHalf, pset=pset, min_=2, max_=4)
    toolbox_w.register('individual', tools.initIterate, creator.IndividualWhite, toolbox_w.expr)
    toolbox_w.register('population', tools.initRepeat, list, toolbox_w.individual)
    toolbox_w.register('compile', gp.compile, pset=pset)
    
    def evaluar_blanco(individuo):
        func = toolbox_w.compile(expr=individuo)
        aciertos = 0
        total = len(datos)
        # Peso extra para falsos positivos (penalizar mas si detecta superficie falsa)
        for s_val, v_val, label in datos:
            try:
                score = func(float(s_val), float(v_val))
                prediccion = 1 if float(score) > 0 else 0
            except:
                return (-1e6,)
            if prediccion == label:
                aciertos += 1
            elif label == 0 and prediccion == 1:
                # Penalizar falso positivo con peso doble
                aciertos -= 2
        return (aciertos / total,)
    
    toolbox_w.register('evaluate', evaluar_blanco)
    toolbox_w.register('select', tools.selTournament, tournsize=4)
    toolbox_w.register('mate', gp.cxOnePoint)
    toolbox_w.register('expr_mut', gp.genFull, min_=1, max_=3)
    toolbox_w.register('mutate', gp.mutUniform, expr=toolbox_w.expr_mut, pset=pset)
    
    toolbox_w.decorate('mate', gp.staticLimit(key=operator.attrgetter('height'), max_value=7))
    toolbox_w.decorate('mutate', gp.staticLimit(key=operator.attrgetter('height'), max_value=7))
    
    random.seed(123)
    pop = toolbox_w.population(n=200)
    hof = tools.HallOfFame(1)
    
    algorithms.eaSimple(pop, toolbox_w,
                         cxpb=0.6, mutpb=0.3, ngen=40,
                         halloffame=hof, verbose=False)
    
    mejor = hof[0]
    func_mejor = toolbox_w.compile(expr=mejor)
    fitness_mejor = evaluar_blanco(mejor)[0]
    
    # Evaluar precision final
    tp, tn, fp, fn = 0, 0, 0, 0
    for s_val, v_val, label in datos:
        try:
            score = func_mejor(float(s_val), float(v_val))
            pred = 1 if float(score) > 0 else 0
        except:
            pred = 0
        if label == 1 and pred == 1: tp += 1
        elif label == 0 and pred == 0: tn += 1
        elif label == 0 and pred == 1: fp += 1
        elif label == 1 and pred == 0: fn += 1
    
    precision_fp = tn / (tn + fp) if (tn + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    
    print(f'GP White: accuracy={fitness_mejor:.3f}, FP_reject={precision_fp:.2%}, recall={recall:.2%}')
    print(f'  expr={str(mejor)[:80]}')
    
    # Si GP no converge bien (accuracy < 0.70), retornar None -> usar umbrales manuales
    if fitness_mejor < 0.70:
        print('  GP White: convergencia insuficiente, usando umbrales manuales.')
        return None
    
    return func_mejor

print('Evolucionando clasificador GP para blanco...')
_GP_WHITE_FUNC = evolucionar_umbral_blanco()


# ─────────────────────────────────────────────────────────────
# 4. RANGOS HSV / COLOR - V15 OPTIMIZADOS
# ─────────────────────────────────────────────────────────────
HSV_RANGOS = {
    'Rojo': [
        (np.array([0,   50, 40]),  np.array([12,  255, 255])),
        (np.array([160, 50, 40]),  np.array([180, 255, 255])),
    ],
    # V15: Blanco MUCHO mas estricto para evitar falsos positivos
    # en superficies blancas. S max reducido de 180->55, V min subido de 50->180
    'Blanco': [
        (np.array([0,   0,  180]), np.array([180, 55, 255])),
    ],
    'Negro': [
        (np.array([0,  0,   0]),   np.array([180, 255,  75])),
    ],
}

# Umbrales de validacion de color diferenciados por color
# V15: Blanco requiere 25% de pixels coincidentes (vs 8% general)
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

# ─────────────────────────────────────────────────────────────
# 5. ZONA DE DETECCION (CIRCULO) + RETICULA
# ─────────────────────────────────────────────────────────────
def get_zona_deteccion(frame_shape):
    fh, fw = frame_shape[:2]
    cx, cy = fw // 2, fh // 2
    radio = int(min(fw, fh) * MESH_FRACTION)
    return cx, cy, radio

def dibujar_reticula(frame):
    """Dibuja la reticula SIEMPRE (cuadrado + circulo + ejes)."""
    cx, cy, r = get_zona_deteccion(frame.shape)
    c = (255, 255, 255)
    cv2.rectangle(frame, (cx-r, cy-r), (cx+r, cy+r), c, 1)
    cv2.line(frame, (cx, cy-r), (cx, cy+r), c, 1)
    cv2.line(frame, (cx-r, cy), (cx+r, cy), c, 1)
    cv2.circle(frame, (cx, cy), r, c, 1)
    return cx, cy, r

def dentro_del_circulo(px, py, cx, cy, radio):
    return math.hypot(px - cx, py - cy) <= radio

# ─────────────────────────────────────────────────────────────
# 6. VALIDACION DE COLOR HSV - V15 con GP White
# ─────────────────────────────────────────────────────────────
def validar_color_en_roi(frame, x1, y1, x2, y2, nombre, umbral_frac=None):
    """
    V15: Validacion de color con umbrales diferenciados.
    Para blanco, aplica doble validacion:
      1. Filtro HSV estricto (rangos manuales optimizados)
      2. Clasificador GP evolucionado (si disponible)
    """
    if umbral_frac is None:
        umbral_frac = UMBRAL_VALIDACION_COLOR.get(nombre, 0.08)
    
    fh, fw = frame.shape[:2]
    x1c, y1c = max(0, int(x1)), max(0, int(y1))
    x2c, y2c = min(fw, int(x2)), min(fh, int(y2))
    roi = frame[y1c:y2c, x1c:x2c]
    if roi.size == 0: return False
    rh, rw = roi.shape[:2]
    mask = np.zeros((rh, rw), dtype=np.uint8)
    cv2.circle(mask, (rw//2, rh//2), min(rw, rh)//2, 255, -1)
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    color_mask = np.zeros((rh, rw), dtype=np.uint8)
    for lo, hi in HSV_RANGOS.get(nombre, []):
        color_mask |= cv2.inRange(hsv, lo, hi)
    color_mask &= mask
    total_px = cv2.countNonZero(mask)
    color_px = cv2.countNonZero(color_mask)
    if total_px == 0: return False
    
    ratio = color_px / total_px
    
    # Validacion HSV basica
    if ratio < umbral_frac:
        return False
    
    # V15: Para BLANCO, aplicar GP evolucionado como segunda capa
    if nombre == 'Blanco' and _GP_WHITE_FUNC is not None:
        # Calcular S y V promedio de la ROI dentro de la mascara
        hsv_masked = hsv.copy()
        # Solo pixels dentro de la mascara circular
        s_channel = hsv_masked[:, :, 1]
        v_channel = hsv_masked[:, :, 2]
        mask_bool = mask > 0
        if np.any(mask_bool):
            s_mean = float(np.mean(s_channel[mask_bool]))
            v_mean = float(np.mean(v_channel[mask_bool]))
            try:
                gp_score = _GP_WHITE_FUNC(s_mean, v_mean)
                if float(gp_score) <= 0:
                    return False  # GP dice que no es pelota blanca
            except:
                pass  # Si GP falla, confiar en HSV manual
    
    return True

# ─────────────────────────────────────────────────────────────
# 7. VALIDACION DE FORMA DE PELOTA
# ─────────────────────────────────────────────────────────────
def es_forma_pelota(x1, y1, x2, y2, frame_shape,
                    max_aspect=1.45, min_frac=0.0003, max_frac=0.50):
    w, h = x2 - x1, y2 - y1
    if w <= 0 or h <= 0: return False
    if max(w, h) / (min(w, h) + 1e-9) > max_aspect: return False
    fh, fw = frame_shape[:2]
    frac = (w * h) / (fw * fh)
    return min_frac <= frac <= max_frac

# ─────────────────────────────────────────────────────────────
# 8. TRACKER MEJORADO (Anti-Ghost)
# ─────────────────────────────────────────────────────────────
class TrackerCirculo:
    """
    Tracker con EMA (suavizado exponencial) y confirmacion estricta.
    - frames_conf=1: necesita 4 frames consecutivos para confirmar
    - frames_perdida=3: pierde la pelota rapido si desaparece
    - alpha=0.5: suaviza posicion para evitar saltos bruscos
    """
    def __init__(self, alpha=0.5, frames_conf=1, frames_perdida=3):
        self.alpha          = alpha
        self.frames_conf    = frames_conf
        self.frames_perdida = frames_perdida
        self.reiniciar()

    def reiniciar(self):
        self.suave       = None
        self.conteo_det  = 0
        self.conteo_perd = 0
        self.visible     = False

    def actualizar(self, deteccion):
        if deteccion is None:
            self.conteo_det  = 0
            self.conteo_perd = min(self.conteo_perd + 1, self.frames_perdida + 1)
            if self.conteo_perd >= self.frames_perdida:
                self.visible = False
                self.suave   = None
            return tuple(int(round(v)) for v in self.suave) if self.visible else None

        self.conteo_perd = 0
        self.conteo_det  = min(self.conteo_det + 1, self.frames_conf + 10)

        if self.conteo_det < self.frames_conf:
            # Aun acumulando confirmacion, guardar posicion provisional
            if self.suave is None:
                self.suave = tuple(float(v) for v in deteccion[:3])
            return None

        if self.suave is None:
            self.suave   = tuple(float(v) for v in deteccion[:3])
            self.visible = True
            return tuple(int(round(v)) for v in deteccion[:3])

        # Suavizado EMA para evitar saltos bruscos
        sx = self.alpha * deteccion[0] + (1.0 - self.alpha) * self.suave[0]
        sy = self.alpha * deteccion[1] + (1.0 - self.alpha) * self.suave[1]
        sr = self.alpha * deteccion[2] + (1.0 - self.alpha) * self.suave[2]
        self.suave   = (sx, sy, sr)
        self.visible = True
        return (int(round(sx)), int(round(sy)), int(round(sr)))

def emparejar_detecciones(trackers, detecciones):
    asignaciones = [None] * len(trackers)
    if not detecciones: return asignaciones
    det_usadas = set()
    for i, tr in enumerate(trackers):
        if tr.suave is not None and tr.visible:
            mejor_det  = None
            mejor_dist = float('inf')
            for j, d in enumerate(detecciones):
                if j in det_usadas: continue
                dist = math.hypot(tr.suave[0] - d[0], tr.suave[1] - d[1])
                if dist < mejor_dist and dist < 100:
                    mejor_dist = dist
                    mejor_det  = j
            if mejor_det is not None:
                asignaciones[i] = detecciones[mejor_det]
                det_usadas.add(mejor_det)
    for j, d in enumerate(detecciones):
        if j not in det_usadas:
            for i, tr in enumerate(trackers):
                if asignaciones[i] is None and (tr.suave is None or not tr.visible):
                    asignaciones[i] = d
                    break
    return asignaciones


# ─────────────────────────────────────────────────────────────
# 9. DETECTOR DE MOVIMIENTO GLOBAL (instancia unica) - V15 REAL
# ─────────────────────────────────────────────────────────────
_detector_movimiento = DetectorMovimiento(
    umbral_blur=35.0,
    umbral_movimiento=18.0,
    ventana_estabilidad=3
)

# Instancia global de estabilizador EIS
_estabilizador_eis = EstabilizadorEIS(suavizado=5, max_correccion=15.0)


# ─────────────────────────────────────────────────────────────
# 10. FUNCION PRINCIPAL DE PROCESAMIENTO - V15
# ─────────────────────────────────────────────────────────────

def ecualizar_clahe(frame):
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8,8))
    cl = clahe.apply(l)
    return cv2.cvtColor(cv2.merge((cl, a, b)), cv2.COLOR_LAB2BGR)

def procesar_frame_vision_yolo(frame, temporizadores, trackers, modelo_yolo,
                                cache_visual=None, callback_objeto=None, **kwargs):
    t_act       = time.time()
    hay_objetos = False
    fh, fw      = frame.shape[:2]

    cx_scr, cy_scr, radio_zona = get_zona_deteccion(frame.shape)
    detecciones_brutas = {'Rojo': [], 'Blanco': [], 'Negro': []}
    if cache_visual is not None:
        frame = cache_visual.aplicar_cache(frame)

    # V15: Estabilizacion electronica (EIS) ANTES de detectar
    frame = _estabilizador_eis.estabilizar(frame)

    # ── ANTI-GHOST: Si el frame es borroso o hay movimiento brusco,
    #    NO se ejecuta YOLO. Los trackers reciben None y se limpian solos.
    frame_estable = _detector_movimiento.frame_valido(frame)

    if frame_estable:
        # ── YOLO inference ───────────────────────────────────
        frame_clahe = ecualizar_clahe(frame)
        resultados = modelo_yolo.predict(frame_clahe, conf=0.38, verbose=False)

        if len(resultados) > 0:
            cajas = resultados[0].boxes
            if cajas is not None:
                for i in range(len(cajas)):
                    cls_id          = int(cajas.cls[i].item())
                    x1, y1, x2, y2 = cajas.xyxy[i].tolist()

                    nombre = None
                    if cls_id == 0: nombre = 'Rojo'
                    elif cls_id == 1: nombre = 'Blanco'
                    elif cls_id == 2: nombre = 'Negro'
                    if nombre is None: continue

                    cx = int((x1 + x2) / 2)
                    cy = int((y1 + y2) / 2)

                    # FILTRO ESPACIAL: centro debe estar DENTRO del circulo
                    if not dentro_del_circulo(cx, cy, cx_scr, cy_scr, radio_zona):
                        continue

                    if not es_forma_pelota(x1, y1, x2, y2, frame.shape):
                        continue

                    # V15: Validacion con umbrales diferenciados por color
                    if not validar_color_en_roi(frame, x1, y1, x2, y2, nombre):
                        continue

                    w     = x2 - x1
                    h     = y2 - y1
                    radio = int((w + h) / 4)
                    detecciones_brutas[nombre].append((cx, cy, radio))

        # ── NMS intra-color (eliminar duplicados mismo color) ─
        for nombre in detecciones_brutas:
            detecciones_brutas[nombre] = nms_mismo_color(
                detecciones_brutas[nombre], factor_radio=0.4
            )
    else:
        # Frame inestable: indicador visual
        cv2.putText(frame, "ESTABILIZANDO...", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)

    # ── Tracking y dibujado ──────────────────────────────────
    # V15: NEGRO PRIMERO (prioridad por peso de puntos: 5pts)
    total_pelotas = 0
    for nombre in ['Negro', 'Rojo', 'Blanco']:
        lista = sorted(detecciones_brutas[nombre],
                       key=lambda d: (d[1]//80, d[0]//80))
        if total_pelotas >= MAX_PELOTAS_TOTAL:
            lista = []
        else:
            lista = lista[:MAX_PELOTAS_TOTAL - total_pelotas]

        asignaciones = emparejar_detecciones(trackers[nombre], lista)

        for idx, det in enumerate(asignaciones):
            tr     = trackers[nombre][idx]
            result = tr.actualizar(det)
            if result is None:
                temporizadores[nombre][idx] = 0.0
                continue
            if total_pelotas >= MAX_PELOTAS_TOTAL: break

            hay_objetos    = True
            total_pelotas += 1
            cx, cy, r      = result
            if temporizadores[nombre][idx] == 0.0:
                temporizadores[nombre][idx] = t_act

            color_bgr = get_color_bgr(nombre)
            x_norm    = round(cx / fw * 2 - 1, 2)
            y_norm    = round(1 - cy / fh * 2, 2)
            z_est     = estimar_z_gp(r, frame.shape)

            cv2.circle(frame, (cx, cy), r, color_bgr, 3)
            cv2.circle(frame, (cx, cy), 4, color_bgr, -1)

            # V15: Logica de CALIBRACION (3 segundos)
            tiempo_detectado = t_act - temporizadores[nombre][idx]
            
            if tiempo_detectado <= TIEMPO_CALIBRACION:
                # Mostrar "Calibrando..." durante los primeros 3 segundos
                lbl_cal = 'Calibrando...'
                label_y = max(18, cy - r - 10)
                (tw, th), _ = cv2.getTextSize(lbl_cal, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(frame, (cx-r, label_y-th-4), (cx-r+tw+4, label_y+4), (20,20,20), -1)
                cv2.putText(frame, lbl_cal, (cx-r+2, label_y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_bgr, 1)
                # NO disparar callback durante calibracion
            else:
                # Mostrar etiqueta normal despues de calibracion
                lbl   = f'{nombre} #{idx+1}'
                lbl_c = f'X:{x_norm:+.1f} Y:{y_norm:+.1f} Z:{z_est}m'

                label_y     = max(18, cy - r - 10)
                (tw, th), _ = cv2.getTextSize(lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
                cv2.rectangle(frame, (cx-r, label_y-th-4), (cx-r+tw+4, label_y+4), (20,20,20), -1)
                cv2.putText(frame, lbl, (cx-r+2, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color_bgr, 2)

                # Disparar callback SOLO despues de calibracion
                if callback_objeto is not None:
                    callback_objeto(lbl, x_norm, y_norm, z_est)

    return frame, hay_objetos

print('Celda 3 V15 (Motor Definitivo) lista (Anti-Ghost + GP Depth + GP White + EIS + Circulo + NMS).')

HSV_RANGOS = {
    'Rojo': [(np.array([0, 50, 40]), np.array([12, 255, 255])),
             (np.array([160, 50, 40]), np.array([180, 255, 255]))],
    'Blanco': [(np.array([0, 0, 180]), np.array([180, 55, 255]))],
    'Negro': [(np.array([0, 0, 0]), np.array([180, 255, 75]))]
}

def escanear_malla_color(roi_img, mask_yolo, nombre_color, celdas=6):
    h, w = roi_img.shape[:2]
    paso_x, paso_y = max(1, w // celdas), max(1, h // celdas)
    hsv_img = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)
    
    celdas_buenas = []
    total_validas = 0
    
    for i in range(celdas):
        for j in range(celdas):
            x1, x2 = j*paso_x, (j+1)*paso_x
            y1, y2 = i*paso_y, (i+1)*paso_y
            
            mask_celda = mask_yolo[y1:y2, x1:x2]
            area_celda = paso_x * paso_y
            if area_celda == 0 or cv2.countNonZero(mask_celda) < (area_celda * 0.4): continue
            
            total_validas += 1
            hsv_celda = hsv_img[y1:y2, x1:x2]
            match = False
            for lo, hi in HSV_RANGOS.get(nombre_color, []):
                mask_c = cv2.inRange(hsv_celda, lo, hi)
                if cv2.countNonZero(cv2.bitwise_and(mask_c, mask_celda)) > (cv2.countNonZero(mask_celda) * 0.4):
                    match = True; break
            
            if match: celdas_buenas.append((x1, y1, x2, y2))
            
    ratio = (len(celdas_buenas) / total_validas) if total_validas > 0 else 0
    return celdas_buenas, ratio

def estimar_z_basico(radio_px, frame_shape):
    frac = (math.pi * radio_px * radio_px) / (frame_shape[0] * frame_shape[1])
    return round(max(0.1, min(5.0, 1.0 / (frac * 10 + 0.01))), 2)

def procesar_frame_avanzado(frame_original, yolo, callback=None):
    frame_clahe = ecualizar_clahe(frame_original)
    fh, fw = frame_original.shape[:2]
    cx_s, cy_s, rad_z = fw//2, fh//2, int(min(fw, fh)*0.38)
    
    res = yolo.predict(frame_clahe, conf=0.38, verbose=False)
    mask_ignore = np.zeros((fh, fw), dtype=np.uint8)
    objetos_brutos = []
    
    if res and res[0].boxes is not None:
        tiene_mascaras = (res[0].masks is not None)
        for i in range(len(res[0].boxes)):
            x1, y1, x2, y2 = res[0].boxes.xyxy[i].tolist()
            cid = int(res[0].boxes.cls[i].item())
            conf = float(res[0].boxes.conf[i].item())
            nm = 'Rojo' if cid==0 else 'Blanco' if cid==1 else 'Negro'
            cx, cy = int((x1+x2)/2), int((y1+y2)/2)
            
            if math.hypot(cx-cx_s, cy-cy_s) > rad_z: continue
            
            roi_img = frame_clahe[int(y1):int(y2), int(x1):int(x2)]
            mask_yolo = None
            circularidad = 0.0
            
            if tiene_mascaras and len(res[0].masks.xy) > i:
                poly = res[0].masks.xy[i]
                if len(poly) >= 3:
                    poly_roi = (np.array(poly) - [x1, y1]).astype(np.int32)
                    area = cv2.contourArea(poly_roi)
                    perim = cv2.arcLength(poly_roi, True)
                    circularidad = (4 * math.pi * area) / (perim * perim) if perim > 0 else 0.0
                    roi_h, roi_w = roi_img.shape[:2]
                    mask_yolo = np.zeros((roi_h, roi_w), dtype=np.uint8)
                    cv2.fillPoly(mask_yolo, [poly_roi], 255)
                    cv2.fillPoly(mask_ignore, [poly.astype(np.int32)], 255)
            
            if mask_yolo is None: continue
            # V15: Circularidad mas estricta para blanco
            if nm == 'Blanco' and circularidad < 0.72: continue
            
            celdas_aprobadas, ratio_malla = escanear_malla_color(roi_img, mask_yolo, nm, celdas=6)
            if ratio_malla < 0.35: continue
            
            objetos_brutos.append({
                'nombre': nm, 'cx': cx, 'cy': cy, 'r': int((x2-x1+y2-y1)/4),
                'x1': int(x1), 'y1': int(y1), 'x2': int(x2), 'y2': int(y2),
                'conf': conf, 'celdas': celdas_aprobadas, 'circ': circularidad
            })

    objetos_brutos.sort(key=lambda o: o['conf'], reverse=True)
    objetos_finales = []
    for obj in objetos_brutos:
        colision = False
        for aceptado in objetos_finales:
            if math.hypot(obj['cx'] - aceptado['cx'], obj['cy'] - aceptado['cy']) < (obj['r'] + aceptado['r']) * 0.6:
                colision = True; break
        if not colision: objetos_finales.append(obj)

    # DIBUJO DE MIRA ACTIVA (CUADRADO + CRUZ + CIRCULO)
    cv2.rectangle(frame_original, (cx_s - rad_z, cy_s - rad_z), (cx_s + rad_z, cy_s + rad_z), (255,255,255), 1)
    cv2.circle(frame_original, (cx_s, cy_s), rad_z, (255,255,255), 1)
    cv2.line(frame_original, (cx_s - rad_z, cy_s), (cx_s + rad_z, cy_s), (255,255,255), 1)
    cv2.line(frame_original, (cx_s, cy_s - rad_z), (cx_s, cy_s + rad_z), (255,255,255), 1)
    
    for obj in objetos_finales:
        nm = obj['nombre']
        c_bgr = get_color_bgr(nm)
        lbl = f"{nm}"
        
        cv2.circle(frame_original, (obj['cx'], obj['cy']), obj['r'], c_bgr, 3)
        ly = max(18, obj['y1'] - 10)
        cv2.putText(frame_original, lbl, (obj['cx'] - obj['r'], ly), cv2.FONT_HERSHEY_SIMPLEX, 0.4, c_bgr, 2)
                
        if callback: callback(lbl, 0, 0, estimar_z_basico(obj['r'], frame_original.shape))

    return frame_original, len(objetos_finales) > 0

# Celda 3 - UI Auto-Connect USB  [V15]
import customtkinter as ctk
from PIL import Image
import threading

class EscanerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title('Deteccion de Carga - V15 (Auto USB)')
        self.geometry('1380x860')
        self.configure(fg_color='#1a1d2e')
        
        self.cap = None
        self.escaneando = False
        self.cache_visual = FrameQualityCache(history_size=3)
        self._cam_idx_activa = -1  # indice de camara actualmente abierta
        
        self.trackers = {
            'Rojo': [TrackerCirculo() for _ in range(LIMITES_PELOTAS['Rojo'])],
            'Blanco': [TrackerCirculo() for _ in range(LIMITES_PELOTAS['Blanco'])],
            'Negro': [TrackerCirculo() for _ in range(LIMITES_PELOTAS['Negro'])]
        }
        self.temporizadores = {
            'Rojo': [0.0]*LIMITES_PELOTAS['Rojo'],
            'Blanco': [0.0]*LIMITES_PELOTAS['Blanco'],
            'Negro': [0.0]*LIMITES_PELOTAS['Negro']
        }
        self.historial_objetos = set()
        self.puntos_actuales = 0
        self.limite_alcanzado = False
        
        self.cam_delay_ms = 33

        ruta_modelo = r"C:\Users\jrhe0\.gemini\antigravity-ide\scratch\detector_pelotas\models\entrenamiento_pelotas\weights\best.pt"
        if os.path.exists(ruta_modelo):
            print("Cargando modelo de IA (YOLOv8)...")
            self.modelo_yolo = YOLO(ruta_modelo)
        else:
            print("ERROR: No se encontro el modelo YOLO en " + ruta_modelo)
            self.modelo_yolo = None
        self._construir_ui()
        # Ir directo a la vista de video (sin pantalla de seleccion)
        self.panel_video.pack(expand=True, fill='both')
        self.lbl_titulo.configure(text='ESPERANDO CAMARA USB...')
        self.lbl_video.configure(
            text='Conecta tu celular por USB\npara iniciar la detección',
            text_color='#f1c40f',
            font=('Helvetica', 20, 'bold')
        )
        # Empezar a buscar camaras inmediatamente
        self._buscar_y_conectar()

    def _construir_ui(self):
        self.lbl_titulo = ctk.CTkLabel(self, text='', font=('Helvetica', 22, 'bold'), text_color='#e8eaf0')
        self.lbl_titulo.pack(pady=(28, 12))
        
        # Panel de video (unico panel, sin panel_config)
        self.panel_video = ctk.CTkFrame(self, fg_color='transparent')
        self.lbl_video = ctk.CTkLabel(self.panel_video, text='')
        self.lbl_video.pack(pady=10, padx=10)
        
        self.frame_controles = ctk.CTkFrame(self.panel_video, fg_color='transparent')
        self.frame_controles.pack(pady=8)
        
        self.btn_escaneo = ctk.CTkButton(self.frame_controles, text='Pausar Escaneo', fg_color='#d35400', command=self._toggle_escaneo)
        self.btn_escaneo.grid(row=0, column=0, padx=10)
        
        self.btn_limpiar = ctk.CTkButton(self.frame_controles, text='Limpiar Todo', command=self._limpiar_todo)
        self.btn_limpiar.grid(row=0, column=1, padx=10)
        
        self.lbl_puntos = ctk.CTkLabel(self.frame_controles, text='Puntos: 0 / 10 MAX', font=('Helvetica', 16, 'bold'), text_color='#3498db')
        self.lbl_puntos.grid(row=0, column=2, padx=20)
        
        self.lbl_gp_status = ctk.CTkLabel(self.panel_video, text='', text_color='#f1c40f', font=('Helvetica', 14, 'bold'))
        self.lbl_gp_status.pack(pady=5)

        self.lista_scroll = ctk.CTkScrollableFrame(self.panel_video, width=300)
        self.lista_scroll.pack(side='right', fill='y', padx=10, pady=10)

    # ── AUTO-DETECCION USB ─────────────────────────────────
    def _buscar_y_conectar(self):
        """Busca camaras USB. Si encuentra una, la abre y empieza a detectar."""
        # Si ya hay camara abierta y funcionando, solo vigilar desconexion
        if self.cap is not None and self.cap.isOpened():
            ret, _ = self.cap.read()
            if ret:
                # Camara sigue viva, revisar de nuevo en 2s
                self.after(2000, self._buscar_y_conectar)
                return
            else:
                # Camara desconectada
                print('Camara USB desconectada.')
                self.cap.release()
                self.cap = None
                self._cam_idx_activa = -1
                self.escaneando = False
                self.lbl_titulo.configure(text='CAMARA DESCONECTADA')
                self.lbl_video.configure(
                    text='Reconecta tu celular por USB\npara reanudar la detección',
                    text_color='#e74c3c',
                    font=('Helvetica', 20, 'bold')
                )
        
        # Buscar camaras disponibles
        camaras = detectar_camaras_sistema()
        
        if camaras:
            # Tomar la primera camara disponible (tipicamente el celular USB)
            idx, nombre = camaras[0]
            print(f'Camara USB detectada: [{idx}] {nombre}')
            
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            if not cap.isOpened() or not cap.read()[0]:
                cap.release()
                cap = cv2.VideoCapture(idx)
            
            if cap.isOpened():
                # Maximizar calidad de camara
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                cap.set(cv2.CAP_PROP_FPS, 30)
                cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
                cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                
                real_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                real_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                real_fps = int(cap.get(cv2.CAP_PROP_FPS))
                print(f'V15 Camara: {real_w}x{real_h} @ {real_fps}fps')
                
                self.cap = cap
                self._cam_idx_activa = idx
                self.escaneando = True  # Auto-iniciar escaneo
                self.cache_visual = FrameQualityCache(history_size=3)
                
                self.lbl_titulo.configure(text=f'DETECTANDO - {nombre}')
                self.lbl_video.configure(text='', font=('Helvetica', 12))
                self.btn_escaneo.configure(text='Pausar Escaneo', fg_color='#d35400')
                
                self._loop_video()
                # Seguir vigilando desconexion
                self.after(2000, self._buscar_y_conectar)
                return
        
        # No se encontro camara, reintentar en 1.5s
        self.after(1500, self._buscar_y_conectar)

    def _toggle_escaneo(self):
        self.escaneando = not self.escaneando
        if self.escaneando:
            self.btn_escaneo.configure(text='Pausar Escaneo', fg_color='#d35400')
        else:
            self.btn_escaneo.configure(text='Reanudar Escaneo', fg_color='#f39c12')

    def _loop_video(self):
        if not self.cap or not self.cap.isOpened(): return
        
        ret, frame = self.cap.read()
        if not ret:
            # Frame perdido, la vigilancia de _buscar_y_conectar manejara la reconexion
            self.after(self.cam_delay_ms, self._loop_video)
            return
        
        frame = cv2.flip(frame, 1)
        # ── RETICULA SIEMPRE VISIBLE ──────────────────────
        dibujar_reticula(frame)
        # ── Deteccion AUTOMATICA (siempre activa si escaneando) ─
        if self.escaneando and not self.limite_alcanzado:
            if self.modelo_yolo is not None:
                frame, _ = procesar_frame_vision_yolo(
                    frame, self.temporizadores, self.trackers, self.modelo_yolo,
                    cache_visual=self.cache_visual,
                    callback_objeto=self.on_objeto_detectado
                )
            else:
                cv2.putText(frame, "ERROR: YOLO NO CARGADO", (50, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        
        img = ctk.CTkImage(
            light_image=Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)),
            size=(1024, 700)
        )
        self.lbl_video.configure(image=img)
        
        self.after(self.cam_delay_ms, self._loop_video)

    def on_objeto_detectado(self, lbl_nombre, x, y, z):
        if self.limite_alcanzado: return
        
        if lbl_nombre not in self.historial_objetos:
            pts = 0
            if 'Negro' in lbl_nombre: pts = 5
            elif 'Blanco' in lbl_nombre: pts = 3
            elif 'Rojo' in lbl_nombre: pts = 1
            
            if self.puntos_actuales + pts > 10:
                self.historial_objetos.add(lbl_nombre)
                self.puntos_actuales += pts
                self.limite_alcanzado = True
                self.escaneando = False
                ctk.CTkLabel(self.lista_scroll, text=f"{lbl_nombre} (+{pts} pts) -> ¡LIMITE!").pack()
                self.lbl_puntos.configure(text=f'Puntos: {self.puntos_actuales} / 10 MAX', text_color='red')
                self.btn_escaneo.configure(text='Límite Alcanzado', state='disabled', fg_color='#7f8c8d')
                self.lbl_gp_status.configure(text=f'¡CANASTA LLENA! ({self.puntos_actuales} pts detectados)', text_color='red')
                return

            self.historial_objetos.add(lbl_nombre)
            self.puntos_actuales += pts
            ctk.CTkLabel(self.lista_scroll, text=f"{lbl_nombre} (+{pts} pts)").pack()
            self.lbl_puntos.configure(text=f'Puntos: {self.puntos_actuales} / 10 MAX')
            
            if self.puntos_actuales == 10:
                self.limite_alcanzado = True
                self.escaneando = False
                self.btn_escaneo.configure(text='Límite Alcanzado', state='disabled', fg_color='#7f8c8d')
                self.lbl_gp_status.configure(text=f'¡CANASTA LLENA! (10 pts)', text_color='red')
                self.lbl_puntos.configure(text_color='red')

    def _limpiar_todo(self):
        for w in self.lista_scroll.winfo_children(): w.destroy()
        self.historial_objetos.clear()
        self.puntos_actuales = 0
        self.limite_alcanzado = False
        self.lbl_puntos.configure(text='Puntos: 0 / 10 MAX', text_color='#3498db')
        self.lbl_gp_status.configure(text='')
        self.btn_escaneo.configure(state='normal', text='Pausar Escaneo' if self.escaneando else 'Reanudar Escaneo',
                                    fg_color='#d35400' if self.escaneando else '#f39c12')
        for c in self.temporizadores: self.temporizadores[c] = [0.0]*LIMITES_PELOTAS[c]
        for c in self.trackers: 
            for tr in self.trackers[c]: tr.reiniciar()

print('Celda 4 V15 lista.')

# Celda 5 - Punto de entrada  [V15]
if __name__ == '__main__':
    app = EscanerApp()
    app.mainloop()