import hashlib
import math
import random
import threading
import time
import base64
import json
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory, make_response
from flask_socketio import SocketIO
import cv2
import numpy as np

from checkpoints import CHECKPOINTS, actualizar_estado_corredor, clasificar_corredores, haversine_distance_m
from config import DURACION, MAX_PARTICIPANTES, participants_lock
from geojson_store import append_feature
from participants import get_or_create_participant, participants_cache, reset_participants, save_participants
from Puntaje import get_puntaje_retos_detalle, refrescar_puntajes_retos, sincronizar_puntajes
from colores.vision_backend import procesar_frame_yolo_api
from ultralytics import YOLO
import os

modelo_yolo_global = None
ruta_modelo = os.path.join(os.path.dirname(__file__), "colores", "detección", "best.pt")
if os.path.exists(ruta_modelo):
    print(f"Cargando YOLO desde {ruta_modelo}")
    modelo_yolo_global = YOLO(ruta_modelo)
else:
    print(f"ERROR: No se encontrÃ³ YOLO en {ruta_modelo}")

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
socketio = SocketIO(app, cors_allowed_origins="*")

reset_participants()
try:
    refrescar_puntajes_retos()
except Exception as e:
    print("No se pudieron cargar puntajes_retos al iniciar:", e)
threading.Thread(target=sincronizar_puntajes, daemon=True).start()

inicio = time.time()
runners_stats: dict[str, dict] = {}
_battery_levels_by_device: dict[str, float] = {}
_battery_lock = threading.Lock()
_last_gps_saved_by_device: dict[str, float] = {}
_gps_dedupe_lock = threading.Lock()
device_trackers: dict[str, dict] = {}
MAX_BATTERY_SCORE = 30.0
MIN_GPS_SAVE_INTERVAL_SECONDS = 1.5
PESO_RESET_CHECKPOINT_ID = 4
PESO_RESET_DISTANCE_METERS = 4.0
COLOR_WEIGHTS_KG = {"Rojo": 1.0, "Blanco": 3.0, "Negro": 5.0}
PESO_ALERTA_KG = 10.0
BASE_DIR = Path(__file__).resolve().parent
VISION_CONFIG = {
    "limits": {"Rojo": 10, "Negro": 2, "Blanco": 3},
    "max_balls_total": 10,
    "mesh_fraction": 0.38,
    "camera": {
        "width": 1280,
        "height": 720,
        "delay_ms": 33,
    },
    "model_path": str(BASE_DIR / "colores" / "detección" / "best.pt"),
    "hsv_ranges": {
        "Rojo": [
            (np.array([0, 50, 40]), np.array([12, 255, 255])),
            (np.array([160, 50, 40]), np.array([180, 255, 255])),
        ],
        "Blanco": [
            (np.array([0, 0, 50]), np.array([180, 180, 255])),
        ],
        "Negro": [
            (np.array([0, 0, 0]), np.array([180, 255, 75])),
        ],
    },
    "color_weights_kg": COLOR_WEIGHTS_KG,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_device_info(data: dict) -> tuple[str, str, str]:
    user_agent = request.headers.get("User-Agent", "")
    device_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    device_id = data.get("device_id")

    if not device_id:
        fingerprint = f"{device_ip}|{user_agent}"
        device_id = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]

    return device_id, device_ip, user_agent

def get_participant_name_for_device(device_id: str, fallback: str = "Desconocido") -> str:
    if not device_id:
        return fallback

    with participants_lock:
        entry = participants_cache.get(device_id)

    if isinstance(entry, dict):
        return entry.get("nombre") or fallback
    if isinstance(entry, str):
        return entry
    return fallback


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def haversine(lat1, lon1, lat2, lon2):
    radius_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_km * c


def get_next_battery_level(device_id: str) -> float:
    with _battery_lock:
        current_level = _battery_levels_by_device.get(device_id)

        if current_level is None:
            current_level = random.uniform(0.0, 100.0)
        else:
            current_level += random.uniform(-5.0, 5.0)

        current_level = clamp(current_level, 0.0, 100.0)
        _battery_levels_by_device[device_id] = current_level
        return current_level


def get_participant_position(participante: str) -> int | None:
    try:
        return int(participante.rsplit("_", 1)[1])
    except (IndexError, TypeError, ValueError):
        return None


def get_battery_score(nivel_bateria: float) -> float:
    with _battery_lock:
        highest_battery = max(_battery_levels_by_device.values(), default=0.0)
    if highest_battery > 0:
        return round((nivel_bateria / highest_battery) * MAX_BATTERY_SCORE, 2)
    return 0.0


def competition_rank(sorted_items: list, target_item, rank_value_fn) -> int | None:
    previous_value = None
    current_rank = 0

    for index, item in enumerate(sorted_items, start=1):
        item_value = rank_value_fn(item)
        if item_value != previous_value:
            current_rank = index
            previous_value = item_value

        if item == target_item:
            return current_rank

    return None


