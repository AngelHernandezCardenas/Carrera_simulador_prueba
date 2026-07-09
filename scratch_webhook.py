import urllib.request
import json
import requests

url = "https://script.google.com/macros/s/AKfycbz9syGZK33V3QHTBfnCquv7faJSdutlaI6xNZTlX66LetBNsjasgEwOIHhNr8hx4j-9/exec"
payload = {
    "hora": "12:00:00",
    "juez": "Test",
    "checkpoint": "Test",
    "equipo": "Test",
    "blanca": 1,
    "roja": 2,
    "negra": 3
}

try:
    print("Testing with requests...")
    r = requests.post(url, json=payload, allow_redirects=True)
    print("Status Code:", r.status_code)
    print("Response:", r.text)
except Exception as e:
    print(f"Error enviando webhook: {e}")
