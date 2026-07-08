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

puntaje_replacements = [
    (r'SCOREBOARD / TABLA DE POSICIONES actualizados en memoria:', 'SCOREBOARD updated in memory:'),
    (r'Error leyendo la hoja de puntajes:', 'Error reading scores sheet:'),
    (r'Desconocido', 'Unknown'),
]

translate_file('Puntaje.py', puntaje_replacements)

app_replacements = [
    (r'ha recibido un nuevo puntaje!', 'has received a new score!'),
    (r'Error de red', 'Network error'),
    (r'Cargando\.\.\.', 'Loading...'),
    (r'Estatus', 'Status'),
]

translate_file('app.py', app_replacements)

