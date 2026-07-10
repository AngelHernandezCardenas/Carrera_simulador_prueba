import hashlib
import math
import random
import threading
import time
import base64
import json
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory, make_response, send_file
from flask_socketio import SocketIO
import cv2
import numpy as np

from checkpoints import CHECKPOINTS, actualizar_estado_corredor, clasificar_corredores, haversine_distance_m
from config import DURACION, MAX_PARTICIPANTES, participants_lock
from geojson_store import append_feature
from participants import get_or_create_participant, participants_cache, reset_participants, save_participants
from judges import get_or_create_judge, judges_cache, save_judges, judges_lock
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

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,X-Device-Id')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

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
MIN_GPS_SAVE_INTERVAL_SECONDS = 1.5
PESO_RESET_CHECKPOINT_ID = 4
PESO_RESET_DISTANCE_METERS = 15.0
# Pesos asignados por la detección de pelotas
COLOR_WEIGHTS_KG = {"Rojo": 3.0, "Blanco": 1.0, "Negro": 5.0}
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
# Race Timer State
# ---------------------------------------------------------------------------
RACE_TIMES_STATE = {} # { "participante_01": {"start_time_ms": int | None, "elapsed_ms": int} }
_race_timer_lock = threading.Lock()

def get_current_race_time_ms(participante: str) -> int:
    with _race_timer_lock:
        state = RACE_TIMES_STATE.get(participante, {"start_time_ms": None, "elapsed_ms": 0})
        if state["start_time_ms"] is not None:
            return state["elapsed_ms"] + int(time.time() * 1000) - state["start_time_ms"]
        return state["elapsed_ms"]

@app.route("/api/race/start", methods=["POST"])
def start_race():
    data = request.json or {}
    participante = data.get("participante")
    if not participante:
        return jsonify({"status": "error", "msg": "Missing participante"}), 400
        
    with _race_timer_lock:
        state = RACE_TIMES_STATE.setdefault(participante, {"start_time_ms": None, "elapsed_ms": 0})
        if state["start_time_ms"] is None:
            state["start_time_ms"] = int(time.time() * 1000)
    return jsonify({"status": "started", "start_time": state["start_time_ms"], "participante": participante})

@app.route("/api/race/stop", methods=["POST"])
def stop_race():
    data = request.json or {}
    participante = data.get("participante")
    if not participante:
        return jsonify({"status": "error", "msg": "Missing participante"}), 400
        
    with _race_timer_lock:
        state = RACE_TIMES_STATE.get(participante)
        if state and state["start_time_ms"] is not None:
            state["elapsed_ms"] += int(time.time() * 1000) - state["start_time_ms"]
            state["start_time_ms"] = None
            elapsed = state["elapsed_ms"]
        else:
            elapsed = state["elapsed_ms"] if state else 0
    return jsonify({"status": "stopped", "elapsed": elapsed, "participante": participante})

@app.route("/api/race/state", methods=["GET"])
def race_state():
    states = {}
    with _race_timer_lock:
        for part, state in RACE_TIMES_STATE.items():
            elapsed = state["elapsed_ms"]
            if state["start_time_ms"] is not None:
                elapsed += int(time.time() * 1000) - state["start_time_ms"]
            states[part] = {
                "running": state["start_time_ms"] is not None,
                "elapsed_ms": elapsed
            }
    return jsonify(states)

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


def get_checkpoint_rank_value(runner: dict) -> tuple:
    return (
        runner.get("estado") != "terminado",
        -int(runner.get("cantidad_checkpoints_visitados", 0)),
        round(float(runner.get("distancia_checkpoint_pendiente_mas_cercano_m", float("inf"))), 2),
    )


def competition_rank(ranked_items, target_item, get_value_func) -> int:
    target_val = get_value_func(target_item)
    rank = 1
    for item in ranked_items:
        if get_value_func(item) < target_val:
            rank += 1
    return rank

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

