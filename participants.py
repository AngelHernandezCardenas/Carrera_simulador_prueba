import json

from config import MAX_PARTICIPANTES, PARTICIPANTS_FILE


participants_cache: dict = {}


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
    participants_cache.clear()
    save_participants(participants_cache)


def _migrar_participantes_si_necesario() -> None:
    """Convierte el formato viejo {device_id: 'nombre'} al nuevo {device_id: {nombre: ...}}."""
    cambiado = False
    for device_id, value in list(participants_cache.items()):
        if isinstance(value, str):
            participants_cache[device_id] = {"nombre": value}
            cambiado = True
    if cambiado:
        save_participants(participants_cache)


def get_or_create_participant(device_id: str) -> str | None:
    if not device_id:
        return None

    if device_id in participants_cache:
        return participants_cache[device_id]["nombre"]

    if len(participants_cache) >= MAX_PARTICIPANTES:
        return None

    nombre = f"participante_{len(participants_cache) + 1:02d}"
    # TODO: BORRAR ESTO DESPUES. Peso inicial temporal solo para pruebas.
    participants_cache[device_id] = {"nombre": nombre, "peso": 9.0}
    save_participants(participants_cache)
    return nombre


participants_cache.update(load_participants())
_migrar_participantes_si_necesario()
