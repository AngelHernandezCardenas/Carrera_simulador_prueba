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

mapa_replacements = [
    (r'corriendo', 'running'),
    (r'terminado', 'finished'),
    (r'Contador iniciado para todos los participantes\.', 'Timer started for all participants.'),
    (r'Estatus terminado para todos', 'Status finished for all'),
    (r'Tiempo final', 'Final time'),
    (r'Completado', 'Completed'),
    (r'En evaluación', 'In evaluation'),
    (r'Velocidad', 'Speed'),
    (r'Posición', 'Position'),
    (r'Posici\\ufffdn', 'Position'),
    (r'Posici\\xf3n', 'Position'),
    (r'Posicin', 'Position'),
    (r'Checkpoints visitados', 'Visited checkpoints'),
    (r'Puntaje', 'Score'),
    (r'Peso', 'Weight'),
    (r'Checkpoint ponderado mas cercano', 'Nearest weighted checkpoint'),
    (r'Dist\. al ponderado', 'Dist. to weighted'),
    (r'Estado Checkpoint Actual', 'Current Checkpoint Status'),
    (r'Checkpoint pendiente', 'Pending checkpoint'),
    (r'Dist\. pendiente', 'Pending dist.'),
    (r'Estado general', 'Overall status'),
    (r'Nivel bateria', 'Battery level'),
    (r'Telemetría Hardware', 'Hardware Telemetry'),
    (r'Telemetr\\ufffdia Hardware', 'Hardware Telemetry'),
    (r'Telemetra Hardware', 'Hardware Telemetry'),
    (r'Voltaje/Corr', 'Voltage/Curr'),
    (r'Potencia/Ah', 'Power/Ah'),
    (r'RPM/Temp', 'RPM/Temp'),
    (r'ha recibido un nuevo puntaje', 'has received a new score'),
    (r'llegó a un nuevo Checkpoint', 'reached a new Checkpoint'),
    (r'lleg\\ufffdo a un nuevo Checkpoint', 'reached a new Checkpoint'),
    (r'lleg a un nuevo Checkpoint', 'reached a new Checkpoint'),
    (r'Líder Actualizado', 'Leader Updated'),
    (r'L\\ufffdder Actualizado', 'Leader Updated'),
    (r'Lder Actualizado', 'Leader Updated'),
]
translate_file('templates/mapa.html', mapa_replacements)