def get_battery_rank(device_id: str) -> int | None:
    with _battery_lock:
        battery_levels = dict(_battery_levels_by_device)

    highest_battery = max(battery_levels.values(), default=0.0)

    def score_from_snapshot(level: float) -> float:
        if highest_battery <= 0:
            return 0.0
        return clamp((level / highest_battery) * MAX_BATTERY_SCORE, 0.0, MAX_BATTERY_SCORE)

    with participants_lock:
        participant_names = {
            participant_device_id: entry.get("nombre") if isinstance(entry, dict) else entry
            for participant_device_id, entry in participants_cache.items()
        }

    ranked_devices = sorted(
        battery_levels,
        key=lambda participant_device_id: (
            -score_from_snapshot(battery_levels[participant_device_id]),
            get_participant_position(participant_names.get(participant_device_id, "")) or 999999,
            participant_device_id,
        ),
    )

    return competition_rank(
        ranked_devices,
        device_id,
        lambda participant_device_id: -round(score_from_snapshot(battery_levels[participant_device_id]), 6),
    )


def get_checkpoint_rank_value(runner: dict) -> tuple:
    return (
        runner.get("estado") != "terminado",
        -int(runner.get(
            "cantidad_checkpoints_ponderados_visitados",
            runner.get("cantidad_checkpoints_visitados", 0),
        )),
        round(float(runner.get("distancia_checkpoint_pendiente_mas_cercano_m", float("inf"))), 2),
    )


def get_checkpoint_rank_from_snapshot(device_id: str, runners_snapshot: dict) -> int | None:
    ranked_runners = clasificar_corredores(runners_snapshot)
    target_runner = next(
        (runner for runner in ranked_runners if runner.get("device_id") == device_id),
        None,
    )

    if target_runner is None:
        return None

    return competition_rank(ranked_runners, target_runner, get_checkpoint_rank_value)


def get_checkpoint_by_id(checkpoint_id: int) -> dict | None:
    for checkpoint in CHECKPOINTS:
        if int(checkpoint["id"]) == checkpoint_id:
            return checkpoint
    return None


def get_checkpoint_name(checkpoint: dict | None) -> str:
    if not checkpoint:
        return "Sin checkpoint"

    checkpoint_id = checkpoint.get("id", "")
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


def get_participants_for_view() -> list[str]:
    with participants_lock:
        participant_names = [
            entry.get("nombre") if isinstance(entry, dict) else str(entry)
            for entry in participants_cache.values()
        ]

    return sorted(
        (name for name in participant_names if name),
        key=lambda name: (get_participant_position(name) or 999999, name),
    )


def safe_filename_part(value) -> str:
    text_value = str(value or "").strip().replace(" ", "_").replace("/", "-")
    safe_value = "".join(
        char if char.isalnum() or char in ("_", "-") else "_"
        for char in text_value
    ).strip("_")
    return safe_value or "sin_dato"


def get_gallery_checkpoint_context(device_id: str) -> dict:
    if not device_id:
        return {}

    with participants_lock:
        entry = participants_cache.get(device_id)
        entry = dict(entry) if isinstance(entry, dict) else {}

    last_coord = entry.get("last_coord")
    if not last_coord or len(last_coord) < 2:
        return {}

    try:
        lat = float(last_coord[0])
        lon = float(last_coord[1])
    except (TypeError, ValueError):
        return {}

    checkpoint_matches = []
    for checkpoint in CHECKPOINTS:
        distance = haversine_distance_m(
            lat,
            lon,
            float(checkpoint["lat"]),
            float(checkpoint["lon"]),
        )
        radius = float(checkpoint.get("radio_m", 5.0))
        if distance <= radius:
            checkpoint_matches.append((distance, checkpoint))

    if not checkpoint_matches:
        return {}

    distance, checkpoint = min(checkpoint_matches, key=lambda item: item[0])
    checkpoint_id = int(checkpoint["id"])
    checkpoint_name = get_checkpoint_name(checkpoint)

    return {
        "checkpoint_id": checkpoint_id,
        "checkpoint_nombre": checkpoint_name,
        "checkpoint_slug": f"checkpoint_{checkpoint_id}",
        "distancia_checkpoint_m": round(distance, 2),
    }


def enrich_gallery_item(item: dict) -> dict:
    enriched = dict(item)
    device_id = enriched.get("device_id")
    enriched["participante"] = enriched.get("participante") or get_participant_name_for_device(device_id, device_id or "Desconocido")

    checkpoint_id = enriched.get("checkpoint_id")
    if checkpoint_id and not enriched.get("checkpoint_nombre"):
        checkpoint = get_checkpoint_by_id(int(checkpoint_id))
        if checkpoint:
            enriched["checkpoint_nombre"] = get_checkpoint_name(checkpoint)
    if checkpoint_id and not enriched.get("checkpoint_slug"):
        enriched["checkpoint_slug"] = f"checkpoint_{int(checkpoint_id)}"

    return enriched


def load_gallery_items() -> list[dict]:
    registro_galeria = BASE_DIR / "galeria.json"
    if not registro_galeria.exists():
        return []

    with open(registro_galeria, "r", encoding="utf-8") as f:
        try:
            gallery_data = json.load(f)
        except Exception:
            return []

    if not isinstance(gallery_data, list):
        return []

    return [
        enrich_gallery_item(item)
        for item in gallery_data
        if isinstance(item, dict)
    ]


def get_peso_from_payload(data: dict, current_peso: float) -> float:
    try:
        if data.get("peso") is not None:
            return float(data["peso"])

        if data.get("peso_incremento") is not None:
            return current_peso + float(data["peso_incremento"])
    except (TypeError, ValueError):
        return current_peso

    return current_peso


def safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def should_skip_gps_save(device_id: str) -> bool:
    now = time.time()
    with _gps_dedupe_lock:
        last_saved = _last_gps_saved_by_device.get(device_id, 0.0)
        if now - last_saved < MIN_GPS_SAVE_INTERVAL_SECONDS:
            return True

        _last_gps_saved_by_device[device_id] = now
        return False


def should_reset_peso(latitude: float, longitude: float) -> bool:
    checkpoint = get_checkpoint_by_id(PESO_RESET_CHECKPOINT_ID)
    if checkpoint is None:
        return False

    distance_m = haversine_distance_m(
        latitude,
        longitude,
        float(checkpoint["lat"]),
        float(checkpoint["lon"]),
    )
    return distance_m <= PESO_RESET_DISTANCE_METERS




def normalize_color_counts(raw_counts) -> dict[str, int]:
    if not isinstance(raw_counts, dict):
        return {color: 0 for color in COLOR_WEIGHTS_KG}

    normalized = {}
    for color in COLOR_WEIGHTS_KG:
        try:
            normalized[color] = max(0, int(raw_counts.get(color, 0) or 0))
        except (TypeError, ValueError):
            normalized[color] = 0
    return normalized


def expand_detected_colors(color_counts: dict[str, int]) -> list[str]:
    colors = []
    for color in COLOR_WEIGHTS_KG:
        colors.extend([color] * color_counts.get(color, 0))
    return colors


def calculate_peso_kg_from_payload(data: dict, color_counts: dict[str, int]) -> float | None:
    for key in ("peso_kg", "carga_kg"):
        if data.get(key) is not None:
            try:
                return max(0.0, float(data[key]))
            except (TypeError, ValueError):
                return None

    if any(color_counts.values()):
        return sum(COLOR_WEIGHTS_KG[color] * count for color, count in color_counts.items())

    return None

