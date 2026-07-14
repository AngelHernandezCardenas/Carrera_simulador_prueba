import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime

from checkpoints import CHECKPOINTS, haversine_distance_m


DEFAULT_URL = "http://127.0.0.1:5000/gps"
DEFAULT_INTERVAL = 1.65  # app.py ignora lecturas del mismo dispositivo antes de 1.5 s
TEAM_NAME = "participante_13"
TEAM_LABEL = "Team 13"
TARGET_LOAD = 10
HOME_UNLOAD_RADIUS_M = 15.0


# Rutas peatonales obtenidas con Valhalla/OpenStreetMap. Se conservaron los
# giros importantes de los andadores y se eliminaron puntos rectos redundantes.
# El primer/último punto de cada tramo se reemplaza abajo con las coordenadas
# exactas configuradas para que la detección de checkpoints sea determinista.
HOME_TO_CP1 = [
    (25.651464, -100.291149),
    (25.651551, -100.291126),
    (25.651620, -100.291045),
    (25.651773, -100.291051),
    (25.651776, -100.290850),
    (25.651806, -100.290851),
    (25.651799, -100.290228),
    (25.651790, -100.289630),
    (25.651617, -100.289631),
    (25.651438, -100.289597),
    (25.651445, -100.289150),
    (25.651115, -100.289151),
    (25.651119, -100.288352),
    (25.651133, -100.288352),
]

CP1_TO_HOME = [
    (25.651133, -100.288352),
    (25.651115, -100.289151),
    (25.651445, -100.289150),
    (25.651438, -100.289597),
    (25.651356, -100.289795),
    (25.651360, -100.290598),
    (25.651281, -100.290619),
    (25.651103, -100.290693),
    (25.651101, -100.291046),
    (25.651277, -100.291045),
    (25.651276, -100.291102),
    (25.651377, -100.291123),
    (25.651464, -100.291149),
]

HOME_TO_CP2 = [
    (25.651464, -100.291149),
    (25.651277, -100.291045),
    (25.651101, -100.291046),
    (25.651103, -100.290693),
    (25.651105, -100.290235),
    (25.650575, -100.290230),
    (25.6505742, -100.2903096),
]

CP2_TO_HOME = [
    (25.6505742, -100.2903096),
    (25.650575, -100.290230),
    (25.651105, -100.290235),
    (25.651103, -100.290693),
    (25.651101, -100.291046),
    (25.651277, -100.291045),
    (25.651464, -100.291149),
]


def checkpoint_id(checkpoint):
    value = checkpoint["id"]
    if str(value).lower() == "home-base":
        return 99
    return int(value)


def get_checkpoint(target_id):
    return next(cp for cp in CHECKPOINTS if checkpoint_id(cp) == target_id)


def exact_route_endpoints():
    home = get_checkpoint(99)
    cp1 = get_checkpoint(1)
    cp2 = get_checkpoint(2)
    home_coord = (float(home["lat"]), float(home["lon"]))
    cp1_coord = (float(cp1["lat"]), float(cp1["lon"]))
    cp2_coord = (float(cp2["lat"]), float(cp2["lon"]))

    routes = [list(route) for route in (HOME_TO_CP1, CP1_TO_HOME, HOME_TO_CP2, CP2_TO_HOME)]
    routes[0][0], routes[0][-1] = home_coord, cp1_coord
    routes[1][0], routes[1][-1] = cp1_coord, home_coord
    routes[2][0], routes[2][-1] = home_coord, cp2_coord
    routes[3][0], routes[3][-1] = cp2_coord, home_coord
    return routes


def route_step(coord, label, white_balls, action=None):
    return {
        "lat": coord[0],
        "lon": coord[1],
        "label": label,
        "white_balls": white_balls,
        "action": action,
    }


def build_route():
    home_to_cp1, cp1_to_home, home_to_cp2, cp2_to_home = exact_route_endpoints()
    steps = []
    home_coord = home_to_cp1[0]
    white_balls = 0

    # Se agregan diez pelotas blancas de forma progresiva durante el primer
    # trayecto. Cada una vale 1, por lo que la carga llega exactamente a 10.
    for index, coord in enumerate(home_to_cp1):
        distance_from_home = haversine_distance_m(
            coord[0], coord[1], home_coord[0], home_coord[1]
        )
        if distance_from_home > HOME_UNLOAD_RADIUS_M:
            white_balls = min(TARGET_LOAD, white_balls + 1)
        label = "salida de Home Base" if index == 0 else f"andador a CP 1 (+{white_balls})"
        action = None
        if index == len(home_to_cp1) - 1:
            label = "llegada a CP 1 con carga 10"
            action = "complete_cp1"
        steps.append(route_step(coord, label, white_balls, action))

    unload_marked = False
    for index, coord in enumerate(cp1_to_home[1:], start=1):
        label = "regreso cargado a Home Base"
        action = None
        distance_from_home = haversine_distance_m(
            coord[0], coord[1], home_coord[0], home_coord[1]
        )
        if distance_from_home <= HOME_UNLOAD_RADIUS_M and not unload_marked:
            label = "entrada y descarga en Home Base"
            action = "unload"
            unload_marked = True
        elif index == len(cp1_to_home) - 1:
            label = "Home Base después de descarga"
        steps.append(route_step(coord, label, TARGET_LOAD, action))

    for index, coord in enumerate(home_to_cp2[1:], start=1):
        label = "andador de Home Base a CP 2"
        action = None
        if index == len(home_to_cp2) - 1:
            label = "llegada única a CP 2"
            action = "visit_cp2"
        steps.append(route_step(coord, label, 0, action))

    for index, coord in enumerate(cp2_to_home[1:], start=1):
        label = "regreso de CP 2 a Home Base"
        action = "finish_home" if index == len(cp2_to_home) - 1 else None
        steps.append(route_step(coord, label, 0, action))

    return steps


