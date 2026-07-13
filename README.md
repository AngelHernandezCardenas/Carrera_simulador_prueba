# Carrera Tracker (WonWheels)

¡Bienvenido al repositorio de **Carrera Tracker (WonWheels)**! Este es un sistema integral diseñado para rastrear en tiempo real a los corredores/equipos durante una carrera o evento, administrar puntajes, cargas, detección de colores por visión artificial, y mostrar la ubicación de los participantes en un mapa 3D en vivo.

El proyecto es altamente interactivo y se compone de varios módulos que trabajan juntos a través de internet y redes locales.

---

## 📖 1. ¿Qué hace este programa? (Anotaciones Principales)

- **Rastreo GPS y Telemetría en Tiempo Real:** Recibe la ubicación de los participantes y datos de telemetría (batería, voltaje, corriente, etc.) a través de una aplicación móvil (React Native/Expo) o **hardware IoT (Raspberry Pi / módulos ESP)** y los dibuja en un mapa web 3D interactivo.
- **Gestión de Puntos de Control (Checkpoints):** Evalúa cuando un participante se acerca a un punto de control, calcula distancias y valida su progreso en la carrera.
- **Detección por Visión Artificial (YOLO):** El sistema puede detectar pelotas de colores (Rojo, Blanco, Negro) usando un modelo YOLO para asignar pesos o puntajes automáticamente.
- **Sincronización con Google Sheets (Excel en la nube):** Actualiza en tiempo real una hoja de cálculo (Google Sheets) con los puntajes, cargas (loads) y el historial de cada equipo cuando interactúan con los jueces en los distintos puntos de control.
- **Diferenciación de Jueces:** Identifica si el juez es de tipo "Normal" (suma cargas y puntajes) o de "Home-Base" (Checkpoint 4 - Descarga en Rectoría), restando el peso actual y enviándolo a la base.

---

## 🏗️ 2. Arquitectura y Componentes

El ecosistema se divide en 4 componentes vitales:

1. **Servidor Principal (Backend):** Desarrollado en Python con **Flask** y **Socket.io**. Procesa la lógica de negocio, mantiene el estado de la carrera, sirve la interfaz web (mapa, scoreboard) y recibe las transmisiones.
2. **Aplicación Móvil (Client/Tracker):** Creada con **React Native (Expo)**. Es la encargada de obtener las coordenadas GPS del celular y transmitirlas mediante WebSockets al servidor central.
3. **Cloudflare Tunnel:** Actúa como puente para exponer el servidor local (en el puerto `5000`) hacia internet, generando una URL pública y segura (`https://*.trycloudflare.com`) a la que se conecta la app móvil sin necesidad de IPs públicas fijas.
4. **Google Apps Script (Webhook):** Script intermedio en JavaScript (`webhook_google_sheets.js`) que recibe peticiones del backend y modifica directamente las filas y columnas del Google Sheet (Excel).
5. **Hardware IoT (Raspberry Pi / ESP):** Módulos físicos instalados en los vehículos/bicicletas (usando microcontroladores ESP32/ESP8266 o computadoras Raspberry Pi) que capturan telemetría eléctrica en tiempo real (voltaje, corriente, potencia, RPM, temperatura) y envían estos datos por internet al servidor principal para ser mostrados en el mapa web.

---

## ⚙️ 3. Funciones Principales

- `/mapa`: Interfaz principal 3D donde se ven los avatares moviéndose con base en el GPS.
- `/scoreboard`: Tabla de clasificación en vivo con cálculo de puntos totales, considerando tiempo, energía y desafíos.
- `/jurados` y `/var`: Interfaces dedicadas para la validación y evaluación por parte de los jueces.
- **Algoritmo de Distancia de Haversine:** Mide de forma precisa las distancias en la superficie terrestre entre el corredor y los *checkpoints*.
- **Integración de Cámara (Visión):** Automatiza la contabilidad de las entregas usando visión por computadora para clasificar cargas según su color.

---

