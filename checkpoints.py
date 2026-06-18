import math


# ---------------------------------------------------------------------------
# EDITA AQUI TUS CHECKPOINTS
# ---------------------------------------------------------------------------
# Cambia lat/lon por las coordenadas reales de tu carrera.
# radio_m es el radio de deteccion en metros para marcar el checkpoint.
CHECKPOINTS = [
    #SON PARA HACER PRUEBAS DE CARRERA REAL, PARA IR A COMER SERA UNA LINEA RECTA
    #lirucisa
    {"id": 1, "Biotecnologia-Centrales": "Checkpoint 1", "lat": 25.651796, "lon": -100.288868, "radio_m": 5.0},
    #esquina de bilbio entre biblio y aulas 4
    {"id": 2, "Bilio-Aulas4": "Checkpoint 2", "lat": 25.650111, "lon": -100.289386, "radio_m": 5.0},
    #atras de rectoria en carreton creo q se llama
    {"id": 3, "Carreton": "Checkpoint 3", "lat": 25.651442, "lon": -100.290235, "radio_m": 5.0},
    #rectoria
    {"id": 4, "Rectoria-Descarga": "Checkpoint 4", "lat": 25.651464, "lon": -100.291149, "radio_m": 5.0},
    #antes de jubileo
    {"id": 5, "Jubileo": "Checkpoint 5", "lat": 25.649140, "lon": -100.290238, "radio_m": 5.0},
]

MAX_CHECKPOINT_SCORE = 30.0
PROXIMITY_DISTANCE_WINDOW_METERS = 1000.0
NON_SCORING_CHECKPOINT_IDS = {4}
MAX_PERSONAS_POR_CHECKPOINT = 4
UNLIMITED_OCCUPANCY_CHECKPOINT_IDS = {4}
CHECKPOINT_DESCARGA_ID = 4

# Checkpoints que cargan puntos al corredor antes de descargar en el checkpoint 4.
# El checkpoint 4 NO debe estar aqui: solo descarga a puntaje_equipo y deja puntos_totales en 0.
# Para agregar otro checkpoint con el mismo puntaje, agrega su id con el mismo valor:
#     6: 3,
# Para agregar uno con puntaje diferente, cambia solo el valor:
#     7: 5,
CHECKPOINT_POINTS = {
    1: 9,
    2: 3,
    3: 3,
    5: 5,  # AJUSTA ESTE PUNTAJE A TU GUSTO
}


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


def _checkpoint_name(checkpoint: dict) -> str:
    checkpoint_id = _checkpoint_id(checkpoint)
    return (
        checkpoint.get("nombre")
        or checkpoint.get("Rectoria")
        or checkpoint.get("Rectoria-Descarga")
        or checkpoint.get("Jubileo")
        or checkpoint.get("Carreton")
        or checkpoint.get("Bilio-Aulas4")
        or checkpoint.get("Biotecnologia-Centrales")
        or f"Checkpoint {checkpoint_id}"
    )


def _sorted_checkpoint_ids(checkpoint_ids) -> list[int]:
    return sorted(int(checkpoint_id) for checkpoint_id in checkpoint_ids)


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


def _scoring_checkpoints(checkpoints: list[dict]) -> list[dict]:
    return [
        checkpoint
        for checkpoint in checkpoints
        if _checkpoint_id(checkpoint) in CHECKPOINT_POINTS
        and _checkpoint_id(checkpoint) not in NON_SCORING_CHECKPOINT_IDS
    ]


def _checkpoint_points(checkpoint_id: int) -> float:
    try:
        return float(CHECKPOINT_POINTS.get(int(checkpoint_id), 0.0))
    except (TypeError, ValueError):
        return 0.0


def _count_scoring_visited(visited_ids: set[int], checkpoints: list[dict]) -> int:
    scoring_ids = {_checkpoint_id(checkpoint) for checkpoint in _scoring_checkpoints(checkpoints)}
    return len(visited_ids.intersection(scoring_ids))


def _is_inside_checkpoint_id(
    lat: float,
    lon: float,
    checkpoints: list[dict],
    checkpoint_id: int,
) -> bool:
    for checkpoint in checkpoints:
        if _checkpoint_id(checkpoint) != checkpoint_id:
            continue

        distance = haversine_distance_m(
            lat,
            lon,
            float(checkpoint["lat"]),
            float(checkpoint["lon"]),
        )
        return distance <= float(checkpoint.get("radio_m", 5.0))

    return False


def _calculate_carried_points(
    visited_ids: set[int],
    deposited_ids: set[int],
    checkpoints: list[dict],
) -> float:
    scoring_ids = {_checkpoint_id(checkpoint) for checkpoint in _scoring_checkpoints(checkpoints)}
    pending_points_ids = visited_ids.intersection(scoring_ids).difference(deposited_ids)
    return sum(_checkpoint_points(checkpoint_id) for checkpoint_id in pending_points_ids)


