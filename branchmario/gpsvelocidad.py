from flask import Flask, request, jsonify
from dotenv import load_dotenv
import json
import os
import time
import threading
import hashlib
import urllib.parse
import urllib.request
import urllib.error

# Carga las variables del archivo .env (si existe)
load_dotenv()

app = Flask(__name__)

GEOJSON_FILE = "gps_data.geojson"
PARTICIPANTS_FILE = "participantes.json"
MAX_PARTICIPANTES = 20

# --- VARIABLES DE ENTORNO PARA OAUTH 2.0 (cargadas desde .env) ---
ARCGIS_FEATURE_LAYER_URL = (os.getenv("ARCGIS_FEATURE_LAYER_URL") or "").strip()
ARCGIS_TOKEN = (os.getenv("ARCGIS_TOKEN") or "").strip()
ARCGIS_CLIENT_ID = (os.getenv("ARCGIS_CLIENT_ID") or "").strip()
ARCGIS_CLIENT_SECRET = (os.getenv("ARCGIS_CLIENT_SECRET") or "").strip()
ARCGIS_TOKEN_URL = (os.getenv("ARCGIS_TOKEN_URL") or "https://www.arcgis.com/sharing/rest/oauth2/token").strip()
ARCGIS_TIMEOUT = int(os.getenv("ARCGIS_TIMEOUT") or "10")

file_lock = threading.Lock()
participants_lock = threading.Lock()
arcgis_lock = threading.Lock()
arcgis_cached_token = {"token": ARCGIS_TOKEN, "expires_at": 0}

def init_geojson():
    with open(GEOJSON_FILE, "w") as f:
        json.dump({"type": "FeatureCollection", "features": []}, f)

def load_geojson():
    try:
        with open(GEOJSON_FILE, "r") as f:
            content = f.read().strip()
            if not content:
                raise ValueError("Archivo vacío")
            return json.loads(content)
    except (json.JSONDecodeError, ValueError, FileNotFoundError):
        # Si está corrupto o vacío, reiniciar
        init_geojson()
        return {"type": "FeatureCollection", "features": []}

def load_participants():
    try:
        with open(PARTICIPANTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_participants(participants):
    with open(PARTICIPANTS_FILE, "w", encoding="utf-8") as f:
        json.dump(participants, f, indent=2)

def arcgis_enabled():
    # Valida si existe un token manual o las credenciales OAuth 2.0
    return bool(ARCGIS_FEATURE_LAYER_URL and (ARCGIS_TOKEN or (ARCGIS_CLIENT_ID and ARCGIS_CLIENT_SECRET)))

def arcgis_endpoint(action):
    url = ARCGIS_FEATURE_LAYER_URL.rstrip("/")
    if url.endswith(f"/{action}"):
        return url
    return f"{url}/{action}"

def post_arcgis_form(url, params):
    encoded = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    with urllib.request.urlopen(req, timeout=ARCGIS_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))

def get_arcgis_token():
    if ARCGIS_TOKEN:
        return ARCGIS_TOKEN

    now_ms = int(time.time() * 1000)
    with arcgis_lock:
        if arcgis_cached_token["token"] and arcgis_cached_token["expires_at"] - now_ms > 60000:
            return arcgis_cached_token["token"]

        # Payload actualizado para usar Client Credentials Grant de OAuth 2.0
        token_data = post_arcgis_form(ARCGIS_TOKEN_URL, {
            "client_id": ARCGIS_CLIENT_ID,
            "client_secret": ARCGIS_CLIENT_SECRET,
            "grant_type": "client_credentials"
        })

        if "error" in token_data:
            raise RuntimeError(token_data["error"].get("message", "No se pudo obtener token OAuth2 de ArcGIS"))

        # La respuesta OAuth2 retorna 'access_token' y 'expires_in' (en segundos, usualmente 7200)
        access_token = token_data.get("access_token")
        expires_in_sec = token_data.get("expires_in", 7200)

        if not access_token:
            raise RuntimeError("Respuesta de token inesperada desde ArcGIS")

        arcgis_cached_token["token"] = access_token
        # Convertimos los segundos a milisegundos para sumarlos a la marca de tiempo actual
        arcgis_cached_token["expires_at"] = now_ms + (expires_in_sec * 1000)
        
        return arcgis_cached_token["token"]