def get_scoreboard_data() -> list[dict]:
    from Puntaje import (
        get_activity_points,
        get_challenges_percent,
        get_energy_percent,
        get_load_percent,
        get_puntaje_retos,
        get_team_id,
        get_team_name,
        get_time_percent,
        get_time_s,
        nombres_equipos_cache,
        puntajes_retos_lock,
    )
    scoreboard_list = []
    
    galeria = load_gallery_items()
    latest_images = {}
    todas_fotos_dict = {}
    for item in galeria:
        part = item.get("participante")
        if part:
            if part not in todas_fotos_dict:
                todas_fotos_dict[part] = []
            if item.get("filename"):
                todas_fotos_dict[part].append({
                    "filename": item.get("filename"),
                    "timestamp": item.get("timestamp")
                })

            if part not in latest_images or item.get("timestamp", 0) > latest_images[part].get("timestamp", 0):
                latest_images[part] = item

    with participants_lock:
        registered_entries = {
            entry.get("nombre"): entry 
            for entry in participants_cache.values() 
            if isinstance(entry, dict) and entry.get("nombre")
        }
        
    with puntajes_retos_lock:
        all_sheets_participants = set(nombres_equipos_cache.keys())
        
    all_participants = set(registered_entries.keys()).union(all_sheets_participants)

    for nombre in all_participants:
        entry = registered_entries.get(nombre, {})
        scores = entry.get("scores", {})
        
        total_local = sum(scores.values())
        puntaje_sheets = get_puntaje_retos(nombre)
        total_score = total_local + puntaje_sheets
        
        activity_points = get_activity_points(nombre)
        time_s = get_time_s(nombre)
        load_percent = get_load_percent(nombre)
        energy_percent = get_energy_percent(nombre)
        time_percent = get_time_percent(nombre)
        challenges_percent = get_challenges_percent(nombre)
        
        equipo_nombre = get_team_name(nombre)
        team_id = get_team_id(nombre)
        
        ultima_foto = latest_images[nombre].get("filename") if nombre in latest_images else None
        fotos_lista = todas_fotos_dict.get(nombre, [])
        
        scoreboard_list.append({
            "nombre": nombre,
            "equipo": equipo_nombre,
            "team_id": team_id,
            "Team": equipo_nombre,
            "Team ID": team_id,
            "Load (%)": round(load_percent, 2),
            "Energy (%)": round(energy_percent, 2),
            "Time (%)": round(time_percent, 2),
            "Challenges (%)": round(challenges_percent, 2),
            "Total (-/100)": round(puntaje_sheets, 2),
            "scores": scores,
            "total_score": round(total_score, 2),
            "puntaje_sheets": round(puntaje_sheets, 2),
            "activity_points": round(activity_points, 2),
            "time_s": round(time_s, 2),
            "race_elapsed_ms": get_current_race_time_ms(nombre),
            "ultima_foto": ultima_foto,
            "todas_fotos": fotos_lista,
            "peso_kg": round(safe_float(entry.get("peso_kg"), 0.0), 2),
            "peso_entregado_kg": round(safe_float(entry.get("peso_entregado_kg"), 0.0), 2),
        })
                
    scoreboard_list = sorted(scoreboard_list, key=lambda x: x["Total (-/100)"], reverse=True)
    for idx, row in enumerate(scoreboard_list, start=1):
        row["Rank"] = idx
    return scoreboard_list


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
@app.route("/scan")
def index():
    dist_dir = os.path.join(os.path.dirname(__file__), "tracker-app", "dist")
    resp = make_response(send_from_directory(dist_dir, "index.html"))
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


@app.route("/scoreboard")
def scoreboard():
    return render_template(
        "scoreboard.html",
        checkpoints=[{**checkpoint, "nombre": get_checkpoint_name(checkpoint)} for checkpoint in CHECKPOINTS],
        participantes=get_participants_for_view(),
    )

@app.route("/tracker")
def tracker():
    return render_template("tracker.html")


