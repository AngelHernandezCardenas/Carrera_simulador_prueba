import math


# ---------------------------------------------------------------------------
# EDITA AQUI TUS 3 CHECKPOINTS
# ---------------------------------------------------------------------------
# Cambia lat/lon por las coordenadas reales de tu carrera.
# radio_m es el radio de deteccion en metros para marcar el checkpoint.
CHECKPOINTS = [
    {"id": 1, "nombre": "Checkpoint 1", "lat": 25.651796, "lon": -100.288868, "radio_m": 5.0},
    {"id": 2, "nombre": "Checkpoint 2", "lat": 25.650694, "lon": -100.288201, "radio_m": 5.0},
    {"id": 3, "nombre": "Checkpoint 3", "lat": 25.649087, "lon": -100.290241, "radio_m": 5.0},
]

MAX_CHECKPOINT_SCORE = 50.0
PROXIMITY_DISTANCE_WINDOW_METERS = 1000.0


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
    return int(checkpoint["id"])


def _sorted_checkpoint_ids(checkpoint_ids) -> list[int]:
    return sorted(int(checkpoint_id) for checkpoint_id in checkpoint_ids)


def _nearest_pending_checkpoint(
    lat: float,
    lon: float,
    visited_ids: set[int],
    checkpoints: list[dict],
) -> tuple[dict | None, float]:
    pending = [
        checkpoint
        for checkpoint in checkpoints
        if _checkpoint_id(checkpoint) not in visited_ids
    ]

    if not pending:
        return None, 0.0

    nearest = min(
        pending,
        key=lambda checkpoint: haversine_distance_m(
            lat,
            lon,
            float(checkpoint["lat"]),
            float(checkpoint["lon"]),
        ),
    )
    distance = haversine_distance_m(lat, lon, float(nearest["lat"]), float(nearest["lon"]))
    return nearest, distance


def _checkpoint_score_out_of_50(
    visited_count: int,
    total_checkpoints: int,
    nearest_pending_distance_m: float,
) -> float:
    if total_checkpoints <= 0:
        return 0.0

    if visited_count >= total_checkpoints:
        return MAX_CHECKPOINT_SCORE

    points_per_checkpoint = MAX_CHECKPOINT_SCORE / total_checkpoints
    distance_ratio = max(
        0.0,
        1.0 - min(nearest_pending_distance_m, PROXIMITY_DISTANCE_WINDOW_METERS)
        / PROXIMITY_DISTANCE_WINDOW_METERS,
    )
    proximity_bonus = distance_ratio * (points_per_checkpoint - 0.01)
    score = (visited_count * points_per_checkpoint) + proximity_bonus
    return round(min(score, MAX_CHECKPOINT_SCORE), 2)


def actualizar_estado_corredor(
    corredor: dict,
    lat: float,
    lon: float,
    checkpoints: list[dict] | None = None,
) -> dict:
    """
    Actualiza el estado de un corredor sin usar orden fijo.
    Si entra al radio de cualquier checkpoint pendiente, se marca como visitado.
    """
    checkpoints = checkpoints or CHECKPOINTS
    visited_ids = set(_sorted_checkpoint_ids(corredor.get("checkpoints_visitados", [])))

    for checkpoint in checkpoints:
        checkpoint_id = _checkpoint_id(checkpoint)
        if checkpoint_id in visited_ids:
            continue

        distance = haversine_distance_m(
            lat,
            lon,
            float(checkpoint["lat"]),
            float(checkpoint["lon"]),
        )
        if distance <= float(checkpoint.get("radio_m", 5.0)):
            visited_ids.add(checkpoint_id)

    nearest_pending, nearest_distance = _nearest_pending_checkpoint(
        lat,
        lon,
        visited_ids,
        checkpoints,
    )
    visited_count = len(visited_ids)
    total_checkpoints = len(checkpoints)
    finished = visited_count >= total_checkpoints
    raw_score = (visited_count * 1000) if finished else (visited_count * 1000 - nearest_distance)

    corredor["checkpoints_visitados"] = _sorted_checkpoint_ids(visited_ids)
    corredor["cantidad_checkpoints_visitados"] = visited_count
    corredor["checkpoint_pendiente_mas_cercano"] = (
        None
        if nearest_pending is None
        else {
            "id": _checkpoint_id(nearest_pending),
            "nombre": nearest_pending.get("nombre", f"Checkpoint {_checkpoint_id(nearest_pending)}"),
        }
    )
    corredor["checkpoint_pendiente_mas_cercano_id"] = (
        None if nearest_pending is None else _checkpoint_id(nearest_pending)
    )
    corredor["distancia_checkpoint_pendiente_mas_cercano_m"] = round(nearest_distance, 2)
    corredor["puntuacion_checkpoints"] = round(raw_score, 2)
    corredor["puntaje_checkpoints"] = _checkpoint_score_out_of_50(
        visited_count,
        total_checkpoints,
        nearest_distance,
    )
    corredor["estado"] = "terminado" if finished else "corriendo"
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