def _checkpoint_score(
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
    corredores: dict | None = None,
) -> dict:
    """
    Actualiza el estado de un corredor sin usar orden fijo.
    Si entra al radio de cualquier checkpoint pendiente, se marca como visitado.
    """
    checkpoints = checkpoints or CHECKPOINTS
    visited_ids = set(_sorted_checkpoint_ids(corredor.get("checkpoints_visitados", [])))
    deposited_ids = set(_sorted_checkpoint_ids(corredor.get("checkpoints_puntos_entregados", [])))
    full_checkpoint_ids_for_visits = _full_checkpoint_ids(corredores, checkpoints, corredor)
    full_checkpoint_ids_for_display = _full_checkpoint_ids_with_current_position(
        corredores,
        checkpoints,
        corredor,
        lat,
        lon,
    )

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

    scoring_checkpoints = _scoring_checkpoints(checkpoints)
    available_scoring_checkpoints = [
        checkpoint
        for checkpoint in scoring_checkpoints
        if _checkpoint_id(checkpoint) not in full_checkpoint_ids_for_display
    ]
    nearest_scoring_checkpoint, closest_scoring_distance = _nearest_checkpoint(
        lat,
        lon,
        available_scoring_checkpoints,
    )
    nearest_pending, nearest_distance = _nearest_pending_checkpoint(
        lat,
        lon,
        visited_ids,
        scoring_checkpoints,
        full_checkpoint_ids_for_display,
    )
    visited_count = len(visited_ids)
    scoring_visited_count = _count_scoring_visited(visited_ids, checkpoints)
    total_checkpoints = len(scoring_checkpoints)
    required_checkpoint_ids = {_checkpoint_id(checkpoint) for checkpoint in checkpoints}
    all_required_visited = required_checkpoint_ids.issubset(visited_ids)
    scoring_finished = scoring_visited_count >= total_checkpoints
    scoring_distance = (
        PROXIMITY_DISTANCE_WINDOW_METERS
        if nearest_pending is None and not scoring_finished
        else nearest_distance
    )
    raw_score = (
        scoring_visited_count * 1000
        if scoring_finished
        else scoring_visited_count * 1000 - scoring_distance
    )

    corredor["checkpoints_visitados"] = _sorted_checkpoint_ids(visited_ids)
    corredor["cantidad_checkpoints_visitados"] = visited_count
    corredor["cantidad_checkpoints_ponderados_visitados"] = scoring_visited_count
    corredor["checkpoint_descarga_visitado"] = all(
        checkpoint_id in visited_ids for checkpoint_id in NON_SCORING_CHECKPOINT_IDS
    )
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
    corredor["distancia_checkpoint_pendiente_mas_cercano_m"] = round(scoring_distance, 2)
    corredor["checkpoint_mas_cercano"] = (
        None
        if nearest_scoring_checkpoint is None
        else {
            "id": _checkpoint_id(nearest_scoring_checkpoint),
            "nombre": _checkpoint_name(nearest_scoring_checkpoint),
        }
    )
    corredor["checkpoint_mas_cercano_id"] = (
        None if nearest_scoring_checkpoint is None else _checkpoint_id(nearest_scoring_checkpoint)
    )
    corredor["distancia_checkpoint_mas_cercano_m"] = round(closest_scoring_distance, 2)
    corredor["puntuacion_checkpoints"] = round(raw_score, 2)
    corredor["puntaje_checkpoints"] = _checkpoint_score(
        scoring_visited_count,
        total_checkpoints,
        scoring_distance,
    )
    scoring_ids = {_checkpoint_id(checkpoint) for checkpoint in scoring_checkpoints}
    deposited_ids = deposited_ids.intersection(scoring_ids)
    puntos_totales = _calculate_carried_points(visited_ids, deposited_ids, checkpoints)
    try:
        puntaje_equipo = float(corredor.get("puntaje_equipo", 0))
    except (TypeError, ValueError):
        puntaje_equipo = 0.0

    if _is_inside_checkpoint_id(lat, lon, checkpoints, CHECKPOINT_DESCARGA_ID):
        puntaje_equipo += puntos_totales
        deposited_ids.update(visited_ids.intersection(scoring_ids))
        puntos_totales = 0

    corredor["checkpoints_puntos_entregados"] = _sorted_checkpoint_ids(deposited_ids)
    corredor["puntos_totales"] = puntos_totales
    corredor["peso"] = puntos_totales
    corredor["puntaje_equipo"] = puntaje_equipo
    finished = all_required_visited and puntos_totales <= 0.0
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
            -int(corredor.get("cantidad_checkpoints_ponderados_visitados", corredor.get("cantidad_checkpoints_visitados", 0))),
            float(corredor.get("distancia_checkpoint_pendiente_mas_cercano_m", float("inf"))),
            corredor.get("nombre", ""),
        ),
    )