@app.route("/api/score", methods=["POST"])
def api_score():
    data = request.json or {}
    checkpoint_id = data.get("checkpoint_id")
    equipo = data.get("equipo")
    puntaje = data.get("puntaje")
    
    if not checkpoint_id or not equipo or puntaje is None:
        return jsonify({"status": "error", "msg": "Faltan datos"}), 400
        
    try:
        puntaje = float(puntaje)
        checkpoint_id_str = str(checkpoint_id)
    except ValueError:
        return jsonify({"status": "error", "msg": "Datos inválidos"}), 400

    target_device = None
    with participants_lock:
        for dev_id, entry in participants_cache.items():
            if isinstance(entry, dict) and entry.get("nombre") == equipo:
                target_device = dev_id
                break
                
        if target_device:
            participant_entry = participants_cache[target_device]
            participant_entry.setdefault("scores", {})[checkpoint_id_str] = puntaje
            save_participants(participants_cache)
            
            puntaje_retos_detalle = get_puntaje_retos_detalle(equipo)
            puntaje_retos_actual = puntaje_retos_detalle["puntaje_retos"]
            puntaje_retos_local = sum(participant_entry["scores"].values())
            total_puntaje = puntaje_retos_actual + puntaje_retos_local
            
            participant_entry["puntaje_retos"] = total_puntaje
            
            socketio.emit("update_puntaje", {
                "participante": equipo,
                "puntaje_retos": total_puntaje,
                "scores_dict": participant_entry["scores"]
            })
            return jsonify({"status": "ok"})
            
    return jsonify({"status": "error", "msg": "Team not found"}), 404


@app.route("/jurados")
def jurados():
    return render_template("jurados.html")


@app.route("/var")
def var_page():
    return render_template("var.html")


@app.route("/api/estado_participante/<participante_id>")
def estado_participante(participante_id):
    target_entry = {}
    with participants_lock:
        for dev_id, entry in participants_cache.items():
            if isinstance(entry, dict) and entry.get("nombre") == participante_id:
                target_entry = entry
                break
                
    return jsonify({
        "status": "ok",
        "participante": participante_id,
        "peso_kg": target_entry.get("peso_kg", 0),
        "carga_kg": target_entry.get("carga_kg", 0)
    })


