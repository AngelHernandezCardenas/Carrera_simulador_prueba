import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# --- Archivos de datos ---
GEOJSON_FILE = BASE_DIR / "gps_data.geojson"
PARTICIPANTS_FILE = BASE_DIR / "participantes.json"
MAX_PARTICIPANTES = 50

# --- Duración de la sesión ---
DURACION = 24 * 60 * 60  # 24 horas en segundos

# --- Locks globales ---
file_lock = threading.Lock()
participants_lock = threading.Lock()