def update_runner_stats(participante: str, latitude: float, longitude: float, speed_kmh) -> dict:
    vel = float(speed_kmh) if speed_kmh is not None else 0.0

    if participante not in runners_stats:
        runners_stats[participante] = {
            "distancia_km": 0.0,
            "max_speed": vel,
            "last_coord": (latitude, longitude),
        }
    else:
        stats = runners_stats[participante]
        last_lat, last_lon = stats["last_coord"]
        dist_incremental = haversine(last_lat, last_lon, latitude, longitude)

        if dist_incremental > 0.001:
            stats["distancia_km"] += dist_incremental
            stats["last_coord"] = (latitude, longitude)

        if vel > stats["max_speed"]:
            stats["max_speed"] = vel

    return runners_stats[participante]


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    resp = make_response(render_template("index.html"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.route("/mapa")
def mapa():
    return render_template(
        "mapa.html",
        checkpoints=[{**checkpoint, "nombre": get_checkpoint_name(checkpoint)} for checkpoint in CHECKPOINTS],
        non_scoring_checkpoint_ids=[PESO_RESET_CHECKPOINT_ID],
        participantes=get_participants_for_view(),
        galeria=load_gallery_items(),
    )


@app.route("/jurados")
def jurados():
    return render_template("jurados.html")


@app.route("/fotos_checkpoints")
def fotos_checkpoints():
    return render_template(
        "fotos_checkpoints.html",
        checkpoints=[{**checkpoint, "nombre": get_checkpoint_name(checkpoint)} for checkpoint in CHECKPOINTS],
        participantes=get_participants_for_view(),
        galeria=load_gallery_items(),
    )


@app.route("/estado_mapa", methods=["GET"])
def estado_mapa():
    return jsonify({
        "checkpoints": [{**checkpoint, "nombre": get_checkpoint_name(checkpoint)} for checkpoint in CHECKPOINTS],
        "non_scoring_checkpoint_ids": [PESO_RESET_CHECKPOINT_ID],
        "participantes": get_participants_for_view(),
        "galeria": load_gallery_items(),
    })


@app.route("/sw.js")
def service_worker():
    return send_from_directory("static", "sw.js")


@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json")


@app.route("/registrar", methods=["POST"])
def registrar():
    print("Recibida petición POST en /registrar")
    data = request.json or {}
    device_id, device_ip, user_agent = get_device_info(data)

    with participants_lock:
        if "custom_name" in data:
            custom = data["custom_name"]
            if device_id not in participants_cache:
                if len(participants_cache) < MAX_PARTICIPANTES:
                    participants_cache[device_id] = {"nombre": custom}
                    save_participants(participants_cache)
                    participante = custom
                else:
                    participante = None
            else:
                participants_cache[device_id]["nombre"] = custom
                save_participants(participants_cache)
                participante = custom
        else:
            participante = get_or_create_participant(device_id)

    if not participante:
        return jsonify({
            "status": "limite_participantes",
            "msg": f"Ya se alcanzÃ³ el lÃ­mite de {MAX_PARTICIPANTES} participantes.",
        }), 403

    return jsonify({
        "status": "ok",
        "participante": participante,
        "device_id": device_id,
        "device_label": data.get("device_label") or f"Dispositivo-{device_id[:8]}",
        "device_ip": device_ip,
    })


@app.route("/gps", methods=["POST"])
def gps():
    global inicio

    if time.time() - inicio > DURACION:
        return jsonify({"status": "cerrado"})

    data = request.json
    if not data or "latitude" not in data or "longitude" not in data:
        return jsonify({"status": "error", "msg": "Datos incompletos"}), 400

    device_id, device_ip, user_agent = get_device_info(data)

    with participants_lock:
        participante = get_or_create_participant(device_id) 

    if not participante:
        return jsonify({
            "status": "limite_participantes",
            "msg": f"Ya se alcanzó el limite de {MAX_PARTICIPANTES} participantes.",
        }), 403

    if should_skip_gps_save(device_id):
        return jsonify({
            "status": "ok",
            "participante": participante,
            "skipped": True,
            "msg": "Lectura duplicada ignorada",
        })

    puntaje_retos_detalle = get_puntaje_retos_detalle(participante)
    puntaje_retos_actual = puntaje_retos_detalle["puntaje_retos"]
    latitude = float(data["latitude"])
    longitude = float(data["longitude"])
    posicion_inicial = get_participant_position(participante)

    with participants_lock:
        participant_entry = participants_cache[device_id]
        participant_entry["device_id"] = device_id
        participant_entry["nombre"] = participante
        participant_entry["last_coord"] = (latitude, longitude)

        estado_anterior = participant_entry.get("estado", "corriendo")
        actualizar_estado_corredor(participant_entry, latitude, longitude, corredores=participants_cache)
        participant_entry["puntaje_retos"] = puntaje_retos_actual
        participant_entry["peso"] = participant_entry.get("puntos_totales", 0)

        color_counts = normalize_color_counts(data.get("conteo_colores") or data.get("color_counts"))
        detected_colors = expand_detected_colors(color_counts)
        peso_detectado_kg = calculate_peso_kg_from_payload(data, color_counts)

        participant_entry["conteo_colores"] = color_counts
        participant_entry["color_detectado"] = detected_colors
        participant_entry.setdefault("peso_kg", 0.0)
        participant_entry.setdefault("peso_entregado_kg", 0.0)
        participant_entry["peso_descargado_kg"] = 0.0

        if peso_detectado_kg is not None:
            participant_entry["peso_kg"] = peso_detectado_kg

        inside_descarga = should_reset_peso(latitude, longitude)
        was_inside_descarga = bool(participant_entry.get("en_checkpoint_descarga_peso", False))
        if inside_descarga and not was_inside_descarga:
            peso_actual_kg = safe_float(participant_entry.get("peso_kg"), 0.0)
            if peso_actual_kg > 0:
                participant_entry["peso_descargado_kg"] = peso_actual_kg
                participant_entry["peso_entregado_kg"] = safe_float(participant_entry.get("peso_entregado_kg"), 0.0) + peso_actual_kg
            participant_entry["peso_kg"] = 0.0
            participant_entry["conteo_colores"] = {color: 0 for color in COLOR_WEIGHTS_KG}
            participant_entry["color_detectado"] = []
            participant_entry["en_checkpoint_descarga_peso"] = True
        elif inside_descarga:
            participant_entry["peso_kg"] = 0.0
            participant_entry["conteo_colores"] = {color: 0 for color in COLOR_WEIGHTS_KG}
            participant_entry["color_detectado"] = []
        else:
            participant_entry["en_checkpoint_descarga_peso"] = False

        estado_actual = participant_entry.get("estado", "corriendo")
        nivel_bateria_final = participant_entry.get("nivel_bateria_final")
        if estado_actual == "terminado":
            if estado_anterior != "terminado" or nivel_bateria_final is None:
                nivel_bateria = get_next_battery_level(device_id)
                participant_entry["nivel_bateria_final"] = nivel_bateria
            else:
                nivel_bateria = float(nivel_bateria_final)
                with _battery_lock:
                    _battery_levels_by_device[device_id] = nivel_bateria
        else:
            nivel_bateria = get_next_battery_level(device_id)

        participant_entry["nivel_bateria"] = nivel_bateria
        save_participants(participants_cache)

        checkpoint_state = {
            "checkpoints_visitados": participant_entry.get("checkpoints_visitados", []),
            "cantidad_checkpoints_visitados": participant_entry.get("cantidad_checkpoints_visitados", 0),
            "cantidad_checkpoints_ponderados_visitados": participant_entry.get("cantidad_checkpoints_ponderados_visitados", 0),
            "checkpoint_descarga_visitado": participant_entry.get("checkpoint_descarga_visitado", False),
            "checkpoint_pendiente_mas_cercano": participant_entry.get("checkpoint_pendiente_mas_cercano"),
            "checkpoint_pendiente_mas_cercano_id": participant_entry.get("checkpoint_pendiente_mas_cercano_id"),
            "distancia_checkpoint_pendiente_mas_cercano_m": participant_entry.get("distancia_checkpoint_pendiente_mas_cercano_m"),
            "checkpoint_mas_cercano": participant_entry.get("checkpoint_mas_cercano"),
            "checkpoint_mas_cercano_id": participant_entry.get("checkpoint_mas_cercano_id"),
            "distancia_checkpoint_mas_cercano_m": participant_entry.get("distancia_checkpoint_mas_cercano_m"),
            "puntuacion_checkpoints": participant_entry.get("puntuacion_checkpoints", 0.0),
            "puntaje_checkpoints": participant_entry.get("puntaje_checkpoints", 0.0),
            "puntaje_retos": participant_entry.get("puntaje_retos", 0.0),
            "estado": estado_actual,
            "puntos_totales": participant_entry.get("puntos_totales", 0),
            "puntaje_equipo": participant_entry.get("puntaje_equipo", 0),
            "peso": participant_entry.get("puntos_totales", 0),
            "peso_kg": participant_entry.get("peso_kg", 0.0),
            "peso_entregado_kg": participant_entry.get("peso_entregado_kg", 0.0),
            "peso_descargado_kg": participant_entry.get("peso_descargado_kg", 0.0),
            "conteo_colores": participant_entry.get("conteo_colores", {color: 0 for color in COLOR_WEIGHTS_KG}),
            "color_detectado": participant_entry.get("color_detectado", []),
        }
        runners_snapshot = {
            runner_device_id: {
                **entry,
                "device_id": runner_device_id,
            }
            for runner_device_id, entry in participants_cache.items()
            if isinstance(entry, dict)
        }

    posicion_checkpoints = get_checkpoint_rank_from_snapshot(device_id, runners_snapshot)
    puntaje_bateria = get_battery_score(nivel_bateria)
    posicion_bateria = get_battery_rank(device_id)
    puntaje_checkpoints = checkpoint_state["puntaje_checkpoints"]
    puntaje_retos = safe_float(checkpoint_state["puntaje_retos"])
    puntaje = round(puntaje_bateria + puntaje_checkpoints + puntaje_retos, 2)
    posicion = posicion_checkpoints
    runner_stats = update_runner_stats(participante, latitude, longitude, data.get("speed_kmh"))

    feature = {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [longitude, latitude],
        },
        "properties": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "Date_GPS": time.strftime("%Y-%m-%d %H:%M:%S"),
            "accuracy": data.get("accuracy"),
            "altitude": data.get("altitude"),
            "heading": data.get("heading"),
            "nivel_bateria": nivel_bateria,
            "posicion_inicial": posicion_inicial,
            "posicion": posicion,
            "posicion_bateria": posicion_bateria,
            "posicion_checkpoints": posicion_checkpoints,
            "puntaje_bateria": puntaje_bateria,
            "puntaje_checkpoints": puntaje_checkpoints,
            "puntaje_retos": puntaje_retos,
            "puntaje_retos_total": puntaje_retos_detalle["puntaje_retos_total"],
            "puntaje_retos_equipo": puntaje_retos_detalle["puntaje_retos_equipo"],
            "puntaje_retos_origen": puntaje_retos_detalle["puntaje_retos_origen"],
            "puntaje_retos_lectura_ts": puntaje_retos_detalle["puntaje_retos_lectura_ts"],
            "puntaje": puntaje,
            "puntos_totales": checkpoint_state["puntos_totales"],
            "peso": checkpoint_state["peso"],
            "peso_kg": checkpoint_state["peso_kg"],
            "peso_entregado_kg": checkpoint_state["peso_entregado_kg"],
            "peso_descargado_kg": checkpoint_state["peso_descargado_kg"],
            "puntaje_equipo": checkpoint_state["puntaje_equipo"],
            "puntuacion_checkpoints": checkpoint_state["puntuacion_checkpoints"],
            "checkpoints_visitados": checkpoint_state["checkpoints_visitados"],
            "checkpoints_visitados_txt": ",".join(
                str(checkpoint_id) for checkpoint_id in checkpoint_state["checkpoints_visitados"]
            ),
            "cantidad_checkpoints_visitados": checkpoint_state["cantidad_checkpoints_visitados"],
            "cantidad_checkpoints_ponderados_visitados": checkpoint_state["cantidad_checkpoints_ponderados_visitados"],
            "checkpoint_descarga_visitado": checkpoint_state["checkpoint_descarga_visitado"],
            "checkpoint_pendiente_mas_cercano": checkpoint_state["checkpoint_pendiente_mas_cercano"],
            "checkpoint_pendiente_mas_cercano_id": checkpoint_state["checkpoint_pendiente_mas_cercano_id"],
            "distancia_checkpoint_pendiente_mas_cercano_m": checkpoint_state["distancia_checkpoint_pendiente_mas_cercano_m"],
            "checkpoint_mas_cercano": checkpoint_state["checkpoint_mas_cercano"],
            "checkpoint_mas_cercano_id": checkpoint_state["checkpoint_mas_cercano_id"],
            "distancia_checkpoint_mas_cercano_m": checkpoint_state["distancia_checkpoint_mas_cercano_m"],
            "estado": checkpoint_state["estado"],
            "distancia_km": runner_stats["distancia_km"],
            "max_speed": runner_stats["max_speed"],
            "speed_mps": data.get("speed_mps"),
            "speed_kmh": data.get("speed_kmh"),
            "speed_source": data.get("speed_source"),
            "accel_gx": data.get("accel_gx"),
            "accel_gy": data.get("accel_gy"),
            "accel_gz": data.get("accel_gz"),
            "accel_g_magnitude": data.get("accel_g_magnitude"),
            "acceleration_mps2": data.get("acceleration_mps2"),
            "sensor_timestamp_ms": data.get("sensor_timestamp_ms"),
            "client_timestamp_ms": data.get("client_timestamp_ms"),
            "participante": participante,
            "device_id": device_id,
            "device_label": data.get("device_label") or f"Dispositivo-{device_id[:8]}",
            "device_ip": device_ip,
            "carga_kg": checkpoint_state["peso_kg"],
            "peso_kg": checkpoint_state["peso_kg"],
            "peso_entregado_kg": checkpoint_state["peso_entregado_kg"],
            "peso_descargado_kg": checkpoint_state["peso_descargado_kg"],
            "conteo_colores": checkpoint_state["conteo_colores"],
            "color_detectado": checkpoint_state["color_detectado"],
        },
    }

    append_feature(feature)

    print(
        f"[GPS] {participante} {feature['properties']['device_label']} "
        f"{latitude}, {longitude} "
        f"vel={data.get('speed_kmh', 'N/A')} km/h ({data.get('speed_source', '')}) "
        f"distancia={runner_stats['distancia_km']:.3f} km "
        f"bateria={nivel_bateria:.2f}% "
        f"estado={checkpoint_state['estado']} "
        f"checkpoints={checkpoint_state['cantidad_checkpoints_visitados']} "
        f"ponderados={checkpoint_state['cantidad_checkpoints_ponderados_visitados']} "
        f"puntos={checkpoint_state['puntos_totales']} "
        f"equipo={checkpoint_state['puntaje_equipo']} "
        f"peso={float(checkpoint_state['peso']):.2f} "
        f"retos={puntaje_retos:.2f} "
        f"puntaje={puntaje:.2f}"
    )

    socketio.emit("nueva_posicion", {
        "participante": participante,
        "latitude": latitude,
        "longitude": longitude,
        "velocidad": float(data.get("speed_kmh")) if data.get("speed_kmh") is not None else 0.0,
        "distancia_km": runner_stats["distancia_km"],
        "max_speed": runner_stats["max_speed"],
        "nivel_bateria": nivel_bateria,
        "posicion": posicion,
        "puntaje": puntaje,
        "puntaje_retos": puntaje_retos,
        "estado": checkpoint_state["estado"],
        "puntos_totales": checkpoint_state["puntos_totales"],
        "peso": checkpoint_state["peso"],
        "peso_kg": checkpoint_state["peso_kg"],
        "peso_entregado_kg": checkpoint_state["peso_entregado_kg"],
        "peso_descargado_kg": checkpoint_state["peso_descargado_kg"],
        "puntaje_equipo": checkpoint_state["puntaje_equipo"],
        "checkpoints_visitados": checkpoint_state["cantidad_checkpoints_visitados"],
        "checkpoints_ponderados_visitados": checkpoint_state["cantidad_checkpoints_ponderados_visitados"],
        "checkpoint_descarga_visitado": checkpoint_state["checkpoint_descarga_visitado"],
        "checkpoint_pendiente_mas_cercano": checkpoint_state["checkpoint_pendiente_mas_cercano"],
        "distancia_checkpoint_pendiente_mas_cercano_m": checkpoint_state["distancia_checkpoint_pendiente_mas_cercano_m"],
        "checkpoint_mas_cercano": checkpoint_state["checkpoint_mas_cercano"],
        "distancia_checkpoint_mas_cercano_m": checkpoint_state["distancia_checkpoint_mas_cercano_m"],
        "carga_kg": checkpoint_state["peso_kg"],
        "peso_kg": checkpoint_state["peso_kg"],
        "peso_entregado_kg": checkpoint_state["peso_entregado_kg"],
        "peso_descargado_kg": checkpoint_state["peso_descargado_kg"],
        "conteo_colores": checkpoint_state["conteo_colores"],
        "color_detectado": checkpoint_state["color_detectado"],
    })

    response = {
        "status": "ok",
        "participante": participante,
        "nivel_bateria": nivel_bateria,
        "posicion_inicial": posicion_inicial,
        "posicion": posicion,
        "posicion_bateria": posicion_bateria,
        "posicion_checkpoints": posicion_checkpoints,
        "puntaje_bateria": puntaje_bateria,
        "puntaje_checkpoints": puntaje_checkpoints,
        "puntaje_retos": puntaje_retos,
        "puntaje": puntaje,
        "puntos_totales": checkpoint_state["puntos_totales"],
        "peso": checkpoint_state["peso"],
        "peso_kg": checkpoint_state["peso_kg"],
        "peso_entregado_kg": checkpoint_state["peso_entregado_kg"],
        "peso_descargado_kg": checkpoint_state["peso_descargado_kg"],
        "puntaje_equipo": checkpoint_state["puntaje_equipo"],
        "puntuacion_checkpoints": checkpoint_state["puntuacion_checkpoints"],
        "checkpoints_visitados": checkpoint_state["checkpoints_visitados"],
        "cantidad_checkpoints_visitados": checkpoint_state["cantidad_checkpoints_visitados"],
        "cantidad_checkpoints_ponderados_visitados": checkpoint_state["cantidad_checkpoints_ponderados_visitados"],
        "checkpoint_descarga_visitado": checkpoint_state["checkpoint_descarga_visitado"],
        "checkpoint_pendiente_mas_cercano": checkpoint_state["checkpoint_pendiente_mas_cercano"],
        "distancia_checkpoint_pendiente_mas_cercano_m": checkpoint_state["distancia_checkpoint_pendiente_mas_cercano_m"],
        "checkpoint_mas_cercano": checkpoint_state["checkpoint_mas_cercano"],
        "distancia_checkpoint_mas_cercano_m": checkpoint_state["distancia_checkpoint_mas_cercano_m"],
        "estado": checkpoint_state["estado"],
        "distancia_km": runner_stats["distancia_km"],
        "max_speed": runner_stats["max_speed"],
        "carga_kg": checkpoint_state["peso_kg"],
        "peso_kg": checkpoint_state["peso_kg"],
        "peso_entregado_kg": checkpoint_state["peso_entregado_kg"],
        "peso_descargado_kg": checkpoint_state["peso_descargado_kg"],
        "conteo_colores": checkpoint_state["conteo_colores"],
        "color_detectado": checkpoint_state["color_detectado"],
    }

    return jsonify(response)

