import time
import requests
import random
import threading
from datetime import datetime

# URL del servidor puente (Dashboard de Telemetría)
URL = "http://localhost:5001/datos"

# Lista de las 12 Raspberries
dispositivos = [f"Raspberry_Relieve{i}" for i in range(1, 13)]

# Coordenadas base
lat_base = 25.6866
lon_base = -100.3161

def simular_raspberry(dispositivo_id, delay_inicial):
    # Simulamos que cada una se enciende en un momento distinto
    time.sleep(delay_inicial)
    print(f"🔌 [{dispositivo_id}] Encendida y conectándose al servidor...")

    while True:
        # Cada bici avanza un poquito por su cuenta
        lat = lat_base + random.uniform(-0.005, 0.005)
        lon = lon_base + random.uniform(-0.005, 0.005)
        
        payload = {
            "dispositivo_id": dispositivo_id,
            "timestamp": datetime.now().isoformat(),
            "latitud": lat,
            "longitud": lon,
            "voltaje": round(random.uniform(12.0, 13.5), 2),
            "corriente": round(random.uniform(1.0, 5.0), 2),
            "potencia": round(random.uniform(10, 60), 2),
            "soc": round(random.uniform(80, 100), 1),
            "ttg_min": random.randint(120, 300),
            "ah_consumidos": round(random.uniform(0.1, 2.0), 2),
            "motor_voltaje": round(random.uniform(23.0, 25.0), 2),
            "motor_corriente": round(random.uniform(2.0, 10.0), 2),
            "motor_potencia": round(random.uniform(50, 250), 2),
            "motor_rpm": random.randint(150, 400),
            "motor_temp": random.randint(30, 45)
        }
        
        try:
            response = requests.post(URL, json=payload, timeout=5)
            if response.status_code in [200, 201]:
                print(f"✅ [Enviado] {dispositivo_id} | SOC: {payload['soc']}%")
        except Exception:
            pass
            
        time.sleep(5)  # Enviar datos cada 5 segundos

print("🚀 Iniciando prueba masiva: 12 Raspberries Simultáneas")
print("Se encenderán en un orden aleatorio para probar el mapeo de equipos.")
print("Presiona Ctrl+C para detener el simulador.\n")

# Desordenamos la lista para probar que el orden de conexión no importa
random.shuffle(dispositivos)

hilos = []
for i, dispositivo_id in enumerate(dispositivos):
    # Le damos a cada Raspberry un tiempo de encendido (delay) distinto
    delay_inicial = i * 1.5 
    t = threading.Thread(target=simular_raspberry, args=(dispositivo_id, delay_inicial), daemon=True)
    t.start()
    hilos.append(t)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n🛑 Simulador detenido.")
