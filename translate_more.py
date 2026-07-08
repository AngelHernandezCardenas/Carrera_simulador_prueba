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

jurados_replacements = [
    (r'Registro de Jueces', 'Judges Registry'),
    (r'Juez', 'Judge'),
    (r'Actividad', 'Activity'),
    (r'Puntos', 'Points'),
    (r'Registrar Puntaje', 'Register Score'),
    (r'Últimos Registros', 'Recent Logs'),
    (r'Equipo', 'Team'),
    (r'Selecciona actividad\.\.\.', 'Select activity...'),
    (r'Selecciona juez\.\.\.', 'Select judge...'),
    (r'Selecciona equipo\.\.\.', 'Select team...'),
    (r'Por favor completa todos los campos', 'Please complete all fields'),
]
translate_file('templates/jurados.html', jurados_replacements)

var_replacements = [
    (r'Revisión VAR', 'VAR Review'),
    (r'Participante', 'Participant'),
    (r'Foto', 'Photo'),
    (r'Hora', 'Time'),
    (r'Acción', 'Action'),
    (r'Validar', 'Validate'),
    (r'Invalidar', 'Invalidate'),
    (r'Sin imágenes recientes', 'No recent images'),
]
translate_file('templates/var.html', var_replacements)

fotos_replacements = [
    (r'Fotos Checkpoints', 'Checkpoints Photos'),
    (r'Galería General', 'General Gallery'),
]
translate_file('templates/fotos_checkpoints.html', fotos_replacements)

app_replacements = [
    (r'Contador detenido', 'Timer stopped'),
    (r'Timer detenido localmente', 'Timer stopped locally'),
    (r'El contador global ha sido detenido.', 'Global timer has been stopped.'),
    (r'Timer reiniciado', 'Timer reset'),
]
translate_file('app.py', app_replacements)

checkpoints_replacements = [
    (r'registrado en', 'registered at'),
]
translate_file('checkpoints.py', checkpoints_replacements)