@app.route("/api/registrar_peso", methods=["POST"])
def registrar_peso():
    data = request.json or {}
    participante = data.get("participante")
    peso_kg = data.get("peso_kg")
    
    if not participante or peso_kg is None:
        return jsonify({"status": "error", "msg": "Participante y peso son requeridos"}), 400
        
    try:
        peso_kg = float(peso_kg)
    except ValueError:
        return jsonify({"status": "error", "msg": "Peso inválido"}), 400

    # --- Integración con Google Sheets Webhook ---
    try:
        from config import GOOGLE_APPS_SCRIPT_WEBHOOK_URL
        import urllib.request
        import json
        from datetime import datetime
        import threading
        
        if GOOGLE_APPS_SCRIPT_WEBHOOK_URL:
            # Obtener datos detallados
            counts = data.get("counts", {})
            juez = data.get("juez", "Desconocido").replace("Judge_", "").replace("juez_", "")
            checkpoint_slug = data.get("checkpoint", "")
            
            # Formatear datos para el webhook
            payload = {
                "hora": datetime.now().strftime("%H:%M:%S"),
                "juez": juez,
                "checkpoint": checkpoint_slug,
                "equipo": participante.replace("Participante_", "") if participante else "",
                "blanca": counts.get("Blanco", 0),
                "roja": counts.get("Rojo", 0),
                "negra": counts.get("Negro", 0)
            }
            
            # Función para enviar en segundo plano a Google Sheets
            def send_webhook(url, payload_data):
                try:
                    try:
                        import requests
                        requests.post(url, json=payload_data, timeout=5, allow_redirects=True)
                    except ImportError:
                        import urllib.request
                        import json
                        req = urllib.request.Request(
                            url, 
                            data=json.dumps(payload_data).encode('utf-8'),
                            headers={'Content-Type': 'application/json'},
                            method='POST'
                        )
                        try:
                            urllib.request.urlopen(req, timeout=5)
                        except Exception as e:
                            # 302 is normal for google apps script
                            if hasattr(e, 'code') and e.code in [302, 303, 307, 308]:
                                pass
                            else:
                                print(f"Error HTTP urllib: {e}")
                except Exception as e:
                    print(f"Error enviando webhook a Google Sheets: {e}")
            
            # Iniciar hilo para no bloquear la respuesta
            threading.Thread(target=send_webhook, args=(GOOGLE_APPS_SCRIPT_WEBHOOK_URL, payload), daemon=True).start()
            
        # GUARDAR LOCALMENTE EN CSV SIEMPRE (Por si fallan las extensiones de Google)
        import csv
        import os
        csv_file = BASE_DIR / "registros_loading.csv"
        file_exists = os.path.isfile(csv_file)
        
        try:
            with open(csv_file, mode='a', newline='', encoding='utf-8') as f:
                counts = data.get("counts", {})
                juez = data.get("juez", "Desconocido").replace("Judge_", "").replace("juez_", "")
                equipo_nom = participante.replace("Participante_", "") if participante else ""
                
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["Fecha", "Hora", "Juez", "Checkpoint", "Equipo", "Blanca", "Roja", "Negra", "Carga_Kg"])
                writer.writerow([
                    datetime.now().strftime("%Y-%m-%d"),
                    datetime.now().strftime("%H:%M:%S"),
                    juez,
                    data.get("checkpoint", ""),
                    equipo_nom,
                    counts.get("Blanco", 0),
                    counts.get("Rojo", 0),
                    counts.get("Negro", 0),
                    peso_kg
                ])
        except Exception as e:
            print(f"Error guardando CSV local: {e}")
            
    except Exception as e:
        print(f"Error procesando webhook/CSV local: {e}")
    # ---------------------------------------------

    target_device = None
    with participants_lock:
        # Buscar participante por nombre o equipo
        for dev_id, entry in participants_cache.items():
            if isinstance(entry, dict) and entry.get("nombre") == participante:
                target_device = dev_id
                break
                
        if target_device:
            participant_entry = participants_cache[target_device]
            participant_entry["peso_kg"] = peso_kg
            participant_entry["carga_kg"] = peso_kg
            save_participants(participants_cache)
            
            socketio.emit("update_peso", {
                "participante": participante,
                "peso_kg": peso_kg
            })
            
    # Siempre retornamos OK para simular que se guardó exitosamente y se envió al excel
    return jsonify({"status": "ok"})


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
    scoreboard_data = get_scoreboard_data()
    runners_snapshot = {}
    with participants_lock:
        runners_snapshot = {
            get_participant_name_for_device(dev_id): {**state, "device_id": dev_id}
            for dev_id, state in participants_cache.items()
            if isinstance(state, dict) and "last_coord" in state
        }
        
        # Add latitude and longitude to match expected structure
        for state in runners_snapshot.values():
            if "last_coord" in state:
                state["latitude"] = state["last_coord"][0]
                state["longitude"] = state["last_coord"][1]
                state["carga_kg"] = state.get("peso_kg", 0)
        
    judges_list = []
    from judges import judges_cache
    for j_id, j_data in judges_cache.items():
        judges_list.append({
            "nombre": j_data.get("nombre", "Juez"),
            "checkpoint_id": j_data.get("checkpoint_id")
        })

    return jsonify({
        "checkpoints": [{**checkpoint, "nombre": get_checkpoint_name(checkpoint)} for checkpoint in CHECKPOINTS],
        "non_scoring_checkpoint_ids": [PESO_RESET_CHECKPOINT_ID],
        "participantes": get_participants_for_view(),
        "galeria": load_gallery_items(),
        "runners": runners_snapshot,
        "scoreboard": scoreboard_data,
        "judges": judges_list
    })

@app.route("/api/scoreboard", methods=["GET"])
def api_scoreboard():
    return jsonify({
        "participantes": get_scoreboard_data()
    })