def feature_to_arcgis(feature):
    lon, lat = feature["geometry"]["coordinates"]
    return {
        "geometry": {
            "x": lon,
            "y": lat,
            "spatialReference": {"wkid": 4326}
        },
        "attributes": feature["properties"]
    }

def send_feature_to_arcgis(feature):
    if not arcgis_enabled():
        return {"enabled": False}

    params = {
        "f": "json",
        "features": json.dumps([feature_to_arcgis(feature)])
    }
    token = get_arcgis_token()
    if token:
        params["token"] = token

    result = post_arcgis_form(arcgis_endpoint("addFeatures"), params)

    if "error" in result:
        raise RuntimeError(result["error"].get("message", "Error de ArcGIS"))

    add_results = result.get("addResults", [])
    if add_results and not add_results[0].get("success"):
        error = add_results[0].get("error", {})
        raise RuntimeError(error.get("description") or error.get("message") or "ArcGIS rechazo el punto")

    return {"enabled": True, "result": result}

participants_cache = load_participants()

def get_or_create_participant(device_id):
    if not device_id:
        return None

    if device_id in participants_cache:
        return participants_cache[device_id]

    if len(participants_cache) >= MAX_PARTICIPANTES:
        return None

    participant = f"participante_{len(participants_cache) + 1:02d}"
    participants_cache[device_id] = participant
    save_participants(participants_cache)

    return participant

# Inicializar si no existe
if not os.path.exists(GEOJSON_FILE):
    init_geojson()

