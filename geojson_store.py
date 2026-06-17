import json
import os
from config import GEOJSON_FILE, file_lock


def init_geojson():
    with open(GEOJSON_FILE, "w", encoding="utf-8") as f:
        f.write("")


def load_geojson():
    """Carga features desde GeoJSON normal o desde GeoJSON por lineas."""
    try:
        with open(GEOJSON_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                raise ValueError("Archivo vacio")

            if content.startswith("{"):
                try:
                    data = json.loads(content)
                except json.JSONDecodeError:
                    data = None

                if data is None:
                    pass
                elif data.get("type") == "FeatureCollection":
                    return data
                elif data.get("type") == "Feature":
                    return {"type": "FeatureCollection", "features": [data]}

            features = [
                json.loads(line)
                for line in content.splitlines()
                if line.strip()
            ]
            return {"type": "FeatureCollection", "features": features}
    except (ValueError, FileNotFoundError):
        init_geojson()
        return {"type": "FeatureCollection", "features": []}

def append_feature(feature):
    """Agrega un feature al GeoJSON local como un registro JSON por linea."""
    with file_lock:
        with open(GEOJSON_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(feature, ensure_ascii=False, separators=(",", ":")))
            f.write("\n")


# Inicializar el archivo si no existe al importar el modulo.
if not os.path.exists(GEOJSON_FILE):
    init_geojson()