@app.route("/api/scoreboard/csv", methods=["GET"])
def api_scoreboard_csv():
    import io
    import csv
    
    data = get_scoreboard_data()
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Escribir encabezados
    writer.writerow([
        "Posicion", "Participante", "Equipo", 
        "Carga Actual (kg)", "Carga Total Entregada (kg)", 
        "Puntos Retos", "Puntaje Total"
    ])
    
    # Escribir filas
    for idx, row in enumerate(data):
        writer.writerow([
            idx + 1,
            row.get("nombre", ""),
            row.get("equipo", ""),
            row.get("peso_kg", 0.0),
            row.get("peso_entregado_kg", 0.0),
            row.get("puntaje_sheets", 0.0),
            row.get("total_score", 0.0)
        ])
        
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=scoreboard.csv"}
    )
@app.route("/sw.js")
def service_worker():
    return send_from_directory("static", "sw.js")


@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json")


@app.route("/set_judge_checkpoint", methods=["POST"])
def set_judge_checkpoint():
    data = request.json or {}
    device_id, _, _ = get_device_info(data)
    checkpoint_id = data.get("checkpoint_id")
    
    if not device_id or not checkpoint_id:
        return jsonify({"status": "error", "msg": "Datos incompletos"}), 400
        
    try:
        checkpoint_id = int(checkpoint_id)
    except ValueError:
        return jsonify({"status": "error", "msg": "Checkpoint ID inválido"}), 400

    from config import judges_lock, MAX_JUECES_POR_CHECKPOINT
    from judges import judges_cache, save_judges, get_or_create_judge

    with judges_lock:
        # Primero aseguramos que el juez existe
        nombre_juez = get_or_create_judge(device_id)
        if not nombre_juez:
            return jsonify({"status": "error", "msg": "No se pudo registrar como juez"}), 403

        # Contar cuántos jueces ya están en este checkpoint
        jueces_en_cp = 0
        for j_id, j_data in judges_cache.items():
            if j_id != device_id and j_data.get("checkpoint_id") == checkpoint_id:
                jueces_en_cp += 1
                
        limite = 3 if checkpoint_id == 4 else MAX_JUECES_POR_CHECKPOINT
        if jueces_en_cp >= limite:
            return jsonify({"status": "error", "msg": f"El Checkpoint {checkpoint_id} ya tiene el máximo de {limite} jueces asignados."}), 403
            
        judges_cache[device_id]["checkpoint_id"] = checkpoint_id
        save_judges(judges_cache)
        
    return jsonify({"status": "ok", "msg": "Checkpoint confirmado correctamente."})

