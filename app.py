import time
import hashlib
import random
import threading
import urllib.error

from flask import Flask, request, jsonify, render_template

from config import MAX_PARTICIPANTES, DURACION, participants_lock
from geojson_store import append_feature
from participants import participants_cache, get_or_create_participant, save_participants
from checkpoints import actualizar_estado_corredor, clasificar_corredores
from arcgis import (
    arcgis_enabled,
    send_feature_to_arcgis,
    should_send_to_arcgis,
    ARCGIS_FEATURE_LAYER_URL,
    ARCGIS_TOKEN,
    ARCGIS_CLIENT_ID,
    ARCGIS_CLIENT_SECRET,
    ARCGIS_THROTTLE_SECONDS,
)

app = Flask(__name__)

inicio = time.time()
_battery_levels_by_device: dict[str, float] = {}
_battery_lock = threading.Lock()
MAX_BATTERY_SCORE = 50.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_device_info(data: dict) -> tuple[str, str, str]:
    user_agent = request.headers.get("User-Agent", "")
    device_ip  = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    device_id  = data.get("device_id")

    if not device_id:
        fingerprint = f"{device_ip}|{user_agent}"
        device_id   = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]

    return device_id, device_ip, user_agent


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


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

    if highest_battery <= 0:
        return 0.0

    return clamp((nivel_bateria / highest_battery) * MAX_BATTERY_SCORE, 0.0, MAX_BATTERY_SCORE)


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

    try:
        return ranked_devices.index(device_id) + 1
    except ValueError:
        return None


def get_checkpoint_rank_from_snapshot(device_id: str, runners_snapshot: dict) -> int | None:
    ranked_runners = clasificar_corredores(runners_snapshot)
    for index, runner in enumerate(ranked_runners, start=1):
        if runner.get("device_id") == device_id:
            return index
    return None


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/registrar", methods=["POST"])
def registrar():
    data = request.json or {}
    device_id, device_ip, user_agent = get_device_info(data)

    with participants_lock:
        participante = get_or_create_participant(device_id)

    if not participante:
        return jsonify({
            "status": "limite_participantes",
            "msg":    f"Ya se alcanzó el límite de {MAX_PARTICIPANTES} participantes.",
        }), 403

    return jsonify({
        "status":            "ok",
        "participante":      participante,
        "device_id":         device_id,
        "device_label":      data.get("device_label") or f"Dispositivo-{device_id[:8]}",
        "device_ip":         device_ip,
        "device_user_agent": user_agent,
    })


