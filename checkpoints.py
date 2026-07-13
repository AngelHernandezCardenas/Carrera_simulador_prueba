import math


# ---------------------------------------------------------------------------
# EDITA AQUI TUS CHECKPOINTS
# ---------------------------------------------------------------------------
# Cambia lat/lon por las coordenadas reales de tu carrera.
# radio_m es el radio de deteccion en metros para marcar el checkpoint.
CHECKPOINTS = [
    #SON PARA HACER PRUEBAS DE CARRERA REAL, PARA IR A COMER SERA UNA LINEA RECTA
    #lirucisa
    {"id": 1, "nombre": "Biotecnologia-Centrales", "lat": 25.651133, "lon": -100.288352, "radio_m": 5.0},
    #esquina de bilbio entre biblio y aulas 4
    {"id": 2, "nombre": "Bilio-Aulas4", "lat": 25.6505742, "lon": -100.2903096, "radio_m": 5.0},
    {"id": "Home-Base", "nombre": "Rectoria-Descarga", "lat": 25.651464, "lon": -100.291149, "radio_m": 5.0},
]

MAX_PERSONAS_POR_CHECKPOINT = 4
UNLIMITED_OCCUPANCY_CHECKPOINT_IDS = {99, "Home-Base"}
CHECKPOINT_DESCARGA_ID = 99

