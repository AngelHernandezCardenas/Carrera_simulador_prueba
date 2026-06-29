# Guía de Inicio: Carrera Tracker

Este documento detalla los pasos exactos para arrancar todo el sistema desde cero. El sistema se compone de tres partes principales:
1. **El Servidor Principal (Backend y Mapa)**
2. **El Túnel (Cloudflare) para acceso desde internet**
3. **La Aplicación Móvil (Expo/React Native)**

---

## 1. Arrancar el Servidor Principal

El servidor central está construido en Python (Flask) y es el encargado de recibir los datos GPS y mostrar el mapa 3D.

1. Abre una nueva terminal.
2. Navega a la carpeta principal del proyecto:
   ```bash
   cd ~/Persona1
   ```
3. Activa el entorno virtual y ejecuta el servidor:
   ```bash
   ./.venv/bin/python app.py
   ```
4. El servidor estará corriendo localmente. Puedes ver el mapa abriendo en tu navegador de la computadora:
   👉 **http://localhost:5000/mapa**

---

## 2. Abrir el Túnel de Cloudflare

Para que la aplicación móvil en tu teléfono pueda enviarle datos al servidor de tu computadora a través de internet, necesitamos exponer el puerto 5000 usando Cloudflare.

1. Abre una **segunda terminal**.
2. Ejecuta el comando del túnel apuntando al puerto 5000:
   ```bash
   cloudflared tunnel --url http://localhost:5000
   ```
3. En los registros que aparezcan en la terminal, busca una línea que diga algo parecido a:
   `https://alguna-palabra-rara.trycloudflare.com`
4. **Copia esa URL (enlace)**. Este es el puente de internet hacia tu computadora.

---

## 3. Arrancar la Aplicación Móvil

La aplicación móvil está construida con React Native (Expo) y sirve para transmitir la ubicación GPS.

1. Abre una **tercera terminal**.
2. Navega a la carpeta de la aplicación móvil:
   ```bash
   cd ~/Persona1/tracker-app
   ```
3. Arranca Expo en modo LAN (la computadora y el teléfono deben estar en la misma red Wi-Fi):
   ```bash
   npx expo start
   ```
4. Aparecerá un código QR en la terminal.
5. Abre la aplicación **Expo Go** en tu teléfono (Android o iOS) y escanea el código QR para abrir la app.

---

## 4. Conectar y Probar el Sistema

Una vez que tengas la aplicación abierta en tu teléfono:

1. Verás un campo de texto que dice **"URL del Servidor"**.
2. **Pega ahí la URL de Cloudflare** que copiaste en el paso 2 (ej. `https://alguna-palabra-rara.trycloudflare.com`). Esa URL corresponde al servidor Flask; no es el túnel de Expo.
3. Pon un nombre para el corredor en "Nombre del Corredor".
4. Presiona el botón **"Registrar y Conectar"**.
5. Finalmente, presiona **"Iniciar Captura"**.
6. ¡Listo! Camina o muévete un poco, y deberías ver cómo tu punto avanza en tiempo real en la pantalla del mapa en tu computadora (`localhost:5000/mapa`).