@app.route("/arcgis/status")
def arcgis_status():
    return jsonify({
        "enabled":                     arcgis_enabled(),
        "feature_layer_url_configured": bool(ARCGIS_FEATURE_LAYER_URL),
        "auth_configured":              bool(ARCGIS_TOKEN or (ARCGIS_CLIENT_ID and ARCGIS_CLIENT_SECRET)),
        "auth_mode":                    "token" if ARCGIS_TOKEN else ("oauth2" if ARCGIS_CLIENT_ID and ARCGIS_CLIENT_SECRET else "none"),
        "throttle_seconds":             ARCGIS_THROTTLE_SECONDS,
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
            "msg":    f"Ya se alcanzó el límite de {MAX_PARTICIPANTES} participantes.",
        }), 403

    latitude = float(data["latitude"])
    longitude = float(data["longitude"])

    nivel_bateria = get_next_battery_level(device_id)
    posicion_inicial = get_participant_position(participante)
    puntaje_bateria = get_battery_score(nivel_bateria)
    posicion_bateria = get_battery_rank(device_id)

    with participants_lock:
        participant_entry = participants_cache[device_id]
        participant_entry["device_id"] = device_id
        participant_entry["nombre"] = participante
        actualizar_estado_corredor(participant_entry, latitude, longitude)
        save_participants(participants_cache)

        checkpoint_state = {
            "checkpoints_visitados": participant_entry.get("checkpoints_visitados", []),
            "cantidad_checkpoints_visitados": participant_entry.get("cantidad_checkpoints_visitados", 0),
            "checkpoint_pendiente_mas_cercano": participant_entry.get("checkpoint_pendiente_mas_cercano"),
            "checkpoint_pendiente_mas_cercano_id": participant_entry.get("checkpoint_pendiente_mas_cercano_id"),
            "distancia_checkpoint_pendiente_mas_cercano_m": participant_entry.get("distancia_checkpoint_pendiente_mas_cercano_m"),
            "puntuacion_checkpoints": participant_entry.get("puntuacion_checkpoints", 0.0),
            "puntaje_checkpoints": participant_entry.get("puntaje_checkpoints", 0.0),
            "estado": participant_entry.get("estado", "corriendo"),
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
    puntaje_checkpoints = checkpoint_state["puntaje_checkpoints"]
    puntaje = round(puntaje_bateria + puntaje_checkpoints, 2)
    posicion = posicion_checkpoints

    feature = {
        "type": "Feature",
        "geometry": {
            "type":        "Point",
            "coordinates": [longitude, latitude],
        },
        "properties": {
            "timestamp":           time.strftime("%Y-%m-%d %H:%M:%S"),
            "accuracy":            data.get("accuracy"),
            "altitude":            data.get("altitude"),
            "altitude_accuracy":   data.get("altitude_accuracy"),
            "heading":             data.get("heading"),
            "nivel_bateria":       nivel_bateria,
            "posicion_inicial":    posicion_inicial,
            "posicion":            posicion,
            "posicion_bateria":    posicion_bateria,
            "posicion_checkpoints": posicion_checkpoints,
            "puntaje_bateria":     puntaje_bateria,
            "puntaje_checkpoints":  puntaje_checkpoints,
            "puntaje":             puntaje,
            "puntuacion_checkpoints": checkpoint_state["puntuacion_checkpoints"],
            "checkpoints_visitados": checkpoint_state["checkpoints_visitados"],
            "checkpoints_visitados_txt": ",".join(
                str(checkpoint_id) for checkpoint_id in checkpoint_state["checkpoints_visitados"]
            ),
            "cantidad_checkpoints_visitados": checkpoint_state["cantidad_checkpoints_visitados"],
            "checkpoint_pendiente_mas_cercano": checkpoint_state["checkpoint_pendiente_mas_cercano"],
            "checkpoint_pendiente_mas_cercano_id": checkpoint_state["checkpoint_pendiente_mas_cercano_id"],
            "distancia_checkpoint_pendiente_mas_cercano_m": checkpoint_state["distancia_checkpoint_pendiente_mas_cercano_m"],
            "estado":              checkpoint_state["estado"],

            # Velocidad (sensor GPS o calculada por Haversine en el cliente)
            "speed_mps":           data.get("speed_mps"),
            "speed_kmh":           data.get("speed_kmh"),
            "speed_source":        data.get("speed_source"),

            # Acelerómetro con gravedad
            "accel_gx":            data.get("accel_gx"),
            "accel_gy":            data.get("accel_gy"),
            "accel_gz":            data.get("accel_gz"),
            "accel_g_magnitude":   data.get("accel_g_magnitude"),
            "acceleration_mps2":   data.get("acceleration_mps2"),

            # Metadatos del sensor
            "accel_interval_ms":       data.get("accel_interval_ms"),
            "accel_supported":         data.get("accel_supported"),
            "accel_permission_state":  data.get("accel_permission_state"),
            "sensor_timestamp_ms":     data.get("sensor_timestamp_ms"),
            "client_timestamp_ms":     data.get("client_timestamp_ms"),

            "participante":        participante,
            "device_id":           device_id,
            "device_label":        data.get("device_label") or f"Dispositivo-{device_id[:8]}",
            "device_ip":           device_ip,
            "device_user_agent":   user_agent,
        },
    }

    # Guardar SIEMPRE en GeoJSON local (historial completo)
    append_feature(feature)

    print(
        f"[GPS] {participante} {feature['properties']['device_label']} "
        f"{data['latitude']}, {data['longitude']} "
        f"vel={data.get('speed_kmh', 'N/A')} km/h ({data.get('speed_source', '')}) "
        f"accel={data.get('acceleration_mps2', '-')} m/s2 "
        f"bateria={nivel_bateria:.2f}% "
        f"posicion_inicial={posicion_inicial} "
        f"posicion={posicion} "
        f"estado={checkpoint_state['estado']} "
        f"checkpoints={checkpoint_state['cantidad_checkpoints_visitados']} "
        f"puntaje={puntaje:.2f} "
        f"(+/-{data.get('accuracy', '')}m)"
    )

    # Enviar a ArcGIS con throttling (1 punto fijo por participante)
    arcgis_sent            = False
    arcgis_skipped_throttle = False
    arcgis_error           = None

    if should_send_to_arcgis(participante):
        try:
            arcgis_response = send_feature_to_arcgis(feature, participante, participants_cache, save_participants)
            arcgis_sent = bool(arcgis_response.get("enabled"))
            if arcgis_sent:
                print(f"[ArcGIS] {arcgis_response.get('action')} -> {participante} (OBJECTID={arcgis_response.get('object_id')})")
        except (urllib.error.URLError, TimeoutError, RuntimeError, KeyError, ValueError) as exc:
            arcgis_error = str(exc)
            print(f"[ArcGIS] Error al enviar punto de {participante}: {arcgis_error}")
    else:
        arcgis_skipped_throttle = True

    response = {
        "status":                 "ok",
        "participante":           participante,
        "nivel_bateria":          nivel_bateria,
        "posicion_inicial":       posicion_inicial,
        "posicion":               posicion,
        "posicion_bateria":       posicion_bateria,
        "posicion_checkpoints":    posicion_checkpoints,
        "puntaje_bateria":        puntaje_bateria,
        "puntaje_checkpoints":     puntaje_checkpoints,
        "puntaje":                puntaje,
        "puntuacion_checkpoints":  checkpoint_state["puntuacion_checkpoints"],
        "checkpoints_visitados":   checkpoint_state["checkpoints_visitados"],
        "cantidad_checkpoints_visitados": checkpoint_state["cantidad_checkpoints_visitados"],
        "checkpoint_pendiente_mas_cercano": checkpoint_state["checkpoint_pendiente_mas_cercano"],
        "distancia_checkpoint_pendiente_mas_cercano_m": checkpoint_state["distancia_checkpoint_pendiente_mas_cercano_m"],
        "estado":                 checkpoint_state["estado"],
        "arcgis_sent":            arcgis_sent,
        "arcgis_skipped_throttle": arcgis_skipped_throttle,
    }
    if arcgis_error:
        response["arcgis_error"] = arcgis_error

    return jsonify(response)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