def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula distancia entre dos coordenadas GPS usando Haversine."""
    earth_radius_m = 6371000.0

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_m * c


def _checkpoint_id(checkpoint: dict) -> int:
    cid = checkpoint["id"]
    if str(cid).lower() == "home-base" or "home" in str(cid).lower():
        return 99
    return int(cid)


def _checkpoint_name(checkpoint: dict) -> str:
    checkpoint_id = _checkpoint_id(checkpoint)
    return checkpoint.get("nombre") or f"Checkpoint {checkpoint_id}"


def _sorted_checkpoint_ids(checkpoint_ids) -> list[int]:
    def safe_int(cid):
        if str(cid).lower() == "home-base" or "home" in str(cid).lower():
            return 99
        return int(cid)
    return sorted(safe_int(checkpoint_id) for checkpoint_id in checkpoint_ids)


def _nearest_checkpoint(lat: float, lon: float, checkpoints: list[dict]) -> tuple[dict | None, float]:
    if not checkpoints:
        return None, 0.0

    nearest = min(
        checkpoints,
        key=lambda checkpoint: haversine_distance_m(
            lat,
            lon,
            float(checkpoint["lat"]),
            float(checkpoint["lon"]),
        ),
    )
    distance = haversine_distance_m(lat, lon, float(nearest["lat"]), float(nearest["lon"]))
    return nearest, distance


def _checkpoint_occupancy_by_id(
    corredores: dict | None,
    checkpoints: list[dict],
    corredor_actual: dict | None = None,
) -> dict[int, int]:
    occupancy = {_checkpoint_id(checkpoint): 0 for checkpoint in checkpoints}

    if not corredores:
        return occupancy

    for corredor in corredores.values():
        if corredor is corredor_actual:
            continue

        last_coord = corredor.get("last_coord")
        if not last_coord or len(last_coord) < 2:
            continue

        try:
            lat, lon = float(last_coord[0]), float(last_coord[1])
        except (TypeError, ValueError):
            continue

        for checkpoint in checkpoints:
            checkpoint_id = _checkpoint_id(checkpoint)
            distance = haversine_distance_m(
                lat,
                lon,
                float(checkpoint["lat"]),
                float(checkpoint["lon"]),
            )
            if distance <= float(checkpoint.get("radio_m", 5.0)):
                occupancy[checkpoint_id] += 1

    return occupancy


def _full_checkpoint_ids(
    corredores: dict | None,
    checkpoints: list[dict],
    corredor_actual: dict | None = None,
) -> set[int]:
    occupancy = _checkpoint_occupancy_by_id(corredores, checkpoints, corredor_actual)
    return {
        checkpoint_id
        for checkpoint_id, count in occupancy.items()
        if count >= MAX_PERSONAS_POR_CHECKPOINT
        and checkpoint_id not in UNLIMITED_OCCUPANCY_CHECKPOINT_IDS
    }


def _full_checkpoint_ids_with_current_position(
    corredores: dict | None,
    checkpoints: list[dict],
    corredor_actual: dict,
    lat: float,
    lon: float,
) -> set[int]:
    occupancy = _checkpoint_occupancy_by_id(corredores, checkpoints, corredor_actual)

    for checkpoint in checkpoints:
        checkpoint_id = _checkpoint_id(checkpoint)
        distance = haversine_distance_m(
            lat,
            lon,
            float(checkpoint["lat"]),
            float(checkpoint["lon"]),
        )
        if distance <= float(checkpoint.get("radio_m", 5.0)):
            occupancy[checkpoint_id] += 1

    return {
        checkpoint_id
        for checkpoint_id, count in occupancy.items()
        if count >= MAX_PERSONAS_POR_CHECKPOINT
        and checkpoint_id not in UNLIMITED_OCCUPANCY_CHECKPOINT_IDS
    }


def _nearest_pending_checkpoint(
    lat: float,
    lon: float,
    visited_ids: set[int],
    checkpoints: list[dict],
    unavailable_ids: set[int] | None = None,
) -> tuple[dict | None, float]:
    unavailable_ids = unavailable_ids or set()
    pending = [
        checkpoint
        for checkpoint in checkpoints
        if _checkpoint_id(checkpoint) not in visited_ids
        and _checkpoint_id(checkpoint) not in unavailable_ids
    ]

    if not pending:
        return None, 0.0

    return _nearest_checkpoint(lat, lon, pending)


def actualizar_estado_corredor(
    corredor: dict,
    lat: float,
    lon: float,
    checkpoints: list[dict] | None = None,
    corredores: dict | None = None,
) -> dict:
    """
    Actualiza el estado de un corredor sin usar orden fijo.
    Si entra al radio de cualquier checkpoint pendiente, se marca como visitado.
    """
    checkpoints = checkpoints or CHECKPOINTS
    visited_ids = set(_sorted_checkpoint_ids(corredor.get("checkpoints_visitados", [])))
    full_checkpoint_ids_for_visits = _full_checkpoint_ids(corredores, checkpoints, corredor)
    full_checkpoint_ids_for_display = _full_checkpoint_ids_with_current_position(
        corredores,
        checkpoints,
        corredor,
        lat,
        lon,
    )

    # /api/score persiste las calificaciones en "scores". Se conserva el
    # fallback para aceptar estados antiguos que usaban "scores_dict".
    scores_dict = corredor.get("scores", corredor.get("scores_dict", {}))
    blocked_by_challenge = False
    for cid in visited_ids:
        if cid == CHECKPOINT_DESCARGA_ID:
            continue
        if str(cid) not in scores_dict and cid not in scores_dict:
            blocked_by_challenge = True
            break
            
    if not blocked_by_challenge:
        for checkpoint in checkpoints:
            checkpoint_id = _checkpoint_id(checkpoint)
            if checkpoint_id in visited_ids:
                continue
            if checkpoint_id in full_checkpoint_ids_for_visits:
                continue

            distance = haversine_distance_m(
                lat,
                lon,
                float(checkpoint["lat"]),
                float(checkpoint["lon"]),
            )
            if distance <= float(checkpoint.get("radio_m", 5.0)):
                visited_ids.add(checkpoint_id)

    available_checkpoints = [
        checkpoint
        for checkpoint in checkpoints
        if _checkpoint_id(checkpoint) not in full_checkpoint_ids_for_display
    ]
    nearest_checkpoint, closest_checkpoint_distance = _nearest_checkpoint(
        lat,
        lon,
        available_checkpoints,
    )
    nearest_pending, nearest_distance = _nearest_pending_checkpoint(
        lat,
        lon,
        visited_ids,
        checkpoints,
        full_checkpoint_ids_for_display,
    )
    visited_count = len(visited_ids)
    required_checkpoint_ids = {_checkpoint_id(checkpoint) for checkpoint in checkpoints}
    all_required_visited = required_checkpoint_ids.issubset(visited_ids)

    corredor["checkpoints_visitados"] = _sorted_checkpoint_ids(visited_ids)
    corredor["cantidad_checkpoints_visitados"] = visited_count
    corredor["checkpoint_descarga_visitado"] = CHECKPOINT_DESCARGA_ID in visited_ids
    corredor["blocked_by_challenge"] = blocked_by_challenge
    corredor["checkpoint_pendiente_mas_cercano"] = (
        None
        if nearest_pending is None
        else {
            "id": _checkpoint_id(nearest_pending),
            "nombre": _checkpoint_name(nearest_pending),
        }
    )
    corredor["checkpoint_pendiente_mas_cercano_id"] = (
        None if nearest_pending is None else _checkpoint_id(nearest_pending)
    )
    corredor["distancia_checkpoint_pendiente_mas_cercano_m"] = round(nearest_distance, 2)
    corredor["checkpoint_mas_cercano"] = (
        None
        if nearest_checkpoint is None
        else {
            "id": _checkpoint_id(nearest_checkpoint),
            "nombre": _checkpoint_name(nearest_checkpoint),
        }
    )
    corredor["checkpoint_mas_cercano_id"] = (
        None if nearest_checkpoint is None else _checkpoint_id(nearest_checkpoint)
    )
    corredor["distancia_checkpoint_mas_cercano_m"] = round(closest_checkpoint_distance, 2)
    corredor["estado"] = "terminado" if all_required_visited else "corriendo"

    return corredor


def clasificar_corredores(corredores: dict) -> list[dict]:
    """
    Clasifica corredores:
    1. Terminados arriba.
    2. Mayor cantidad de checkpoints visitados.
    3. Menor distancia al checkpoint pendiente mas cercano.
    """
    return sorted(
        corredores.values(),
        key=lambda corredor: (
            corredor.get("estado") != "terminado",
            -int(corredor.get("cantidad_checkpoints_visitados", 0)),
            float(corredor.get("distancia_checkpoint_pendiente_mas_cercano_m", float("inf"))),
            corredor.get("nombre", ""),
        ),
    )
