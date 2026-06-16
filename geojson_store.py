import json
import os

from config import GEOJSON_FILE, file_lock


def dump_geojson(geojson, file_obj):
    features = geojson.get("features", [])

    file_obj.write('{"type":"FeatureCollection","features":[')
    if features:
        file_obj.write("\n")
        for index, feature in enumerate(features):
            if index > 0:
                file_obj.write(",\n")
            json.dump(feature, file_obj, separators=(",", ":"))
        file_obj.write("\n")
    file_obj.write("]}")


def init_geojson():
    with open(GEOJSON_FILE, "w", encoding="utf-8") as f:
        dump_geojson({"type": "FeatureCollection", "features": []}, f)


def load_geojson():
    try:
        with open(GEOJSON_FILE, "r", encoding="utf-8") as f:
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
        with open(GEOJSON_FILE, "w", encoding="utf-8") as f:
            dump_geojson(geojson, f)


if not os.path.exists(GEOJSON_FILE):
    init_geojson()
