import time
import requests
import os
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("ARCGIS_CLIENT_ID")
CLIENT_SECRET = os.getenv("ARCGIS_CLIENT_SECRET")

token_actual = None 
token_expira_en = 0

def obtener_token_arcgis():
    url = "https://www.arcgis.com/sharing/rest/oauth2/token"

    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials",
        "expiration": 20160,
        "f": "json"
    }

    r = requests.post(url, data=data)
    respuesta = r.json()

    if "access_token" not in respuesta:
        raise Exception(f"Error al obtener token: {respuesta}")

    token = respuesta["access_token"]
    expires_in = respuesta.get("expires_in", 3600)

    return token, time.time() + expires_in


def get_token_valido():
    global token_actual, token_expira_en

    # Renueva 5 minutos antes de que expire
    if token_actual is None or time.time() > token_expira_en - 300:
        token_actual, token_expira_en = obtener_token_arcgis()
        print("Token renovado correctamente")

    return token_actual