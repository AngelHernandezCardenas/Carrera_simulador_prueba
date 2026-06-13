import os
import threading
from dotenv import load_dotenv

load_dotenv()

# --- Archivos de datos ---
GEOJSON_FILE = "gps_data.geojson"
PARTICIPANTS_FILE = "participantes.json"
MAX_PARTICIPANTES = 20

# --- Duración de la sesión ---
DURACION = 4 * 60 * 60  # 4 horas en segundos

# --- Locks globales ---
file_lock          = threading.Lock()
participants_lock  = threading.Lock()
