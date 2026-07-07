import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# --- Archivos de datos ---
GEOJSON_FILE = BASE_DIR / "gps_data.geojson"
PARTICIPANTS_FILE = BASE_DIR / "participantes.json"
JUDGES_FILE = BASE_DIR / "judges.json"
MAX_PARTICIPANTES = 50

# --- DuraciÃ³n de la sesiÃ³n ---
DURACION = 4 * 60 * 60  # 4 horas en segundos

# --- Locks globales ---
file_lock = threading.Lock()
participants_lock = threading.Lock()
judges_lock = threading.Lock()


