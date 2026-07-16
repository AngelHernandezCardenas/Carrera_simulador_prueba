#!/bin/bash

# Activar el entorno virtual automáticamente
source .venv/bin/activate

echo "Iniciando Servidor Principal (app.py) en puerto 5000..."
python3 app.py &
PID_APP=$!

echo "Iniciando Servidor Raspberry (app_relieve.py) en puerto 5001..."
cd relieve
python3 app_relieve.py &
PID_RELIEVE=$!
cd ..

echo "Iniciando túnel de Cloudflare..."
cloudflared tunnel run --token eyJhIjoiMTBhMmE2YzRjNzQ5NjlkOWQ1M2NlMGQ5ZGU5ZTIxOGYiLCJ0IjoiNzMwOTdiYzctNWMyMC00MzExLThmNzMtZWVkNGU4YjViMThkIiwicyI6Ik5UVmhOMk16WmpNdFkyWmlaaTAwTmpreUxUa3paV1V0T0RJMk9UVmtaV05rWVRWaiJ9 &
PID_TUNNEL=$!

# Función para cerrar todo ordenadamente al presionar Ctrl+C
cleanup() {
    echo ""
    echo "Apagando todos los servicios..."
    kill $PID_APP
    kill $PID_RELIEVE
    kill $PID_TUNNEL
    echo "¡Servicios apagados exitosamente!"
    exit 0
}

# Capturar señal de Ctrl+C para ejecutar la función cleanup
trap cleanup SIGINT SIGTERM

echo ""
echo "¡Todo está corriendo! Presiona Ctrl+C en esta consola para apagar todo."
echo "----------------------------------------------------------------------"

# Mantener el script corriendo y escuchar las terminales
wait $PID_APP $PID_RELIEVE $PID_TUNNEL
