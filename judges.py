import json
from config import JUDGES_FILE, MAX_PARTICIPANTES, judges_lock

# Cache en memoria de los jueces
judges_cache: dict = {}
OBSOLETE_SCORE_FIELDS = {
    "cantidad_checkpoints_ponderados_visitados",
    "puntuacion_checkpoints",
    "puntaje_checkpoints",
    "checkpoints_puntos_entregados",
    "puntos_totales",
    "peso",
    "puntaje_equipo",
}


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------

def load_judges() -> dict:
    try:
        with open(JUDGES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def save_judges(judges: dict) -> None:
    with open(JUDGES_FILE, "w", encoding="utf-8") as f:
        json.dump(judges, f, indent=2)


def reset_judges() -> None:
    """Reinicia los jueces al levantar el servidor."""
    pass


# ---------------------------------------------------------------------------
# Migración de formato antiguo
# ---------------------------------------------------------------------------

def _migrar_judges_si_necesario() -> None:
    """Convierte el formato viejo {device_id: 'nombre'} al nuevo {device_id: {nombre: ...}}."""
    cambiado = False
    for device_id, value in list(judges_cache.items()):
        if isinstance(value, str):
            judges_cache[device_id] = {"nombre": value}
            cambiado = True
            continue
        if isinstance(value, dict):
            for field in OBSOLETE_SCORE_FIELDS:
                if field in value:
                    del value[field]
                    cambiado = True
    if cambiado:
        save_judges(judges_cache)


# ---------------------------------------------------------------------------
# Lógica de negocio
# ---------------------------------------------------------------------------

def get_or_create_judge(device_id: str) -> str | None:
    if not device_id:
        return None

    if device_id in judges_cache:
        return judges_cache[device_id]["nombre"]

    if len(judges_cache) >= MAX_PARTICIPANTES:
        return None

    nombre = f"Judge_{len(judges_cache) + 1}"
    judges_cache[device_id] = {"nombre": nombre}
    save_judges(judges_cache)
    return nombre


# ---------------------------------------------------------------------------
# Inicialización al importar
# ---------------------------------------------------------------------------

judges_cache.update(load_judges())
_migrar_judges_si_necesario()
