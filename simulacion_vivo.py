import json
import math
import random
import time
import urllib.error
import urllib.request

URL = "http://127.0.0.1:5000/gps"
CHECKPOINTS = [
    {"id": 1, "lat": 25.651796, "lon": -100.288868},
    {"id": 2, "lat": 25.650111, "lon": -100.289386},
    {"id": 5, "lat": 25.649140, "lon": -100.290238},
    {"id": 3, "lat": 25.651442, "lon": -100.290235},
    {"id": 4, "lat": 25.651464, "lon": -100.291149},
]
PARTICIPANTS = 6
STEPS_BETWEEN = 10
HOLD_STEPS = 3
SEND_INTERVAL = 0.30
LOOPS = 8

def interpolate(a, b, steps):
    for i in range(steps):
        t = i / float(steps)
        yield {
            "lat": a["lat"] + (b["lat"] - a["lat"]) * t,
            "lon": a["lon"] + (b["lon"] - a["lon"]) * t,
        }

def build_route(offset_index):
    ordered = CHECKPOINTS[offset_index:] + CHECKPOINTS[:offset_index]
    points = []
    for idx, cp in enumerate(ordered):
        for _ in range(HOLD_STEPS):
            points.append({"lat": cp["lat"], "lon": cp["lon"], "checkpoint": cp["id"], "hold": True})
        nxt = ordered[(idx + 1) % len(ordered)]
        for point in interpolate(cp, nxt, STEPS_BETWEEN):
            points.append({"lat": point["lat"], "lon": point["lon"], "checkpoint": None, "hold": False})
    return points

routes = [build_route(i % len(CHECKPOINTS)) for i in range(PARTICIPANTS)]
indexes = [(i * 7) % len(routes[i]) for i in range(PARTICIPANTS)]
last_sent = [0.0 for _ in range(PARTICIPANTS)]
sent_counts = [0 for _ in range(PARTICIPANTS)]
max_points = len(routes[0]) * LOOPS

print(f"Simulacion en vivo: {PARTICIPANTS} participantes, {LOOPS} vueltas. Ctrl+C para detener.", flush=True)

def post_payload(payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(URL, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3) as response:
        return response.getcode(), response.read().decode("utf-8", errors="replace")

try:
    while min(sent_counts) < max_points:
        now = time.time()
        for participant_index in range(PARTICIPANTS):
            if sent_counts[participant_index] >= max_points:
                continue
            if now - last_sent[participant_index] < 1.8:
                continue

            route = routes[participant_index]
            point = route[indexes[participant_index] % len(route)]
            jitter = 0 if point.get("hold") else random.uniform(-0.000015, 0.000015)
            payload = {
                "device_id": f"sim-live-{participant_index + 1:02d}",
                "device_label": f"Sim Vivo {participant_index + 1:02d}",
                "latitude": point["lat"] + jitter,
                "longitude": point["lon"] - jitter,
                "speed_kmh": 0.8 if point.get("hold") else random.uniform(4.5, 9.5),
                "accuracy": 3.0,
                "soc": max(15.0, 98.0 - sent_counts[participant_index] * 0.05),
                "conteo_colores": {"rojo": participant_index % 3, "azul": (participant_index + 1) % 2, "verde": participant_index % 2},
            }
            try:
                status, body = post_payload(payload)
                print(f"P{participant_index + 1:02d} -> {status} lat={payload['latitude']:.6f} lon={payload['longitude']:.6f}", flush=True)
            except urllib.error.HTTPError as exc:
                print(f"P{participant_index + 1:02d} HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')}", flush=True)
            except Exception as exc:
                print(f"P{participant_index + 1:02d} error: {exc}", flush=True)

            last_sent[participant_index] = now
            indexes[participant_index] += 1
            sent_counts[participant_index] += 1
            time.sleep(SEND_INTERVAL)
        time.sleep(0.1)
finally:
    print("Simulacion finalizada.", flush=True)
