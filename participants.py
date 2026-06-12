import json
from config import PARTICIPANTS_FILE, MAX_PARTICIPANTES, participants_lock


# Cache en memoria de los participantes
participants_cache: dict = {}


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
    if cambiado:
        save_participants(participants_cache)


# ---------------------------------------------------------------------------
# Lógica de negocio
# ---------------------------------------------------------------------------

def get_or_create_participant(device_id: str) -> str | None:
    if not device_id:
        return None

    if device_id in participants_cache:
        return participants_cache[device_id]["nombre"]

    if len(participants_cache) >= MAX_PARTICIPANTES:
        return None

    nombre = f"participante_{len(participants_cache) + 1:02d}"
    participants_cache[device_id] = {"nombre": nombre}
    save_participants(participants_cache)
    return nombre


# ---------------------------------------------------------------------------
# Inicialización al importar
# ---------------------------------------------------------------------------

participants_cache.update(load_participants())
_migrar_participantes_si_necesario()