def endpoint_url(gps_url, endpoint):
    return f"{gps_url.rsplit('/', 1)[0]}/{endpoint.lstrip('/')}"


def post_json(url, payload):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        response_body = response.read().decode("utf-8", errors="replace")
        return response.getcode(), json.loads(response_body)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Simula al Team 13 por andadores: Home Base → CP 1 con carga 10 → "
            "Home Base (descarga) → CP 2 → Home Base."
        )
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="URL del endpoint /gps")
    parser.add_argument("--intervalo", type=float, default=DEFAULT_INTERVAL)
    parser.add_argument(
        "--run-id",
        default=datetime.now().strftime("%Y%m%d-%H%M%S"),
        help="Identificador para crear una prueba sin estado anterior",
    )
    args = parser.parse_args()
    if args.intervalo < DEFAULT_INTERVAL:
        parser.error(f"--intervalo debe ser al menos {DEFAULT_INTERVAL} segundos")
    return args


def register_team(gps_url, device_id):
    return post_json(
        endpoint_url(gps_url, "registrar"),
        {
            "device_id": device_id,
            "device_label": TEAM_LABEL,
            "custom_name": TEAM_NAME,
        },
    )


def complete_checkpoint_1_challenge(gps_url, device_id):
    return post_json(
        endpoint_url(gps_url, "api/score"),
        {
            "device_id": device_id,
            "equipo": TEAM_NAME,
            "checkpoint_id": 1,
            "puntaje": 0,
        },
    )


def make_payload(device_id, step, sequence):
    return {
        "device_id": device_id,
        "device_label": TEAM_LABEL,
        "participante": TEAM_NAME,
        "latitude": step["lat"],
        "longitude": step["lon"],
        "speed_kmh": 6.0,
        "accuracy": 3.0,
        "soc": max(20.0, 98.0 - sequence * 0.2),
        "conteo_colores": {
            "Rojo": 0,
            "Blanco": step["white_balls"],
            "Negro": 0,
        },
    }


def main():
    args = parse_args()
    route = build_route()
    device_id = f"sim-route-team-13-{args.run_id}"
    latest_state = {}
    unload_state = None
    cp2_state = None

    try:
        status, registration = register_team(args.url, device_id)
        if status != 200 or registration.get("participante") != TEAM_NAME:
            print(f"No se pudo registrar Team 13: {registration}")
            return 1
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f"No se pudo registrar Team 13: {exc}")
        return 1

    print(
        f"Simulación por andadores: {len(route)} posiciones, carga máxima 10. "
        "Ctrl+C para detener."
    )

    try:
        for sequence, step in enumerate(route):
            cycle_started = time.monotonic()
            try:
                status, response = post_json(args.url, make_payload(device_id, step, sequence))
                if response.get("skipped"):
                    print(f"{TEAM_LABEL}: lectura omitida por el servidor")
                    continue

                latest_state = response
                load = response.get("peso_kg", 0)
                delivered = response.get("peso_entregado_kg", 0)
                visits = response.get("checkpoints_visitados", [])
                print(
                    f"[{sequence + 1:02d}/{len(route)}] {step['label']:<34} | "
                    f"carga={load:g} | entregado={delivered:g} | CP={visits}"
                )

                if step["action"] == "complete_cp1":
                    score_status, score_response = complete_checkpoint_1_challenge(
                        args.url,
                        device_id,
                    )
                    if score_status != 200 or score_response.get("status") != "ok":
                        print(f"No se pudo habilitar el regreso a Home Base: {score_response}")
                        return 1
                    print("Team 13 -> reto de CP 1 calificado; regreso habilitado")
                elif step["action"] == "unload":
                    unload_state = response
                elif step["action"] == "visit_cp2":
                    cp2_state = response

                # Respaldo ante ajustes futuros en el radio de descarga: se
                # conserva la lectura exacta en la que el servidor descargó.
                if response.get("peso_descargado_kg") == TARGET_LOAD:
                    unload_state = response
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                print(f"{TEAM_LABEL}: HTTP {exc.code}: {detail}")
                return 1
            except urllib.error.URLError as exc:
                print(f"No se pudo conectar a {args.url}: {exc.reason}")
                return 1
            except (TimeoutError, json.JSONDecodeError) as exc:
                print(f"{TEAM_LABEL}: respuesta inválida: {exc}")
                return 1

            remaining = args.intervalo - (time.monotonic() - cycle_started)
            if sequence < len(route) - 1 and remaining > 0:
                time.sleep(remaining)
    except KeyboardInterrupt:
        print("\nSimulación detenida.")
        return 130

    final_visits = latest_state.get("checkpoints_visitados", [])
    unloaded = bool(
        unload_state
        and float(unload_state.get("peso_kg", -1)) == 0
        and float(unload_state.get("peso_descargado_kg", -1)) == TARGET_LOAD
        and float(unload_state.get("peso_entregado_kg", -1)) == TARGET_LOAD
    )
    cp2_visited = bool(cp2_state and cp2_state.get("checkpoints_visitados") == [1, 2, 99])
    passed = unloaded and cp2_visited and final_visits == [1, 2, 99]

    print("\nResultado de la prueba")
    print(f"Descarga de 10 en Home Base: {'OK' if unloaded else 'FALLÓ'}")
    print(f"Visita posterior a CP 2: {'OK' if cp2_visited else 'FALLÓ'}")
    print(f"Estado final al regresar a Home Base: {final_visits}")
    print("PRUEBA CORRECTA" if passed else "PRUEBA FALLIDA")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