@app.route("/")
def index():
    return """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GPS Tracker</title>
    <style>
        body { font-family: sans-serif; max-width: 400px; margin: 40px auto; padding: 20px; }
        button { padding: 14px 28px; font-size: 16px; cursor: pointer; border-radius: 8px;
                 border: none; background: #2563eb; color: white; width: 100%; }
        button:disabled { background: #93c5fd; cursor: not-allowed; }
        #estado { margin-top: 20px; padding: 14px; border-radius: 8px;
                  background: #f1f5f9; font-size: 14px; white-space: pre-line; }
        .ok    { background: #dcfce7 !important; color: #166534; }
        .error { background: #fee2e2 !important; color: #991b1b; }
    </style>
</head>
<body>
    <h2>GPS Tracker</h2>
    <button id="btn" onclick="iniciar()">Iniciar captura</button>
    <div id="estado">Esperando...</div>

<script>
    let intervalo = null;
    let activo = false;
    let participante = null;
    let ultimaPosicion = null; // Se usa para calcular velocidad si el GPS no entrega speed
    const DEVICE_ID_KEY = "gps_tracker_device_id";

    function getDeviceId() {
        let deviceId = localStorage.getItem(DEVICE_ID_KEY);

        if (!deviceId) {
            if (window.crypto && crypto.randomUUID) {
                deviceId = crypto.randomUUID();
            } else {
                deviceId = "dev-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
            }

            localStorage.setItem(DEVICE_ID_KEY, deviceId);
        }

        return deviceId;
    }

    function getDeviceLabel(deviceId) {
        const platform = navigator.userAgentData?.platform || navigator.platform || "Dispositivo";
        return `${platform}-${deviceId.slice(0, 8)}`;
    }

    async function registrarParticipante() {
        const deviceId = getDeviceId();
        const resp = await fetch("/registrar", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                device_id: deviceId,
                device_label: getDeviceLabel(deviceId)
            })
        });
        const data = await resp.json();

        if (!resp.ok || data.status !== "ok") {
            throw new Error(data.msg || "No se pudo registrar el dispositivo.");
        }

        participante = data.participante;
        log(`${participante} asignado.\\nListo para iniciar captura.`, "ok");
    }

    function log(msg, tipo) {
        const el = document.getElementById("estado");
        el.textContent = msg;
        el.className = tipo || "";
    }

    function toNumberOrNull(value) {
        return Number.isFinite(value) ? value : null;
    }

    function distanciaHaversineMetros(lat1, lon1, lat2, lon2) {
        const R = 6371000; // Radio aproximado de la Tierra en metros
        const rad = Math.PI / 180;
        const dLat = (lat2 - lat1) * rad;
        const dLon = (lon2 - lon1) * rad;
        const a =
            Math.sin(dLat / 2) ** 2 +
            Math.cos(lat1 * rad) * Math.cos(lat2 * rad) *
            Math.sin(dLon / 2) ** 2;

        return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    function calcularVelocidad(lat, lon, timestampMs, gpsSpeedMps) {
        // Primero intenta usar la velocidad nativa del GPS del teléfono
        let speedMps = toNumberOrNull(gpsSpeedMps);
        let speedSource = "gps_sensor";

        // Si el navegador no entrega speed, se calcula con distancia / tiempo
        if (speedMps === null && ultimaPosicion) {
            const distancia = distanciaHaversineMetros(
                ultimaPosicion.lat,
                ultimaPosicion.lon,
                lat,
                lon
            );
            const deltaTiempoSeg = (timestampMs - ultimaPosicion.timestampMs) / 1000;

            if (deltaTiempoSeg > 0) {
                speedMps = distancia / deltaTiempoSeg;
                speedSource = "calculada_distancia_tiempo";
            }
        }

        ultimaPosicion = { lat, lon, timestampMs };

        return {
            speed_mps: speedMps,
            speed_kmh: speedMps === null ? null : speedMps * 3.6,
            speed_source: speedSource
        };
    }

    function iniciar() {
        if (!navigator.geolocation) {
            log("Geolocalización no soportada en este navegador.", "error");
            return;
        }
        if (!participante) {
            log("Registrando participante, intenta de nuevo en un momento.", "error");
            registrarParticipante().catch(function(error) {
                log(error.message, "error");
            });
            return;
        }
        if (activo) {
            clearInterval(intervalo);
            activo = false;
            document.getElementById("btn").textContent = "Iniciar captura";
            log(" Captura detenida.");
            return;
        }
        activo = true;
        document.getElementById("btn").textContent = "Detener captura";
        log("Obteniendo ubicación...");
        capturar();
        intervalo = setInterval(capturar, 1000);
    }

    function capturar() {
        navigator.geolocation.getCurrentPosition(
            async function(pos) {
                const lat = pos.coords.latitude;
                const lon = pos.coords.longitude;
                const acc = pos.coords.accuracy;

                log(
                    `Ubicación obtenida\\n` +
                    `Lat: ${lat.toFixed(6)}\\nLon: ${lon.toFixed(6)}\\n` +
                    `Precisión: ±${acc.toFixed(0)} m\\n` +
                    `Hora: ${new Date().toLocaleTimeString()}`,
                    "ok"
                );

                try {
                    const deviceId = getDeviceId();
                    const resp = await fetch("/gps", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            latitude: lat,
                            longitude: lon,
                            accuracy: acc,
                            device_id: deviceId,
                            device_label: getDeviceLabel(deviceId)
                        })
                    });
                    const data = await resp.json();

                    if (!resp.ok && data.status !== "limite_participantes") {
                        throw new Error(data.msg || `Error del servidor: ${resp.status}`);
                    }

                    if (data.status === "cerrado") {
                        clearInterval(intervalo);
                        activo = false;
                        document.getElementById("btn").textContent = "Iniciar captura";
                        log("Sesión terminada por el servidor (límite de tiempo alcanzado).", "error");
                    } else if (data.status === "limite_participantes") {
                        clearInterval(intervalo);
                        activo = false;
                        document.getElementById("btn").textContent = "Iniciar captura";
                        log(data.msg, "error");
                    } else if (data.participante) {
                        participante = data.participante;
                    }
                } catch(e) {
                    log("GPS obtenido pero error al enviar al servidor:\\n" + e.message, "error");
                }
            },
            function(error) {
                const mensajes = {
                    1: "Permiso denegado por el usuario.",
                    2: "Posición no disponible (GPS apagado o sin señal).",
                    3: "Tiempo de espera agotado."
                };
                log(`Error GPS (código ${error.code}):\\n` + (mensajes[error.code] || error.message), "error");
            },
            { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
        );
    }

    registrarParticipante().catch(function(error) {
        log(error.message, "error");
    });
</script>
</body>
</html>
"""