## 🚀 4. Guía de Instalación y Uso

### A. Arrancar el Servidor Central (Python)

1. **Requisitos:** Python 3.10+, y las librerías listadas en `requirements.txt`.
2. Clona este repositorio y abre una terminal en la raíz (`~/Persona1`).
3. Crea y activa tu entorno virtual, luego instala las dependencias:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. Ejecuta la aplicación:
   ```bash
   python app.py
   ```
5. El backend estará corriendo en http://localhost:5000/mapa.

### B. Generar el Túnel de Internet (Cloudflare)

Para que los teléfonos envíen datos desde cualquier red móvil al servidor local:
1. Abre una segunda terminal y asegúrate de tener `cloudflared` instalado.
2. Corre el siguiente comando:
   ```bash
   cloudflared tunnel --url http://localhost:5000
   ```
3. Copia la URL que te genera (ej. `https://alguna-palabra-rara.trycloudflare.com`). **Esta será tu URL de Servidor.**

### C. Arrancar y Conectar la App Móvil

1. **Requisitos:** Node.js, npm, y la app Expo Go en el teléfono.
2. Abre una tercera terminal y ve a la app móvil:
   ```bash
   cd tracker-app
   npm install
   npx expo start
   ```
3. Escanea el código QR con **Expo Go** en tu móvil.
4. Cuando abra la app, ingresa la URL de Cloudflare obtenida en el paso B, ingresa el nombre de tu equipo/corredor y pulsa **"Registrar y Conectar"**.
5. Presiona **"Iniciar Captura"**. ¡El punto se moverá en el mapa de tu PC!

---

## 📊 5. ¿Cómo enlazar con Excels (Google Sheets)?

El proyecto no utiliza un simple archivo `.xlsx` local, sino que se enlaza en tiempo real a la nube utilizando **Google Sheets** y **Google Apps Script (Webhooks)** para tener tableros compartidos a nivel global.

### Cómo funciona el enlace:

1. **El Script de Google:** Dentro del proyecto encontrarás el archivo `webhook_google_sheets.js`. Debes copiar el contenido de ese archivo e ir a tu documento de Google Sheets -> `Extensiones` -> `Apps Script`. Pégalo, guárdalo y haz un despliegue (Deploy) como "Aplicación web". Google te dará una URL (Webhook).
2. **Conexión con Python:** En tu archivo de variables de entorno (`.env`) o configuración (`config.py`), debe configurarse la variable `GOOGLE_APPS_SCRIPT_WEBHOOK_URL` con la URL obtenida en el paso 1.
3. **Flujo de datos (Loads):** 
   - Cuando un juez "Normal" califica pelotas (Ej: Negra = 5 puntos, Roja = 3 puntos, Blanca = 1 punto), el backend manda un evento JSON al Webhook. El Google Sheet busca la fila del equipo y **suma** los puntos a la columna `Current load`.
   - Cuando el participante llega a la base (Checkpoint 4 / Rectoria-Descarga / Juez de Home-Base), el sistema manda un evento especial llamado `update_home_base`. El Webhook toma todo el peso de `Current load`, lo vacía (lo deja en 0) y lo **transfiere** a la columna `Load at home`.
4. **Historial:** Todas y cada una de las interacciones se registran automáticamente en una pestaña llamada `Loading` para tener un registro histórico auditable de qué juez evaluó, a qué hora y con qué colores.

---

## 📁 6. Estructura de Carpetas

- `/`: Archivos principales del backend (`app.py`, `checkpoints.py`, `datos.py`, `Puntaje.py`).
- `/tracker-app`: Código fuente completo de la aplicación móvil React Native.
- `/templates` y `/static`: Interfaz web (HTML, CSS, JS) para los mapas y scoreboards.
- `/colores` y `/ROBOFLOW`: Lógica y modelos entrenados de Visión Artificial para la detección de pesos.
- `/galeria.json` y `/participantes.json`: Bases de datos locales ligeras para el caché de fotos, posiciones y registros.
