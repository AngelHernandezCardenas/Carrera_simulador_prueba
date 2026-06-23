"""
gp_vision_optimizer.py
──────────────────────
Optimizador GP liviano para maximizar FPS del pipeline de visión.
Adaptado de gp_mochila_optimizado.py — sin DEAP, sin generaciones,
solo mutación aleatoria + selección por torneo en tiempo real.
"""
import random
import time
import copy


# ── Rangos válidos para cada parámetro ────────────────────────────────────────
PARAM_RANGES = {
    'blur_k':         (3, 7, 2),      # min, max, step (impares)
    'morph_open_k':   (3, 7, 2),
    'morph_close_k':  (5, 9, 2),
    'area_min_frac':  (0.003, 0.010),  # float continuo
    'jpeg_quality':   (30, 80, 5),
    'max_width':      (320, 1280, 80),
}

# Valores iniciales conservadores (ya probados)
DEFAULT_PARAMS = {
    'blur_k':        5,
    'morph_open_k':  5,
    'morph_close_k': 7,
    'area_min_frac': 0.005,
    'jpeg_quality':  65,
    'max_width':     1280,
}


def _clamp(val, lo, hi):
    return max(lo, min(hi, val))


def _rand_param(key):
    """Genera un valor aleatorio válido para el parámetro dado."""
    r = PARAM_RANGES[key]
    if key == 'area_min_frac':
        return round(random.uniform(r[0], r[1]), 4)
    lo, hi, step = r
    opciones = list(range(lo, hi + 1, step))
    return random.choice(opciones)


def _mutar_param(key, val):
    """Muta un solo parámetro con perturbación pequeña."""
    r = PARAM_RANGES[key]
    if key == 'area_min_frac':
        delta = random.uniform(-0.002, 0.002)
        return round(_clamp(val + delta, r[0], r[1]), 4)
    lo, hi, step = r
    opciones = list(range(lo, hi + 1, step))
    idx = opciones.index(val) if val in opciones else len(opciones) // 2
    # Mover ±1 posición
    nuevo_idx = _clamp(idx + random.choice([-1, 0, 1]), 0, len(opciones) - 1)
    return opciones[nuevo_idx]


class Individuo:
    """Un candidato de parámetros con su fitness (FPS medido)."""
    __slots__ = ('params', 'fitness', 'muestras')

    def __init__(self, params=None):
        self.params   = params or {k: _rand_param(k) for k in PARAM_RANGES}
        self.fitness  = 0.0
        self.muestras = 0

    def clonar(self):
        nuevo = Individuo(copy.deepcopy(self.params))
        nuevo.fitness  = self.fitness
        nuevo.muestras = self.muestras
        return nuevo


class GPVisionOptimizer:
    """
    Optimizador GP liviano para parámetros de visión.

    Uso:
        opt = GPVisionOptimizer()
        params = opt.obtener_params()      # dict con blur_k, etc.
        # ... procesar frame con esos params ...
        opt.reportar_tiempo(elapsed_ms)    # reportar latencia del frame
    """

    def __init__(self, pool_size=6, frames_por_eval=8):
        self.pool_size      = pool_size
        self.frames_por_eval = frames_por_eval

        # Crear pool inicial con el default + variantes aleatorias
        self.pool = [Individuo(copy.deepcopy(DEFAULT_PARAMS))]
        while len(self.pool) < pool_size:
            self.pool.append(Individuo())

        self.activo_idx      = 0
        self.frame_count     = 0
        self.acum_tiempo_ms  = 0.0
        self.mejor_global    = self.pool[0].clonar()

    def obtener_params(self):
        """Retorna los parámetros del individuo activo."""
        return self.pool[self.activo_idx].params

    def reportar_tiempo(self, elapsed_ms):
        """
        Reporta el tiempo de procesamiento de un frame (ms).
        Cada `frames_por_eval` frames, evalúa el fitness y avanza al siguiente.
        """
        self.frame_count    += 1
        self.acum_tiempo_ms += elapsed_ms

        if self.frame_count >= self.frames_por_eval:
            # Calcular FPS promedio como fitness
            avg_ms = self.acum_tiempo_ms / self.frame_count
            fps    = 1000.0 / max(avg_ms, 1.0)

            ind = self.pool[self.activo_idx]
            # Media móvil exponencial del fitness
            if ind.muestras == 0:
                ind.fitness = fps
            else:
                ind.fitness = 0.6 * fps + 0.4 * ind.fitness
            ind.muestras += 1

            # Actualizar mejor global
            if ind.fitness > self.mejor_global.fitness:
                self.mejor_global = ind.clonar()

            # Avanzar al siguiente individuo
            self.activo_idx = (self.activo_idx + 1) % self.pool_size

            # Cada ronda completa → evolucionar
            if self.activo_idx == 0:
                self._evolucionar()

            # Reset contadores
            self.frame_count    = 0
            self.acum_tiempo_ms = 0.0

    def _evolucionar(self):
        """
        Evolución simplificada: torneo + mutación.
        - Ordena por fitness descendente
        - Mantiene la mitad superior
        - Reemplaza la mitad inferior con mutaciones de los mejores
        """
        # Ordenar por fitness (mayor = mejor)
        self.pool.sort(key=lambda x: x.fitness, reverse=True)

        mitad = self.pool_size // 2

        for i in range(mitad, self.pool_size):
            # Seleccionar un padre al azar de la mitad superior
            padre = random.choice(self.pool[:mitad])
            hijo  = padre.clonar()

            # Mutar 1-3 parámetros al azar
            n_muts = random.randint(1, 3)
            keys   = random.sample(list(hijo.params.keys()), min(n_muts, len(hijo.params)))
            for k in keys:
                hijo.params[k] = _mutar_param(k, hijo.params[k])

            hijo.fitness  = padre.fitness * 0.9  # herencia parcial
            hijo.muestras = 0
            self.pool[i]  = hijo

    def obtener_stats(self):
        """Retorna estadísticas del optimizador para debug."""
        mejor = max(self.pool, key=lambda x: x.fitness)
        return {
            'mejor_fps':    round(mejor.fitness, 1),
            'mejor_params': mejor.params,
            'global_fps':   round(self.mejor_global.fitness, 1),
        }
