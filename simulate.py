import urllib.request
import json
import random
from datetime import datetime, timedelta

WEBHOOK_URL = 'https://script.google.com/macros/s/AKfycbx6_D83m0wFavWQFGHRwC8q2E13fzkl2qa8Db-m77dL9Mgi9HZ-XtuRE3JuoZ8ORYBQIw/exec'

judges = [f'Judge_{i}' for i in range(1, 16)]
participants = [f'Participante_{random.randint(1, 30)}' for _ in range(15)]
checkpoints = [f'Checkpoint {random.randint(1, 5)}' for _ in range(15)]

print('Iniciando simulacion de 15 registros...')

for i in range(15):
    payload = {
        'hora': (datetime.now() + timedelta(minutes=i*2)).strftime('%H:%M:%S'),
        'juez': judges[i],
        'checkpoint': checkpoints[i],
        'equipo': participants[i].split('_')[1],
        'blanca': random.randint(0, 5),
        'roja': random.randint(0, 3),
        'negra': random.randint(0, 2)
    }
    
    try:
        req = urllib.request.Request(WEBHOOK_URL, method='POST')
        req.add_header('Content-Type', 'application/json')
        response = urllib.request.urlopen(req, data=json.dumps(payload).encode('utf-8'), timeout=10)
        print(f'Registro {i+1}/15 enviado con exito: Juez {judges[i]} -> {participants[i]}')
    except Exception as e:
        print(f'Error en registro {i+1}/15: {e}')

print('Simulacion terminada.')
