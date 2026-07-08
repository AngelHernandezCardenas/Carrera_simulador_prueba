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

tracker_replacements = [
    (r'Dispositivo', 'Device'),
    (r'Participante', 'Participant'),
    (r'Desconocido', 'Unknown'),
    (r'Registrar', 'Register'),
    (r'Acciones GPS', 'GPS Actions'),
    (r'Iniciar Captura', 'Start Capture'),
    (r'Estado', 'Status'),
    (r'Puntos Checkpoint', 'Checkpoint Points'),
    (r'Subir Checkpoint', 'Submit Score'),
    (r'Cámara y Escaneo', 'Camera and Scan'),
    (r'Encender Cámara', 'Turn on Camera'),
    (r'Escanear', 'Scan'),
    (r'Limpiar Escaneo', 'Clear Scan'),
    (r'Galería', 'Gallery'),
    (r'Acelerómetro Manual', 'Manual Accelerometer'),
    (r'Activar Acelerómetro', 'Activate Accelerometer'),
    (r'Controles Visor', 'Viewer Controls'),
    (r'Cerrar Visor', 'Close Viewer'),
    (r'Alternar Contorno', 'Toggle Contour'),
    (r'Cargando\.\.\.', 'Loading...'),
    (r'Selecciona un Checkpoint primero', 'Select a Checkpoint first'),
    (r'Selecciona un competidor', 'Select a competitor'),
    (r'No hay puntos para enviar', 'No points to submit'),
    (r'Enviando', 'Sending'),
    (r'puntos a', 'points to'),
    (r'Puntaje guardado con', 'Score successfully saved'),
    (r'Error de red', 'Network error'),
    (r'Permiso de acelerómetro denegado', 'Accelerometer permission denied'),
    (r'Permiso de aceler\\ufff0metro denegado', 'Accelerometer permission denied'),
    (r'Acelerómetro activado', 'Accelerometer activated'),
    (r'Aceler\\ufff0metro activado', 'Accelerometer activated'),
    (r'Registro exitoso', 'Registration successful'),
    (r'Error al registrar', 'Error registering'),
    (r'Captura detenida', 'Capture stopped'),
    (r'Captura iniciada', 'Capture started'),
    (r'Error cargando galería', 'Error loading gallery'),
    (r'Error cargando galer\\ufffda', 'Error loading gallery'),
    (r'Galería vacía', 'Empty gallery'),
    (r'Galer\\ufffda vac\\ufffda', 'Empty gallery'),
    (r'Sin CP', 'No CP'),
    (r'Vaciar galería completamente', 'Empty gallery completely'),
    (r'Vaciar galer\\ufffda completamente', 'Empty gallery completely'),
    (r'Galería limpiada', 'Gallery cleared'),
    (r'Galer\\ufffda limpiada', 'Gallery cleared'),
    (r'Error al limpiar', 'Error clearing'),
]

translate_file('templates/tracker.html', tracker_replacements)

