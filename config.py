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

# --- Variables de entorno para ArcGIS / OAuth 2.0 ---
ARCGIS_FEATURE_LAYER_URL = (os.getenv("ARCGIS_FEATURE_LAYER_URL") or "").strip()
ARCGIS_TOKEN             = (os.getenv("ARCGIS_TOKEN") or "").strip()
ARCGIS_CLIENT_ID         = (os.getenv("ARCGIS_CLIENT_ID") or "").strip()
ARCGIS_CLIENT_SECRET     = (os.getenv("ARCGIS_CLIENT_SECRET") or "").strip()
ARCGIS_TOKEN_URL         = (os.getenv("ARCGIS_TOKEN_URL") or "").strip()
ARCGIS_TIMEOUT           = int(os.getenv("ARCGIS_TIMEOUT") or "10")

# Cada cuántos segundos (mínimo) se envía un punto a ArcGIS por participante
ARCGIS_THROTTLE_SECONDS = float(os.getenv("ARCGIS_THROTTLE_SECONDS") or "5")

# --- Locks globales ---
file_lock          = threading.Lock()
participants_lock  = threading.Lock()
arcgis_lock        = threading.Lock()