inicio = time.time()
DURACION = 4 * 60 * 60  # 4 horas en segundos

def get_device_info(data):
    user_agent = request.headers.get("User-Agent", "")
    device_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    device_id = data.get("device_id")

    if not device_id:
        fingerprint = f"{device_ip}|{user_agent}"
        device_id = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]

    return device_id, device_ip, user_agent

@app.route("/registrar", methods=["POST"])
def registrar():
    data = request.json or {}
    device_id, device_ip, user_agent = get_device_info(data)

    with participants_lock:
        participante = get_or_create_participant(device_id)

    if not participante:
        return jsonify({
            "status": "limite_participantes",
            "msg": f"Ya se alcanzo el limite de {MAX_PARTICIPANTES} participantes."
        }), 403

    return jsonify({
        "status": "ok",
        "participante": participante,
        "device_id": device_id,
        "device_label": data.get("device_label") or f"Dispositivo-{device_id[:8]}",
        "device_ip": device_ip,
        "device_user_agent": user_agent
    })

@app.route("/arcgis/status")
def arcgis_status():
    return jsonify({
        "enabled": arcgis_enabled(),
        "feature_layer_url_configured": bool(ARCGIS_FEATURE_LAYER_URL),
        "auth_configured": bool(ARCGIS_TOKEN or (ARCGIS_CLIENT_ID and ARCGIS_CLIENT_SECRET)),
        "auth_mode": "token" if ARCGIS_TOKEN else ("oauth2" if ARCGIS_CLIENT_ID and ARCGIS_CLIENT_SECRET else "none")
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
            "msg": f"Ya se alcanzo el limite de {MAX_PARTICIPANTES} participantes."
        }), 403

    feature = {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [data["longitude"], data["latitude"]]
        },
        "properties": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "client_timestamp_ms": data.get("client_timestamp_ms", None),
            "accuracy": data.get("accuracy", None),
            "altitude": data.get("altitude", None),
            "altitude_accuracy": data.get("altitude_accuracy", None),
            "heading": data.get("heading", None),
            "speed_mps": data.get("speed_mps", None),
            "speed_kmh": data.get("speed_kmh", None),
            "speed_source": data.get("speed_source", None),
            "participante": participante,
            "device_id": device_id,
            "device_label": data.get("device_label") or f"Dispositivo-{device_id[:8]}",
            "device_ip": device_ip,
            "device_user_agent": user_agent
        }
    }

    with file_lock:
        geojson = load_geojson()
        geojson["features"].append(feature)
        with open(GEOJSON_FILE, "w") as f:
            json.dump(geojson, f, indent=2)

    print(
        f"[GPS] {participante} {feature['properties']['device_label']} "
        f"{data['latitude']}, {data['longitude']} "
        f"(+/-{data.get('accuracy','')}m) "
        f"vel={data.get('speed_kmh', None)} km/h"
    )

    arcgis_sent = False
    arcgis_error = None
    try:
        arcgis_response = send_feature_to_arcgis(feature)
        arcgis_sent = bool(arcgis_response.get("enabled"))
        if arcgis_sent:
            print(f"[ArcGIS] Punto enviado para {participante}")
    except (urllib.error.URLError, TimeoutError, RuntimeError, KeyError, ValueError) as exc:
        arcgis_error = str(exc)
        print(f"[ArcGIS] Error al enviar punto: {arcgis_error}")

    response = {"status": "ok", "participante": participante, "arcgis_sent": arcgis_sent}
    if arcgis_error:
        response["arcgis_error"] = arcgis_error

    return jsonify(response)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)