import json
import time
import threading
import urllib.parse
import urllib.request
import urllib.error

from config import (
    ARCGIS_FEATURE_LAYER_URL,
    ARCGIS_TOKEN,
    ARCGIS_CLIENT_ID,
    ARCGIS_CLIENT_SECRET,
    ARCGIS_TOKEN_URL,
    ARCGIS_TIMEOUT,
    ARCGIS_THROTTLE_SECONDS,
    arcgis_lock,
)

# Token cacheado en memoria para OAuth 2.0
_arcgis_cached_token = {"token": ARCGIS_TOKEN, "expires_at": 0}

# Última vez (timestamp) que se envió un punto a ArcGIS, por participante
_last_arcgis_send: dict[str, float] = {}
_last_arcgis_send_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def arcgis_enabled() -> bool:
    return bool(
        ARCGIS_FEATURE_LAYER_URL
        and (ARCGIS_TOKEN or (ARCGIS_CLIENT_ID and ARCGIS_CLIENT_SECRET))
    )


def _arcgis_endpoint(action: str) -> str:
    url = ARCGIS_FEATURE_LAYER_URL.rstrip("/")
    # Quita la acción anterior si ya viene una en la URL base
    for known_action in ("addFeatures", "updateFeatures", "deleteFeatures", "applyEdits", "query"):
        suffix = f"/{known_action}"
        if url.endswith(suffix):
            url = url[: -len(suffix)]
            break
    return f"{url}/{action}"


def _post_arcgis_form(url: str, params: dict) -> dict:
    encoded = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=ARCGIS_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_arcgis_token() -> str:
    if ARCGIS_TOKEN:
        return ARCGIS_TOKEN

    now_ms = int(time.time() * 1000)
    with arcgis_lock:
        if _arcgis_cached_token["token"] and _arcgis_cached_token["expires_at"] - now_ms > 60_000:
            return _arcgis_cached_token["token"]

        token_data = _post_arcgis_form(ARCGIS_TOKEN_URL, {
            "client_id":     ARCGIS_CLIENT_ID,
            "client_secret": ARCGIS_CLIENT_SECRET,
            "grant_type":    "client_credentials",
        })

        if "error" in token_data:
            raise RuntimeError(token_data["error"].get("message", "No se pudo obtener token OAuth2 de ArcGIS"))

        access_token   = token_data.get("access_token")
        expires_in_sec = token_data.get("expires_in", 7200)

        if not access_token:
            raise RuntimeError("Respuesta de token inesperada desde ArcGIS")

        _arcgis_cached_token["token"]      = access_token
        _arcgis_cached_token["expires_at"] = now_ms + (expires_in_sec * 1000)

    return _arcgis_cached_token["token"]


def _feature_to_arcgis_attrs(feature: dict, object_id=None) -> dict:
    lon, lat = feature["geometry"]["coordinates"]
    attrs = dict(feature["properties"])
    if object_id is not None:
        attrs["OBJECTID"] = object_id
    return {
        "geometry": {"x": lon, "y": lat, "spatialReference": {"wkid": 4326}},
        "attributes": attrs,
    }


# ---------------------------------------------------------------------------
# Operaciones ArcGIS
# ---------------------------------------------------------------------------

def arcgis_add_feature(feature: dict) -> int:
    """Crea el feature por primera vez y devuelve el OBJECTID asignado por ArcGIS."""
    token = _get_arcgis_token()
    params = {"f": "json", "features": json.dumps([_feature_to_arcgis_attrs(feature)])}
    if token:
        params["token"] = token

    result = _post_arcgis_form(_arcgis_endpoint("addFeatures"), params)

    if "error" in result:
        raise RuntimeError(result["error"].get("message", "Error de ArcGIS (addFeatures)"))

    add_results = result.get("addResults", [])
    if not add_results or not add_results[0].get("success"):
        error = add_results[0].get("error", {}) if add_results else {}
        raise RuntimeError(error.get("description") or error.get("message") or "ArcGIS rechazó el punto (addFeatures)")

    return add_results[0]["objectId"]


def arcgis_update_feature(feature: dict, object_id: int) -> dict:
    """Actualiza el feature existente (mismo OBJECTID) con la nueva posición/atributos."""
    token = _get_arcgis_token()
    params = {"f": "json", "features": json.dumps([_feature_to_arcgis_attrs(feature, object_id=object_id)])}
    if token:
        params["token"] = token

    result = _post_arcgis_form(_arcgis_endpoint("updateFeatures"), params)

    if "error" in result:
        raise RuntimeError(result["error"].get("message", "Error de ArcGIS (updateFeatures)"))

    update_results = result.get("updateResults", [])
    if not update_results or not update_results[0].get("success"):
        error = update_results[0].get("error", {}) if update_results else {}
        raise RuntimeError(error.get("description") or error.get("message") or "ArcGIS rechazó la actualización (updateFeatures)")

    return result


def send_feature_to_arcgis(feature: dict, participante: str, participants_cache: dict, save_fn) -> dict:
    """
    Mantiene UN solo punto por participante en ArcGIS.
    - Primer envío  → addFeatures,  guarda OBJECTID en participantes.json
    - Envíos siguientes → updateFeatures usando ese OBJECTID
    """
    if not arcgis_enabled():
        return {"enabled": False}

    from config import participants_lock  # importación local para evitar circular
    with participants_lock:
        object_id = participants_cache.get(participante, {}).get("arcgis_object_id")

    if object_id is None:
        new_object_id = arcgis_add_feature(feature)
        with participants_lock:
            entry = participants_cache.get(participante, {})
            entry["arcgis_object_id"] = new_object_id
            participants_cache[participante] = entry
            save_fn(participants_cache)
        return {"enabled": True, "action": "add", "object_id": new_object_id}

    result = arcgis_update_feature(feature, object_id)
    return {"enabled": True, "action": "update", "object_id": object_id, "result": result}


def should_send_to_arcgis(participante: str) -> bool:
    """Throttling: solo permite enviar a ArcGIS cada ARCGIS_THROTTLE_SECONDS por participante."""
    now = time.time()
    with _last_arcgis_send_lock:
        last = _last_arcgis_send.get(participante, 0)
        if now - last >= ARCGIS_THROTTLE_SECONDS:
            _last_arcgis_send[participante] = now
            return True
    return False