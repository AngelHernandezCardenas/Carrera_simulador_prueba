import json
import os
from config import GEOJSON_FILE, file_lock


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
        init_geojson()
        return {"type": "FeatureCollection", "features": []}


def append_feature(feature):
    """Agrega un feature al GeoJSON local de forma thread-safe."""
    with file_lock:
        geojson = load_geojson()
        geojson["features"].append(feature)
        with open(GEOJSON_FILE, "w") as f:
            json.dump(geojson, f, indent=2)


# Inicializar el archivo si no existe al importar el módulo
if not os.path.exists(GEOJSON_FILE):
    init_geojson()
