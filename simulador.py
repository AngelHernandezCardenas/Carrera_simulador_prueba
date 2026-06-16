import json
import time
import urllib.request
import urllib.error

def main():
    # URL local de tu servidor Flask
    url = "http://127.0.0.1:5000/gps"
    
    print("Cargando test/gps_data.geojson...")
    try:
        with open("test/gps_data.geojson", "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error al cargar el archivo: {e}")
        return
        
    features = data.get("features", [])
    if not features:
        print("No se encontraron puntos en el GeoJSON.")
        return
        
    print(f"Encontrados {len(features)} puntos. Iniciando simulación a 1 punto por segundo...")
    
    # Enviar cada punto del GeoJSON al servidor simulando un dispositivo
    for i, feature in enumerate(features):
        coords = feature.get("geometry", {}).get("coordinates")
        if not coords or len(coords) < 2:
            continue
            
        lon, lat = coords
        props = feature.get("properties", {})
        
        payload = {
            "latitude": lat,
            "longitude": lon,
            "speed_kmh": props.get("speed_kmh", 5.0),
            "accuracy": props.get("accuracy", 10.0),
            "device_id": "simulador-mono-01",
            "device_label": "Simulador Mono"
        }
        
        data_bytes = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data_bytes, headers={'Content-Type': 'application/json'})
        
        try:
            with urllib.request.urlopen(req, timeout=2) as response:
                status_code = response.getcode()
                print(f"[{i+1}/{len(features)}] Punto enviado: {lat:.6f}, {lon:.6f} - Resp: {status_code}")
        except urllib.error.URLError as e:
            print(f"Error de conexión (Asegúrate de que app.py esté corriendo en otra pestaña): {e.reason}")
            
        # Esperar 0.33 segundos antes de enviar el siguiente (Velocidad x3)
        time.sleep(0.33)

if __name__ == "__main__":
    main()
