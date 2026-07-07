import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# --- Archivos de datos ---
GEOJSON_FILE = BASE_DIR / "gps_data.geojson"
PARTICIPANTS_FILE = BASE_DIR / "participantes.json"
JUDGES_FILE = BASE_DIR / "judges.json"
MAX_PARTICIPANTES = 50
MAX_JUECES_POR_CHECKPOINT = 2

# Google Apps Script Webhook URL para enviar los pesos al Excel
# Debes llenar esta variable con la URL que obtengas al implementar tu script
GOOGLE_APPS_SCRIPT_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbx6_D83m0wFavWQFGHRwC8q2E13fzkl2qa8Db-m77dL9Mgi9HZ-XtuRE3JuoZ8ORYBQIw/exec"

# --- DuraciÃ³n de la sesiÃ³n ---
DURACION = 4 * 60 * 60  # 4 horas en segundos

# --- Locks globales ---
file_lock = threading.Lock()
participants_lock = threading.Lock()
judges_lock = threading.Lock()