@app.route("/registrar", methods=["POST"])
def registrar():
    print("Recibida petición POST en /registrar")
    data = request.json or {}
    device_id, device_ip, user_agent = get_device_info(data)

    if "custom_name" in data:
        from config import participants_lock
        with participants_lock:
            custom = data["custom_name"].strip() if data["custom_name"] else ""
            if not custom:
                participante = get_or_create_participant(device_id)
            else:
                if device_id not in participants_cache:
                    if len(participants_cache) < MAX_PARTICIPANTES:
                        participants_cache[device_id] = {"nombre": custom, "lat": None, "lon": None}
                        save_participants(participants_cache)
                        participante = custom
                    else:
                        participante = None
                else:
                    participants_cache[device_id]["nombre"] = custom
                    save_participants(participants_cache)
                    participante = custom
    else:
        from config import judges_lock
        with judges_lock:
            participante = get_or_create_judge(device_id)

    if not participante:
        return jsonify({
            "status": "limite_participantes",
            "msg": f"Ya se alcanzó el límite de participantes o jueces.",
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
    client_participante = data.get("participante")

    with participants_lock:
        if client_participante and ("Judge" in client_participante or "Juez" in client_participante):
            from judges import judges_cache, save_judges
            if device_id not in judges_cache:
                judges_cache[device_id] = {"nombre": client_participante}
                save_judges(judges_cache)
            # NO lo agregamos al participants_cache y retornamos temprano
            return jsonify({
                "status": "ok", 
                "participante": client_participante, 
                "msg": "GPS ignorado para jueces"
            })
        else:
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
        
        participant_entry.setdefault("scores", {})
        puntaje_retos_local = sum(participant_entry["scores"].values())
        participant_entry["puntaje_retos"] = puntaje_retos_actual + puntaje_retos_local

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
        if "soc" in data and data["soc"] is not None:
            nivel_bateria = float(data["soc"])
            with _battery_lock:
                _battery_levels_by_device[device_id] = nivel_bateria
        else:
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
            "checkpoint_descarga_visitado": participant_entry.get("checkpoint_descarga_visitado", False),
            "blocked_by_challenge": participant_entry.get("blocked_by_challenge", False),
            "checkpoint_pendiente_mas_cercano": participant_entry.get("checkpoint_pendiente_mas_cercano"),
            "checkpoint_pendiente_mas_cercano_id": participant_entry.get("checkpoint_pendiente_mas_cercano_id"),
            "distancia_checkpoint_pendiente_mas_cercano_m": participant_entry.get("distancia_checkpoint_pendiente_mas_cercano_m"),
            "checkpoint_mas_cercano": participant_entry.get("checkpoint_mas_cercano"),
            "checkpoint_mas_cercano_id": participant_entry.get("checkpoint_mas_cercano_id"),
            "distancia_checkpoint_mas_cercano_m": participant_entry.get("distancia_checkpoint_mas_cercano_m"),
            "puntaje_retos": participant_entry.get("puntaje_retos", 0.0),
            "estado": estado_actual,
            "peso_kg": participant_entry.get("peso_kg", 0.0),
            "peso_entregado_kg": participant_entry.get("peso_entregado_kg", 0.0),
            "peso_descargado_kg": participant_entry.get("peso_descargado_kg", 0.0),
            "conteo_colores": participant_entry.get("conteo_colores", {color: 0 for color in COLOR_WEIGHTS_KG}),
            "color_detectado": participant_entry.get("color_detectado", []),
            "scores_dict": participant_entry.get("scores", {}),
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
    puntaje_retos = safe_float(checkpoint_state["puntaje_retos"])
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
            "posicion_checkpoints": posicion_checkpoints,
            "puntaje_retos": puntaje_retos,
            "puntaje_retos_total": puntaje_retos_detalle["puntaje_retos_total"],
            "puntaje_retos_equipo": puntaje_retos_detalle["puntaje_retos_equipo"],
            "puntaje_retos_origen": puntaje_retos_detalle["puntaje_retos_origen"],
            "puntaje_retos_lectura_ts": puntaje_retos_detalle["puntaje_retos_lectura_ts"],
            "peso_kg": checkpoint_state["peso_kg"],
            "peso_entregado_kg": checkpoint_state["peso_entregado_kg"],
            "peso_descargado_kg": checkpoint_state["peso_descargado_kg"],
            "checkpoints_visitados": checkpoint_state["checkpoints_visitados"],
            "checkpoints_visitados_txt": ",".join(
                str(checkpoint_id) for checkpoint_id in checkpoint_state["checkpoints_visitados"]
            ),
            "cantidad_checkpoints_visitados": checkpoint_state["cantidad_checkpoints_visitados"],
            "checkpoint_descarga_visitado": checkpoint_state["checkpoint_descarga_visitado"],
            "blocked_by_challenge": checkpoint_state.get("blocked_by_challenge", False),
            "checkpoint_pendiente_mas_cercano": checkpoint_state["checkpoint_pendiente_mas_cercano"],
            "checkpoint_pendiente_mas_cercano_id": checkpoint_state["checkpoint_pendiente_mas_cercano_id"],
            "distancia_checkpoint_pendiente_mas_cercano_m": checkpoint_state["distancia_checkpoint_pendiente_mas_cercano_m"],
            "checkpoint_mas_cercano": checkpoint_state["checkpoint_mas_cercano"],
            "checkpoint_mas_cercano_id": checkpoint_state["checkpoint_mas_cercano_id"],
            "distancia_checkpoint_mas_cercano_m": checkpoint_state["distancia_checkpoint_mas_cercano_m"],
            "estado": checkpoint_state["estado"],
            "scores_dict": checkpoint_state["scores_dict"],
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
            "motor_voltaje": data.get("motor_voltaje"),
            "motor_corriente": data.get("motor_corriente"),
            "motor_potencia": data.get("motor_potencia"),
            "motor_rpm": data.get("motor_rpm"),
            "motor_temp": data.get("motor_temp"),
            "ah_consumidos": data.get("ah_consumidos")
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
        f"retos={puntaje_retos:.2f} "
        f"puntaje_retos={puntaje_retos:.2f}"
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
        "puntaje_retos": puntaje_retos,
        "estado": checkpoint_state["estado"],
        "peso_kg": checkpoint_state["peso_kg"],
        "peso_entregado_kg": checkpoint_state["peso_entregado_kg"],
        "peso_descargado_kg": checkpoint_state["peso_descargado_kg"],
        "checkpoints_visitados": checkpoint_state["cantidad_checkpoints_visitados"],
        "checkpoints_visitados_lista": checkpoint_state["checkpoints_visitados"],
        "checkpoints_visitados_txt": ",".join(
            str(checkpoint_id) for checkpoint_id in checkpoint_state["checkpoints_visitados"]
        ),
        "checkpoint_descarga_visitado": checkpoint_state["checkpoint_descarga_visitado"],
        "blocked_by_challenge": checkpoint_state.get("blocked_by_challenge", False),
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
        "scores_dict": checkpoint_state["scores_dict"],
        # ── Telemetría eléctrica (Raspberry / Bicicleta Relieve) ──────────────
        "voltaje":         data.get("voltaje"),
        "corriente":       data.get("corriente"),
        "potencia":        data.get("potencia"),
        "soc":             data.get("soc"),
        "ttg_min":         data.get("ttg_min"),
        "ah_consumidos":   data.get("ah_consumidos"),
        "motor_voltaje":   data.get("motor_voltaje"),
        "motor_corriente": data.get("motor_corriente"),
        "motor_potencia":  data.get("motor_potencia"),
        "motor_rpm":       data.get("motor_rpm"),
        "motor_temp":      data.get("motor_temp"),
    })

    response = {
        "status": "ok",
        "participante": participante,
        "nivel_bateria": nivel_bateria,
        "posicion_inicial": posicion_inicial,
        "posicion": posicion,
        "posicion_checkpoints": posicion_checkpoints,
        "puntaje_retos": puntaje_retos,
        "peso_kg": checkpoint_state["peso_kg"],
        "peso_entregado_kg": checkpoint_state["peso_entregado_kg"],
        "peso_descargado_kg": checkpoint_state["peso_descargado_kg"],
        "checkpoints_visitados": checkpoint_state["checkpoints_visitados"],
        "cantidad_checkpoints_visitados": checkpoint_state["cantidad_checkpoints_visitados"],
        "checkpoint_descarga_visitado": checkpoint_state["checkpoint_descarga_visitado"],
        "blocked_by_challenge": checkpoint_state.get("blocked_by_challenge", False),
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
        "scores_dict": checkpoint_state["scores_dict"],
    }
    
    # Send telemetry to RelieVeasy Web App
    try:
        import urllib.request
        import json
        import threading
        
        telemetry_payload = {
            "device_id": device_id,
            "participante": participante,
            "latitude": latitude,
            "longitude": longitude,
            "speed_kmh": data.get("speed_kmh", 0),
            "nivel_bateria": nivel_bateria
        }
        def send_telemetry():
            try:
                req = urllib.request.Request(
                    "http://localhost:3000/api/webhook/telemetry", 
                    data=json.dumps(telemetry_payload).encode('utf-8'),
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                urllib.request.urlopen(req, timeout=3)
            except Exception as e:
                pass
        
        threading.Thread(target=send_telemetry, daemon=True).start()
    except Exception:
        pass

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

        gp_max_w = 1280
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
        import judges
        
        participante_nombre = data.get("participante")
        if not participante_nombre or participante_nombre == "Desconocido":
            participante_nombre = get_participant_name_for_device(device_id)

        dt_now = datetime.now()
        fecha_hora = dt_now.strftime("%Y-%m-%d %H:%M:%S")
        
        # Obtener el nombre del juez asignado a este dispositivo
        nombre_juez = judges.get_or_create_judge(device_id) or "Desconocido"
        checkpoint_nombre = data.get("checkpoint_nombre", "")
        
        # Imprimir la marca de agua (Juez, Checkpoint y Timestamp) en la imagen
        watermark_text = f"Judge: {nombre_juez} | {fecha_hora}"
        cv2.putText(frame_annotated, watermark_text, (20, frame_annotated.shape[0] - 20), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)

        jpeg_q = 35
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_q]
        _, buffer = cv2.imencode(".jpg", frame_annotated, encode_params)
        annotated_b64 = base64.b64encode(buffer).decode("utf-8")

        if detectado and "color" in detectado:
            checkpoint_id_req = data.get("checkpoint_id", 0)
            checkpoint_context = None

            if checkpoint_id_req > 0:
                for checkpoint in CHECKPOINTS:
                    if int(checkpoint["id"]) == checkpoint_id_req:
                        checkpoint_context = {
                            "checkpoint_id": checkpoint_id_req,
                            "checkpoint_nombre": get_checkpoint_name(checkpoint),
                            "checkpoint_slug": f"checkpoint_{checkpoint_id_req}",
                            "distancia_checkpoint_m": 0.0
                        }
                        break
            
            if not checkpoint_context:
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
                "juez": nombre_juez,
                "detections": detectado["counts"]
            }
            gallery_item.update(checkpoint_context)
            galeria_data.append(gallery_item)

            with open(registro_galeria, "w", encoding="utf-8") as f:
                json.dump(galeria_data, f, indent=4)
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
    participante = request.args.get("participante")
    items = load_gallery_items()
    if participante:
        items = [item for item in items if item.get("participante") == participante]
    return jsonify(items)

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

        gp_max_w = 1280  # Aumentado para mejor resolución (720p)
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

