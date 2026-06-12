import time
import hashlib
import urllib.error

from flask import Flask, request, jsonify, render_template

from config import MAX_PARTICIPANTES, DURACION, participants_lock
from geojson_store import append_feature
from participants import participants_cache, get_or_create_participant, save_participants
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

    feature = {
        "type": "Feature",
        "geometry": {
            "type":        "Point",
            "coordinates": [data["longitude"], data["latitude"]],
        },
        "properties": {
            "timestamp":           time.strftime("%Y-%m-%d %H:%M:%S"),
            "accuracy":            data.get("accuracy"),
            "altitude":            data.get("altitude"),
            "altitude_accuracy":   data.get("altitude_accuracy"),
            "heading":             data.get("heading"),

            # Velocidad (sensor GPS o calculada por Haversine en el cliente)
            "speed_mps":           data.get("speed_mps"),
            "speed_kmh":           data.get("speed_kmh"),
            "speed_source":        data.get("speed_source"),

            # Acelerómetro sin gravedad
            "accel_x":             data.get("accel_x"),
            "accel_y":             data.get("accel_y"),
            "accel_z":             data.get("accel_z"),
            "accel_magnitude":     data.get("accel_magnitude"),

            # Acelerómetro con gravedad
            "accel_gx":            data.get("accel_gx"),
            "accel_gy":            data.get("accel_gy"),
            "accel_gz":            data.get("accel_gz"),
            "accel_g_magnitude":   data.get("accel_g_magnitude"),

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
        f"accel=({data.get('accel_x', '-')}, {data.get('accel_y', '-')}, {data.get('accel_z', '-')}) "
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
