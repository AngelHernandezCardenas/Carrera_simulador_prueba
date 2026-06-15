import time
import hashlib
import urllib.error

from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_socketio import SocketIO
from config import MAX_PARTICIPANTES, DURACION, participants_lock
from geojson_store import append_feature
from participants import participants_cache, get_or_create_participant, save_participants

import math

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

inicio = time.time()

# Diccionario en memoria para las estadisticas de la carrera
runners_stats = {}

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0 # Radio de la Tierra en km
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c


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


@app.route("/mapa")
def mapa():
    return render_template("mapa.html")


@app.route("/sw.js")
def service_worker():
    return send_from_directory("static", "sw.js")


@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json")


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
            "Date_GPS":            time.strftime("%Y-%m-%d %H:%M:%S"),
            "accuracy":            data.get("accuracy"),
            "altitude":            data.get("altitude"),
            "altitude_accuracy":   data.get("altitude_accuracy"),
            "heading":             data.get("heading"),

            # Velocidad (sensor GPS o calculada por Haversine en el cliente)
            "speed_mps":           data.get("speed_mps"),
            "speed_kmh":           data.get("speed_kmh"),
            "speed_source":        data.get("speed_source"),

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

    # Actualizar estadisticas en memoria
    lat = data["latitude"]
    lon = data["longitude"]
    # Sanitizar velocidad por si el cliente envia 'null'
    vel = data.get("speed_kmh")
    vel = float(vel) if vel is not None else 0.0

    if participante not in runners_stats:
        runners_stats[participante] = {
            "distancia_km": 0.0,
            "max_speed": vel,
            "last_coord": (lat, lon)
        }
    else:
        stats = runners_stats[participante]
        last_lat, last_lon = stats["last_coord"]
        dist_incremental = haversine(last_lat, last_lon, lat, lon)
        
        # Ignorar "saltos" anomalos grandes (ej. > 1km en un segundo) si fuera necesario, aqui lo sumamos normal
        if dist_incremental > 0.001: # Mas de 1 metro
            stats["distancia_km"] += dist_incremental
            stats["last_coord"] = (lat, lon)
        
        if vel > stats["max_speed"]:
            stats["max_speed"] = vel

    print(
        f"[GPS] {participante} {feature['properties']['device_label']} "
        f"{lat}, {lon} | Distancia: {runners_stats[participante]['distancia_km']:.3f} km"
    )

    # Emitir el punto a través de WebSockets para el mapa y la tabla
    socketio.emit('nueva_posicion', {
        'participante': participante,
        'latitude': lat,
        'longitude': lon,
        'velocidad': vel,
        'distancia_km': runners_stats[participante]['distancia_km'],
        'max_speed': runners_stats[participante]['max_speed']
    })

    return jsonify({
        "status": "ok",
        "participante": participante
    })



# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
