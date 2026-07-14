import requests
import time
import random

SERVER_URL = "http://localhost:5000/gps"

def simular_raspberry():
    print("Iniciando simulación de Raspberry Pi (Enviando Telemetría)...")
    
    # Valores base
    soc = 98.0
    ah_consumidos = 0.0
    lat = 20.676667
    lon = -103.3475
    
    for i in range(5):
        # Disminuir batería y aumentar Ah consumidos poco a poco
        soc -= random.uniform(0.1, 0.5)
        ah_consumidos += random.uniform(0.1, 0.3)
        
        # Mover un poquito el GPS
        lat += 0.0001
        lon += 0.0001
        
        payload = {
            "participante": "Participante_2", # Simulamos ser el equipo 2
            "latitude": lat,
            "longitude": lon,
            "soc": round(soc, 2),
            "ah_consumidos": round(ah_consumidos, 2),
            "voltaje": 12.4,
            "corriente": 2.5
        }
        
        print(f"[{i+1}/5] Enviando ping de Team 2... SOC: {payload['soc']}% | Energía: {payload['ah_consumidos']} Ah")
        
        try:
            res = requests.post(SERVER_URL, json=payload, timeout=5)
            if res.status_code == 200:
                print(" -> ¡Éxito! (Checa tu pestaña 'Energy' del Excel para ver cómo se sobrescribe)")
            else:
                print(f" -> Error HTTP {res.status_code}")
        except Exception as e:
            print(f" -> Error de conexión: {e} (¿Asegúrate de que app.py esté corriendo en otra terminal?)")
        
        # Esperamos 16 segundos para asegurar pasar el Throttle de 15 segundos
        if i < 4:
            print("Esperando 16 segundos para el siguiente envío (Throttle)...")
            time.sleep(16)

if __name__ == "__main__":
    simular_raspberry()