@app.route("/vision", methods=["POST"])
def vision():
    print("Recibida petición POST en /vision")
    data = request.json or {}
    if "image" not in data or "device_id" not in data:
        print("Datos faltantes en /vision")
        return jsonify({"status": "error", "msg": "Datos de imagen o dispositivo faltantes"}), 400

    device_id = data["device_id"]
    image_b64 = data["image"]
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]

    try:
        image_bytes = base64.b64decode(image_b64)
        np_arr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({"status": "error", "msg": "No se pudo decodificar el frame"}), 400

        if device_id not in device_trackers:
            device_trackers[device_id] = {}

        estado = device_trackers[device_id]

        gp_max_w = 320
        h_orig, w_orig = frame.shape[:2]
        if w_orig > gp_max_w:
            scale = gp_max_w / w_orig
            frame = cv2.resize(frame, (gp_max_w, int(h_orig * scale)), interpolation=cv2.INTER_AREA)

        # Hacer copia limpia ANTES de que procesar_frame_yolo_api modifique el frame
        frame_clean = frame.copy()

        mobile_mode = data.get("mobile", False)
        calibrate_mode = data.get("calibrate", False)
        
        t_start = time.time()
        detectado, frame_annotated = procesar_frame_yolo_api(frame, estado, modelo_yolo_global, mobile_mode=mobile_mode, calibrate_mode=calibrate_mode)

        # Agregar marca de agua
        from datetime import datetime
        
        target_participante = data.get("target_participante")
        if target_participante:
            participante_nombre = target_participante
            
            # Asegurar que el participante objetivo esté registrado en la caché
            from participants import participants_cache, save_participants, participants_lock
            with participants_lock:
                exists = any(
                    (entry.get("nombre") if isinstance(entry, dict) else str(entry)) == target_participante 
                    for entry in participants_cache.values()
                )
                if not exists:
                    dummy_id = f"dummy_{target_participante.replace(' ', '_')}"
                    participants_cache[dummy_id] = {"nombre": target_participante}
                    save_participants(participants_cache)
        else:
            participante_nombre = get_participant_name_for_device(device_id)

        dt_now = datetime.now()
        fecha_hora = dt_now.strftime("%Y-%m-%d %H:%M:%S")
        # No imprimimos la marca de agua en la imagen directamente según lo solicitado

        jpeg_q = 35
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_q]
        _, buffer = cv2.imencode(".jpg", frame_annotated, encode_params)
        annotated_b64 = base64.b64encode(buffer).decode("utf-8")

        if detectado and "color" in detectado:
            checkpoint_context = get_gallery_checkpoint_context(device_id)
            if not checkpoint_context:
                # Si no está en un checkpoint, asignar uno manual para que siempre se guarde la foto
                checkpoint_context = {
                    "checkpoint_id": 0,
                    "checkpoint_nombre": "Manual / Sin GPS",
                    "checkpoint_slug": "manual",
                    "distancia_checkpoint_m": 0.0
                }

            # --- Modulo de guardado de imagenes (Galeria) ---
            capturas_dir = BASE_DIR / "capturas"
            capturas_dir.mkdir(exist_ok=True)
            timestamp = int(dt_now.timestamp())
            safe_name = safe_filename_part(participante_nombre)
            checkpoint_slug = checkpoint_context["checkpoint_slug"]
            filename = f"captura_{safe_name}_{checkpoint_slug}_{timestamp}.jpg"

            filepath = capturas_dir / filename
            cv2.imwrite(str(filepath), frame_annotated)

            # Guardar tambien la imagen sin contornos (clean)
            filepath_clean = capturas_dir / filename.replace(".jpg", "_clean.jpg")
            cv2.imwrite(str(filepath_clean), frame_clean)

            # Guardamos registro en un JSON
            registro_galeria = BASE_DIR / "galeria.json"
            galeria_data = []
            if registro_galeria.exists():
                with open(registro_galeria, "r", encoding="utf-8") as f:
                    try: galeria_data = json.load(f)
                    except: pass

            gallery_item = {
                "filename": filename,
                "timestamp": timestamp,
                "device_id": device_id,
                "participante": participante_nombre,
                "fecha_hora": fecha_hora,
                "detections": detectado["counts"]
            }
            gallery_item.update(checkpoint_context)
            galeria_data.append(gallery_item)

            with open(registro_galeria, "w", encoding="utf-8") as f:
                json.dump(galeria_data, f, indent=4)
            
            # --- Integración con Mapa (GeoJSON y ArcGIS) ---
            if target_participante and detectado.get("carga_kg", 0) > 0:
                from geojson_store import load_geojson, append_feature
                from colores.arcgis import should_send_to_arcgis, send_feature_to_arcgis
                from participants import participants_cache, save_participants

                geojson_data = load_geojson()
                last_coords = None
                # Buscar la ultima ubicacion conocida del participante
                for feat in reversed(geojson_data.get("features", [])):
                    if feat.get("properties", {}).get("participante") == target_participante:
                        last_coords = feat.get("geometry", {}).get("coordinates")
                        break
                
                if last_coords:
                    map_feature = {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": last_coords,
                        },
                        "properties": {
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "participante": target_participante,
                            "device_label": "Jurado Scan",
                            "Carga_kg": detectado.get("carga_kg"),
                            "Color_Detectado": json.dumps(detectado.get("counts", {})),
                            "photo_filename": filename
                        }
                    }
                    append_feature(map_feature)
                    if should_send_to_arcgis(target_participante):
                        try:
                            send_feature_to_arcgis(map_feature, target_participante, participants_cache, save_participants)
                        except Exception as e:
                            print(f"[ArcGIS Vision Error]: {e}")
            # ------------------------------------------------

            return jsonify({
                "status": "ok",
                "detected": True,
                "saved": True,
                "filename": filename,
                "checkpoint_id": checkpoint_context["checkpoint_id"],
                "checkpoint_nombre": checkpoint_context["checkpoint_nombre"],
                "distancia_checkpoint_m": checkpoint_context["distancia_checkpoint_m"],
                "color": detectado["color"],
                "carga_kg": detectado["carga_kg"],
                "orientacion": detectado["orientacion"],
                "counts": detectado["counts"],
                "balls": detectado.get("balls", []),
                "annotated_image": annotated_b64,
                "gp_max_width": gp_max_w,
                "gp_jpeg_quality": jpeg_q,
            })

        return jsonify({
            "status": "ok",
            "detected": False,
            "counts": estado.get("counts") if not detectado else detectado.get("counts"),
            "balls": [],
            "annotated_image": annotated_b64,
            "gp_max_width": gp_max_w,
            "gp_jpeg_quality": jpeg_q,
        })

    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "msg": str(exc)}), 500

