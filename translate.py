import os
import re

def translate_file(path, replacements):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = content
    for old, new in replacements:
        new_content = re.sub(old, new, new_content)
        
    if new_content != content:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Translated {path}")
    else:
        print(f"No changes in {path}")

# Replacements for templates/mapa.html
mapa_replacements = [
    (r'>TELEMETRIA<', '>TELEMETRY<'),
    (r'>Iniciar<', '>Start<'),
    (r'>Detener<', '>Stop<'),
    (r'>Día<', '>Day<'),
    (r'CORREDORES<', 'RUNNERS<'),
    (r'LÍDER \(KM\)', 'LEADER (KM)'),
    (r'>POS<', '>POS<'),
    (r'>CORREDOR<', '>RUNNER<'),
    (r'>TIEMPO<', '>TIME<'),
    (r'>VISITADOS<', '>VISITED<'),
    (r'>CHECKPOINT<', '>CHECKPOINT<'),
    (r'>Telemetria<', '>Telemetry<'),
    (r'id="timer-status-\$\{id\}">corriendo<', 'id="timer-status-${id}">running<'),
    (r'id="timer-status-\$\{id\}">terminado<', 'id="timer-status-${id}">finished<'),
]

translate_file('templates/mapa.html', mapa_replacements)

# Replacements for templates/index.html
index_replacements = [
    (r'Activar acelerómetro manual', 'Activate manual accelerometer'),
    (r'Encender cámara', 'Turn on camera'),
    (r'Iniciar captura', 'Start capture'),
    (r'Escanear', 'Scan'),
    (r'Reiniciar', 'Reset'),
    (r'Galería', 'Gallery'),
    (r'Escáner visual de carga', 'Visual load scanner'),
    (r'Velocidad', 'Speed'),
    (r'Precisión GPS', 'GPS Accuracy'),
    (r'Checkpoint ponderado más cercano', 'Nearest weighted checkpoint'),
    (r'Acelerómetro con gravedad', 'Accelerometer with gravity'),
    (r'Aceleración', 'Acceleration'),
    (r'Magnitud:', 'Magnitude:'),
    (r'Distancia:', 'Distance:'),
    (r'Fuente:', 'Source:'),
    (r'Hora:', 'Time:'),
    (r'Esperando\.\.\.', 'Waiting...'),
    (r'Galería de Capturas', 'Capture Gallery'),
    (r'Limpiar', 'Clear'),
    (r'Cerrar', 'Close'),
    (r'Cargando\.\.\.', 'Loading...'),
    (r'Alternar Contorno', 'Toggle Contour'),
    (r'Color:', 'Color:'),
]

translate_file('templates/index.html', index_replacements)

# Replacements for templates/scoreboard.html
scoreboard_replacements = [
    (r'Scoreboard en Vivo', 'Live Scoreboard'),
    (r'Total de participantes:', 'Total participants:'),
    (r'Cargando datos\.\.\.', 'Loading data...'),
]

translate_file('templates/scoreboard.html', scoreboard_replacements)

# App.py translations
app_replacements = [
    (r'Equipo no encontrado', 'Team not found'),
    (r'Contador iniciado para todos los participantes', 'Timer started for all participants'),
    (r'El peso de la pelota se actualizó', 'Ball weight updated'),
    (r'Faltan datos de la pelota', 'Missing ball data'),
    (r'Error al actualizar pelota', 'Error updating ball'),
    (r'Registrado', 'Registered'),
]

translate_file('app.py', app_replacements)