@app.route("/<path:path>")
def static_proxy(path):
    dist_dir = os.path.join(os.path.dirname(__file__), "tracker-app", "dist")
    if os.path.exists(os.path.join(dist_dir, path)):
        return send_from_directory(dist_dir, path)
    return "Not Found", 404

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

# ==========================================
# SERVIDOR WEB DE LA CÁMARA (SIMPLIFICACIÓN)
# ==========================================
TRACKER_DIST = BASE_DIR / "tracker-app" / "dist"

@app.route('/scan')
@app.route('/scan/')
def serve_scanner_app():
    """Sirve la aplicación de la cámara compilada en la web"""
    index_path = TRACKER_DIST / "index.html"
    if index_path.exists():
        return send_file(str(index_path))
    return "La cámara web aún no ha sido compilada. Por favor, ejecuta 'npx expo export:web' dentro de la carpeta tracker-app.", 404

@app.route('/mapa')
@app.route('/mapa/')
def serve_mapa():
    """Muestra el mapa de seguimiento GPS"""
    return render_template('mapa.html')

import requests
from flask import Response

@app.route('/scoreboard')
@app.route('/scoreboard/')
def serve_scoreboard_html():
    """Restaura el scoreboard clásico de Python, sin tocar RelieVeasy"""
    return render_template('scoreboard.html')

@app.route('/<path:filename>')
def serve_static_files(filename):
    """Sirve los archivos JS/CSS/Imágenes de la aplicación de la cámara"""
    file_path = TRACKER_DIST / filename
    if file_path.exists():
        return send_file(str(file_path))
    return "Not Found", 404

if __name__ == "__main__":
    import threading
    from Puntaje import sincronizar_puntajes
    
    # Iniciar la sincronización de puntajes en segundo plano para reflejar los cambios del excel
    threading.Thread(target=sincronizar_puntajes, daemon=True).start()
    
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
