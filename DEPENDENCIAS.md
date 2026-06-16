# Requisitos y Dependencias del Proyecto

Este documento detalla todas las herramientas y librerías necesarias para poder correr el sistema completo desde cero en cualquier otra computadora.

## 1. Backend (Servidor Python / Flask)

### Pre-requisitos del Sistema:
- **Python 3.10** o superior.
- **pip** (Instalador de paquetes de Python).
- **cloudflared** (Para generar el túnel hacia internet).

### Instalación de Librerías (requirements.txt):
Acabo de generar automáticamente el archivo `requirements.txt` en la raíz de tu proyecto. Este archivo contiene las versiones exactas de las librerías que estás usando actualmente. Para instalarlas en un equipo nuevo, solo debes correr:

```bash
# Crear entorno virtual (Recomendado)
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

Las librerías principales incluyen:
- `Flask==3.1.3` (El servidor web).
- `Flask-SocketIO==5.6.1` (Para la transmisión de datos GPS en tiempo real).
- `python-dotenv==1.2.2` (Para variables de entorno).

---

## 2. Aplicación Móvil (React Native / Expo)

La aplicación móvil no usa un `requirements.txt`, sino que utiliza el estándar de Node.js llamado `package.json` (ubicado dentro de la carpeta `/tracker-app`).

### Pre-requisitos del Sistema:
- **Node.js** (Versión 18 o superior recomendada).
- **npm** o **yarn** (Gestor de paquetes de Node).
- Aplicación **Expo Go** instalada en tu teléfono móvil para pruebas físicas.

### Instalación de Librerías (package.json):
Para descargar todas las dependencias móviles en un equipo nuevo, debes entrar a la carpeta de la app y correr el comando de instalación:

```bash
cd tracker-app
npm install
```

Las librerías principales que usa el proyecto móvil son:
- `expo` (Framework base).
- `expo-location` (Para acceder a la antena GPS del teléfono, tanto en primer como en segundo plano).
- `expo-sensors` (Para acceder al Acelerómetro y giroscopio).
- `socket.io-client` (Para conectarse al servidor Python y transmitir los datos).
- `@react-native-async-storage/async-storage` (Para guardar el ID del dispositivo y que no se pierda si cierras la app).

Para arrancar el servidor de desarrollo móvil, recuerda que el comando es:
```bash
npx expo start --tunnel
```
