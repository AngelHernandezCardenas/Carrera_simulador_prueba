from config import PARTICIPANTS_FILE, MAX_PARTICIPANTES, participants_lock
from judges import judges_cache

# Cache en memoria de los participantes
participants_cache: dict = {}
OBSOLETE_SCORE_FIELDS = {
    "cantidad_checkpoints_ponderados_visitados",
    "puntuacion_checkpoints",
    "puntaje_checkpoints",
    "checkpoints_puntos_entregados",
    "puntos_totales",
    "peso",
    "puntaje_equipo",
}


import json

# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------

def load_participants() -> dict:
    try:
        with open(PARTICIPANTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def save_participants(participants: dict) -> None:
    with open(PARTICIPANTS_FILE, "w", encoding="utf-8") as f:
        json.dump(participants, f, indent=2)


def reset_participants() -> None:
    """Reinicia los participantes al levantar el servidor."""
    # Desactivamos la limpieza para no perder a los usuarios.
    pass


# ---------------------------------------------------------------------------
# Migración de formato antiguo
# ---------------------------------------------------------------------------

def _migrar_participantes_si_necesario() -> None:
    """Convierte el formato viejo {device_id: 'nombre'} al nuevo {device_id: {nombre: ...}}."""
    cambiado = False
    for device_id, value in list(participants_cache.items()):
        if isinstance(value, str):
            participants_cache[device_id] = {"nombre": value}
            cambiado = True
            continue
        if isinstance(value, dict):
            for field in OBSOLETE_SCORE_FIELDS:
                if field in value:
                    del value[field]
                    cambiado = True
    if cambiado:
        save_participants(participants_cache)


# ---------------------------------------------------------------------------
# Lógica de negocio
# ---------------------------------------------------------------------------

def get_or_create_participant(device_id: str) -> str | None:
    if not device_id:
        return None

    if device_id in participants_cache:
        nombre = participants_cache[device_id]["nombre"]
        if "Judge" not in nombre and "Juez" not in nombre:
            return nombre

    if len(participants_cache) >= MAX_PARTICIPANTES:
        return None

    # Avoid collisions with existing names by finding the next available slot
    slot = len(participants_cache) + 1
    nombre = f"participante_{slot:02d}"
    while any(p.get("nombre") == nombre for p in participants_cache.values()):
        slot += 1
        nombre = f"participante_{slot:02d}"

    participants_cache[device_id] = {"nombre": nombre}
    save_participants(participants_cache)
    return nombre


# ---------------------------------------------------------------------------
# Inicialización al importar
# ---------------------------------------------------------------------------

participants_cache.update(load_participants())
_migrar_participantes_si_necesario()