@app.route("/galeria", methods=["GET"])
def galeria():
    """Endpoint para listar las imagenes guardadas con participante y checkpoint."""
    return jsonify(load_gallery_items())

@app.route("/limpiar_galeria", methods=["POST", "DELETE"])
def limpiar_galeria():
    """Endpoint para vaciar la galería y eliminar las imágenes físicas"""
    registro_galeria = BASE_DIR / "galeria.json"
    capturas_dir = BASE_DIR / "capturas"
    
    # Limpiar el JSON
    if registro_galeria.exists():
        with open(registro_galeria, "w", encoding="utf-8") as f:
            json.dump([], f)
            
    # Eliminar las imágenes
    if capturas_dir.exists():
        for archivo in capturas_dir.glob("*.jpg"):
            try:
                archivo.unlink()
            except Exception as e:
                print(f"No se pudo eliminar {archivo}: {e}")
                
    return jsonify({"status": "ok", "msg": "Galería limpiada"})

from flask import send_from_directory
@app.route("/capturas/<filename>", methods=["GET"])
def obtener_captura(filename):
    """Endpoint para servir las imágenes guardadas a la galería"""
    return send_from_directory(str(BASE_DIR / "capturas"), filename)

@app.route("/vision_fast", methods=["POST"])
def vision_fast():
    device_id = request.headers.get("X-Device-Id")
    if not device_id:
        return jsonify({"status": "error", "msg": "X-Device-Id faltante"}), 400

    image_bytes = request.data
    if not image_bytes:
        return jsonify({"status": "error", "msg": "Datos de imagen binaria faltantes"}), 400

    try:
        import json
        np_arr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({"status": "error", "msg": "No se pudo decodificar el frame binario"}), 400

        if device_id not in device_trackers:
            device_trackers[device_id] = {}

        estado = device_trackers[device_id]

        gp_max_w = 640  # Aumentado para mejor resolución
        h_orig, w_orig = frame.shape[:2]
        if w_orig > gp_max_w:
            scale = gp_max_w / w_orig
            frame = cv2.resize(frame, (gp_max_w, int(h_orig * scale)), interpolation=cv2.INTER_AREA)

        detectado, frame_annotated = procesar_frame_yolo_api(frame, estado, modelo_yolo_global)

        jpeg_q = 65  # Mejor calidad visual
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_q]
        _, buffer = cv2.imencode(".jpg", frame_annotated, encode_params)
        
        # Enviar respuesta binaria directamente
        response = make_response(buffer.tobytes())
        response.headers['Content-Type'] = 'image/jpeg'
        
        # Enviar metadatos ocultos en las cabeceras HTTP
        meta_data = {
            "status": "ok",
            "detected": bool(detectado),
            "counts": estado.get("counts") if not detectado else detectado.get("counts"),
            "gp_max_width": gp_max_w,
            "gp_jpeg_quality": jpeg_q,
        }
        if detectado:
            meta_data.update({
                "color": detectado.get("color"),
                "carga_kg": detectado.get("carga_kg"),
                "orientacion": detectado.get("orientacion")
            })
            
        response.headers['X-Vision-Data'] = json.dumps(meta_data)
        
        return response

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "msg": str(e)}), 500

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
