import time
import threading
import serial
import glob
import requests
import subprocess
import os
from datetime import datetime

# ── Configuración ─────────────────────────────────────────────────────────────
SERVER_URL    = "https://industries-hereby-presently-movers.trycloudflare.com/datos"
DISPOSITIVO   = "Raspberry_Relieve1"

# ── Puertos SIM7600 ─────────────────────────────────
# if02 = AT commands para red/celular
CEL_PORT = "/dev/serial/by-id/usb-SimTech__Incorporated_SimTech__Incorporated_0123456789ABCDEF-if02-port0"

# if04 = AT commands para GPS
GPS_PORT = "/dev/serial/by-id/usb-SimTech__Incorporated_SimTech__Incorporated_0123456789ABCDEF-if04-port0"

GPS_BAUDRATE = 115200
CEL_BAUDRATE = 115200

# Lock para que nada más toque CEL_PORT mientras activar_datos_celular() corre
_cel_lock = threading.Lock()
GPS_INTERVALO = 1                # segundos entre lecturas GPS
ENVIO_INTERVALO = 1              # segundos entre envíos al servidor

# APN se detecta automáticamente según la operadora de la SIM
APN = None   # se asigna en activar_datos_celular()

# Base de datos de operadoras → APN
# MCC+MNC : (nombre, apn)
_APN_DB = {
    # México
    "334020": ("Telcel",        "internet.itelcel.com"),
    "334050": ("AT&T MX",       "internet"),
    "334030": ("Movistar MX",   "internet.movistar.mx"),
    "334040": ("Iusacell/Bait", "internet"),
    "334140": ("Izzi",          "izzimovil.izzi.mx"),
    "334090": ("AT&T MX",       "internet"),
    # USA (por si hay roaming)
    "310410": ("AT&T US",       "phone"),
    "310260": ("T-Mobile US",   "fast.t-mobile.com"),
    "311480": ("Verizon",       "vzwinternet"),
    # fallback genérico
    "default":("Desconocida",   "internet"),
}

def _detectar_apn(ser) -> str:
    """Consulta al SIM7600 la operadora registrada y devuelve el APN correcto."""
    _at(ser, 'AT+COPS=3,2', espera=1)   # forzar formato numérico
    r = _at(ser, 'AT+COPS?', espera=2)
    print(f"[CEL] Operadora raw: {r.strip()}")

    mccmnc = None
    for linea in r.splitlines():
        if "+COPS:" in linea:
            partes = linea.split(",")
            if len(partes) >= 3:
                mccmnc = partes[2].strip().strip('"')
                break

    if mccmnc and mccmnc in _APN_DB:
        nombre, apn = _APN_DB[mccmnc]
    else:
        nombre, apn = _APN_DB["default"]
        print(f"[CEL] MCC+MNC '{mccmnc}' no reconocido, usando APN genérico")

    print(f"[CEL] Operadora detectada: {nombre} → APN: {apn}")
    return apn

# Batería VE.Direct — Victron SmartShunt
BAT_PORT     = "/dev/serial/by-id/usb-VictronEnergy_BV_VE_Direct_cable_A_AUI12345"
BAT_BAUDRATE = 19200

# Motor VE.Direct (USB)
MOTOR_BAUDRATE = 19200
MOTOR_PORT = "/dev/serial/by-id/usb-VictronEnergy_BV_VE_Direct_cable_VEAD2A4V-if00-port0"  # se autodetecta

_lock = threading.Lock()
estado = {
    "latitud":      None,
    "longitud":     None,
    # Batería
    "voltaje":      None,
    "corriente":    None,
    "potencia":     None,
    "soc":          None,
    "ttg":          None,
    "ah_consumidos": None,   # corriente acumulada (Ah), tomada del campo CE del VE.Direct
    # Motor
    "motor_v":      None,
    "motor_i":      None,
    "motor_p":      None,
    "motor_rpm":    None,
    "motor_temp":   None,
}

# Interfaz de red de la SIM (usb0, wwan0, etc.) — se detecta al conectar
_sim_interfaz: str | None = None


# ══════════════════════════════════════════════════════════════════════════════
# CELULAR — Activar datos SIM7600
# ══════════════════════════════════════════════════════════════════════════════

def _at(ser, cmd: str, espera: float = 1.0) -> str:
    ser.write((cmd + "\r\n").encode())
    time.sleep(espera)
    return ser.read(ser.in_waiting or 1024).decode("ascii", errors="ignore")


def _detectar_interfaz_sim() -> str | None:
    """
    Busca la interfaz de red que expone el SIM7600 en modo ECM/RNDIS.
    Candidatos típicos: usb0, usb1, wwan0, eth1.
    Devuelve el nombre de la interfaz si tiene IP asignada, None si no.
    """
    candidatos = ["usb0", "usb1", "wwan0", "wwan1", "eth1"]
    for iface in candidatos:
        resultado = subprocess.run(
            ["ip", "addr", "show", iface],
            capture_output=True, text=True
        )
        if resultado.returncode == 0 and "inet " in resultado.stdout:
            print(f"[CEL] Interfaz SIM detectada: {iface}")
            return iface
    return None


def _ping_por_interfaz(iface: str | None) -> bool:
    """Hace ping forzando una interfaz específica. Si iface=None usa la ruta por defecto."""
    cmd = ["ping", "-c", "2", "-W", "5", "8.8.8.8"]
    if iface:
        cmd = ["ping", "-c", "2", "-W", "5", "-I", iface, "8.8.8.8"]
    resultado = subprocess.run(cmd, capture_output=True, text=True)
    return resultado.returncode == 0


def activar_datos_celular() -> bool:
    """
    Levanta la conexión de datos del SIM7600 usando el modo ECM (USB network).
    Usa CEL_PORT (interfaz AT de red, if02) — NUNCA el mismo puerto que usa
    el thread de GPS (GPS_PORT, if04), para evitar que dos threads compitan
    por el mismo descriptor serial y se corrompan las respuestas AT.

    Returns:
        True si la conexión quedó activa por SIM, False si falló.
    """
    global _sim_interfaz

    with _cel_lock:
        print("[CEL] Iniciando conexión de datos celular...")

        try:
            ser = serial.Serial()
            ser.port = CEL_PORT
            ser.baudrate = CEL_BAUDRATE
            ser.timeout = 2
            
            # Deshabilitar señales de control por hardware para evitar el Broken Pipe
            ser.setDTR(False)
            ser.setRTS(False)
            
            ser.open()
        except serial.SerialException as e:
            print(f"[CEL] No se pudo abrir puerto AT (CEL_PORT): {e}")
            return False

        try:
            # 1. Verificar que el módulo responde
            r = _at(ser, "AT", espera=1)
            if "OK" not in r:
                print(f"[CEL] Módulo no responde: {r!r}")
                return False
            print("[CEL] Módulo AT OK")

            # 2. Verificar SIM
            r = _at(ser, "AT+CPIN?", espera=2)
            if "READY" not in r:
                print(f"[CEL] SIM no lista: {r!r}")
                return False
            print("[CEL] SIM OK")

            # 3. Verificar registro en red
            for _ in range(10):
                r = _at(ser, "AT+CREG?", espera=1)
                if ",1" in r or ",5" in r:   # 1=registrado, 5=roaming
                    print("[CEL] Registrado en red")
                    break
                print("[CEL] Esperando registro en red...")
                time.sleep(2)
            else:
                print("[CEL] No se pudo registrar en red")
                return False

            # 4. Verificar calidad de señal
            r = _at(ser, "AT+CSQ", espera=1)
            print(f"[CEL] Señal: {r.strip()}")

            # 5. Detectar APN automáticamente
            apn = _detectar_apn(ser)

            # 5a. Desactivar contexto PDP primero para forzar reconexión limpia
            _at(ser, "AT+CGACT=0,1", espera=3)
            time.sleep(1)

            # 5b. Configurar APN
            _at(ser, f'AT+CGDCONT=1,"IP","{apn}"', espera=1)

            # 5c. Activar contexto PDP — reintentar hasta 3 veces
            pdp_ok = False
            for intento in range(3):
                r = _at(ser, "AT+CGACT=1,1", espera=10)
                print(f"[CEL] Activar PDP (intento {intento+1}): {r.strip()}")
                if "OK" in r and "ERROR" not in r:
                    pdp_ok = True
                    break
                print("[CEL] PDP falló, esperando 5s...")
                time.sleep(5)

            if not pdp_ok:
                print("[CEL] ✗ No se pudo activar PDP — SIM sin datos")
                return False

            # 6. Cerrar y reabrir NETOPEN limpiamente
            _at(ser, "AT+NETCLOSE", espera=3)
            time.sleep(1)
            r = _at(ser, "AT+NETOPEN", espera=8)
            print(f"[CEL] NETOPEN: {r.strip()}")
            if "+NETOPEN: 0" not in r and "ERROR: 3" not in r:
                print("[CEL] Reintentando NETOPEN...")
                time.sleep(3)
                r = _at(ser, "AT+NETOPEN", espera=8)
                print(f"[CEL] NETOPEN retry: {r.strip()}")

            # 7. Obtener IP asignada
            time.sleep(2)
            r = _at(ser, "AT+IPADDR", espera=5)
            print(f"[CEL] IP: {r.strip()}")
            if "ERROR" in r or not r.strip():
                print("[CEL] ✗ No se obtuvo IP — la SIM no levantó conexión")
                return False

        except Exception as e:
            print(f"[CEL] Error configurando módulo: {e}")
            return False
        finally:
            ser.close()

        # 8. Esperar a que el SO registre la interfaz de red del SIM7600
        print("[CEL] Buscando interfaz de red de la SIM...")
        time.sleep(3)
        for _ in range(10):
            iface = _detectar_interfaz_sim()
            if iface:
                _sim_interfaz = iface
                break
            time.sleep(2)
        else:
            print("[CEL] ✗ No se encontró interfaz de red del SIM7600 (usb0/wwan0)")
            print("[CEL]   Verifica que el SIM7600 esté en modo ECM/RNDIS")
            return False

        # 9. Verificar que la SIM tiene internet real (ping forzado por su interfaz)
        if _ping_por_interfaz(_sim_interfaz):
            print(f"[CEL] ✓ SIM con internet activo en interfaz {_sim_interfaz}")
            return True

        print("[CEL] ✗ La SIM no tiene acceso a internet")
        return False


def thread_watchdog_celular():
    """
    Verifica cada 60 segundos que la SIM siga con internet.
    - Hace ping forzando la interfaz de la SIM (no WiFi).
    - Si se cae, intenta reconectar por SIM.
    """
    global _sim_interfaz
    while True:
        time.sleep(60)

        iface = _sim_interfaz or _detectar_interfaz_sim()
        if not iface:
            print("[CEL] Watchdog: interfaz SIM no encontrada — reconectando...")
            activar_datos_celular()
            continue

        if not _ping_por_interfaz(iface):
            print(f"[CEL] Watchdog: sin internet en {iface} — reconectando...")
            _sim_interfaz = None
            activar_datos_celular()
        else:
            print(f"[CEL] Watchdog: ✓ SIM activa en {iface}")


# ══════════════════════════════════════════════════════════════════════════════
# BATERÍA — Victron SmartShunt VE.Direct
# ══════════════════════════════════════════════════════════════════════════════

class VEDirectParser:
    def __init__(self):
        self._bloque: dict[str, str] = {}

    def alimentar(self, linea: str) -> dict | None:
        linea = linea.strip()
        if not linea or "\t" not in linea:
            return None
        clave, valor = linea.split("\t", 1)
        if clave == "Checksum":
            bloque = dict(self._bloque)
            self._bloque.clear()
            return bloque if bloque else None
        self._bloque[clave] = valor
        return None


def _convertir_ve(clave: str, valor: str):
    try:
        n = int(valor)
        if clave == "V":   return n / 1000.0
        if clave == "I":   return n / 1000.0
        if clave == "SOC": return n / 10.0
        return n
    except (ValueError, TypeError):
        return valor


def _detectar_puerto_bat() -> str | None:
    candidatos = []
    for pat in ["/dev/serial0", "/dev/serial1",
                "/dev/ttyAMA0", "/dev/ttyAMA1", "/dev/ttyAMA2",
                "/dev/ttyAMA3", "/dev/ttyAMA4", "/dev/ttyAMA5"]:
        if os.path.exists(pat):
            candidatos.append(pat)
    print(f"[BAT] Puertos GPIO candidatos: {candidatos}")
    return candidatos[0] if candidatos else None


def thread_bateria():
    puerto = BAT_PORT if os.path.exists(BAT_PORT) else _detectar_puerto_bat()
    if not puerto:
        print("[BAT] No se encontró puerto VE.Direct.")
        return

    print(f"[BAT] Conectando a SmartShunt en {puerto} @ {BAT_BAUDRATE} baud...")
    try:
        ser = serial.Serial(puerto, BAT_BAUDRATE,
                            bytesize=serial.EIGHTBITS,
                            parity=serial.PARITY_NONE,
                            stopbits=serial.STOPBITS_ONE,
                            timeout=2)
    except serial.SerialException as e:
        print(f"[BAT] No se pudo abrir el puerto: {e}")
        return

    print("[BAT] Leyendo VE.Direct...")
    parser = VEDirectParser()

    try:
        while True:
            raw = ser.readline()
            if not raw:
                continue
            bloque = parser.alimentar(raw.decode("utf-8", errors="replace"))
            if bloque:
                v   = _convertir_ve("V",   bloque.get("V",   ""))
                i   = _convertir_ve("I",   bloque.get("I",   ""))
                p   = _convertir_ve("P",   bloque.get("P",   ""))
                soc = _convertir_ve("SOC", bloque.get("SOC", ""))
                ttg = bloque.get("TTG", None)   # minutos restantes

                # Corriente acumulada (Consumed Energy), viene en mAh, normalmente negativo
                ce_raw = bloque.get("CE", None)
                ah_consumidos = None
                if ce_raw is not None:
                    try:
                        ah_consumidos = abs(int(ce_raw)) / 1000.0
                    except ValueError:
                        ah_consumidos = None

                if isinstance(v, (int, float)):
                    with _lock:
                        estado.update(
                            voltaje=v, corriente=i, potencia=p,
                            soc=soc if isinstance(soc, float) else None,
                            ttg=int(ttg) if ttg and ttg != "---" else None,
                            ah_consumidos=ah_consumidos,
                        )
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    print(f"[BAT  {ts}] {v} V | {i} A | {p} W | SOC: {soc}% | Ah consum.: {ah_consumidos}")
    except Exception as e:
        print(f"[BAT] Error: {e}")
    finally:
        if ser.is_open:
            ser.close()


# ══════════════════════════════════════════════════════════════════════════════
# MOTOR — Victron VE.Direct por USB
# ══════════════════════════════════════════════════════════════════════════════

def _detectar_puerto_motor() -> str | None:
    """
    Busca un puerto ttyUSB* disponible que no sea el GPS/CEL ni la batería GPIO.
    Prueba comunicación VE.Direct en cada candidato.
    """
    puertos_ocupados = {
        GPS_PORT, CEL_PORT, BAT_PORT,
        "/dev/serial0", "/dev/serial1",
        "/dev/ttyAMA0", "/dev/ttyAMA1",
    }

    candidatos = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
    candidatos = [p for p in candidatos if p not in puertos_ocupados]

    if not candidatos:
        print("[MOTOR] No hay puertos USB disponibles (todos ocupados o ninguno conectado)")
        return None

    print(f"[MOTOR] Puertos candidatos: {candidatos}")

    for puerto in candidatos:
        print(f"[MOTOR] Probando {puerto}...")
        try:
            ser = serial.Serial(puerto, MOTOR_BAUDRATE,
                                bytesize=serial.EIGHTBITS,
                                parity=serial.PARITY_NONE,
                                stopbits=serial.STOPBITS_ONE,
                                timeout=2)
            time.sleep(0.5)
            datos = ser.read(64)
            ser.close()
            if datos:
                print(f"[MOTOR] VE.Direct detectado en {puerto}")
                return puerto
            else:
                print(f"[MOTOR] {puerto} sin datos VE.Direct")
        except Exception as e:
            print(f"[MOTOR] {puerto} error: {e}")

    print("[MOTOR] No se encontró módulo VE.Direct en ningún puerto USB")
    return None


def thread_motor():
    """Thread que lee el módulo Victron del motor por USB."""
    global MOTOR_PORT
    MOTOR_PORT = _detectar_puerto_motor()
    if not MOTOR_PORT:
        print("[MOTOR] No se encontró módulo — el supervisor reintentará más tarde.")
        time.sleep(15)
        return

    print(f"[MOTOR] Conectando en {MOTOR_PORT} @ {MOTOR_BAUDRATE} baud...")
    try:
        ser = serial.Serial(MOTOR_PORT, MOTOR_BAUDRATE,
                            bytesize=serial.EIGHTBITS,
                            parity=serial.PARITY_NONE,
                            stopbits=serial.STOPBITS_ONE,
                            timeout=2)
    except serial.SerialException as e:
        print(f"[MOTOR] No se pudo abrir puerto: {e}")
        return

    print("[MOTOR] Leyendo VE.Direct...")
    parser = VEDirectParser()

    try:
        while True:
            raw = ser.readline()
            if not raw:
                continue
            bloque = parser.alimentar(raw.decode("utf-8", errors="replace"))
            if bloque:
                v    = _convertir_ve("V",   bloque.get("V",   ""))
                i    = _convertir_ve("I",   bloque.get("I",   ""))
                p    = _convertir_ve("P",   bloque.get("P",   ""))
                rpm  = bloque.get("RPM",  None)
                temp = bloque.get("T",    None)

                if isinstance(v, (int, float)):
                    with _lock:
                        estado.update(
                            motor_v=v, motor_i=i, motor_p=p,
                            motor_rpm=int(rpm) if rpm else None,
                            motor_temp=int(temp) if temp else None,
                        )

                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    extras = ""
                    if rpm:  extras += f" | RPM: {rpm}"
                    if temp: extras += f" | Temp: {temp}°C"
                    print(f"[MOTOR {ts}] {v} V | {i} A | {p} W{extras}")

    except Exception as e:
        print(f"[MOTOR] Error: {e}")
    finally:
        if ser.is_open:
            ser.close()


# ══════════════════════════════════════════════════════════════════════════════
# GPS — SIM7600 AT+CGPSINFO
# ══════════════════════════════════════════════════════════════════════════════
# IMPORTANTE: este thread usa GPS_PORT exclusivamente para leer posición.
# Ya NO manda datos al servidor — eso lo hace thread_envio_servidor(), que
# corre independiente. Así, si el GPS pierde fix o el puerto se atora,
# el envío de batería/motor al servidor sigue funcionando sin interrupción.

def _parsear_cgpsinfo(respuesta: str) -> tuple[str, str] | None:
    for linea in respuesta.splitlines():
        if "+CGPSINFO:" in linea:
            partes = linea.replace("+CGPSINFO:", "").strip().split(",")
            if len(partes) >= 4 and partes[0].strip():
                return partes[0].strip(), partes[2].strip()
    return None


def thread_gps():
    print(f"[GPS] Conectando en {GPS_PORT} @ {GPS_BAUDRATE} baud...")
    try:
        ser = serial.Serial(GPS_PORT, GPS_BAUDRATE, timeout=1)
    except serial.SerialException as e:
        print(f"[GPS] No se pudo abrir el puerto: {e}")
        return

    time.sleep(2)
    _at(ser, "AT+CGPS=1", espera=2)
    print("[GPS] GPS encendido. Leyendo posición...")

    try:
        while True:
            t0 = time.monotonic()
            respuesta = _at(ser, "AT+CGPSINFO", espera=1)
            print(f"[GPS RAW] {respuesta.strip()}")

            coords = _parsear_cgpsinfo(respuesta)

            with _lock:
                if coords:
                    estado["latitud"], estado["longitud"] = coords
                else:
                    estado["latitud"], estado["longitud"] = None, None

            if not coords:
                print("[GPS] Sin fix todavía...")

            restante = GPS_INTERVALO - (time.monotonic() - t0)
            if restante > 0:
                time.sleep(restante)
    except Exception as e:
        print(f"[GPS] Error: {e}")
    finally:
        ser.is_open and ser.close()


# ══════════════════════════════════════════════════════════════════════════════
# ENVÍO AL SERVIDOR — thread independiente, no depende del GPS
# ══════════════════════════════════════════════════════════════════════════════

def thread_envio_servidor():
    """
    Manda telemetría al servidor cada ENVIO_INTERVALO segundos, leyendo el
    snapshot más reciente de `estado`. Es independiente del thread de GPS:
    si el GPS pierde fix, truena, o su puerto se atora, este thread sigue
    mandando datos de batería/motor con lat/lon en null.
    """
    while True:
        t0 = time.monotonic()
        with _lock:
            snap = dict(estado)

        ts = datetime.now().isoformat()
        _enviar_servidor({
            "dispositivo_id": DISPOSITIVO,
            "timestamp":      ts,
            "latitud":        snap["latitud"],
            "longitud":       snap["longitud"],
            # Batería
            "voltaje":        snap["voltaje"],
            "corriente":      snap["corriente"],
            "potencia":       snap["potencia"],
            "soc":            snap["soc"],
            "ttg_min":        snap["ttg"],
            "ah_consumidos":  snap["ah_consumidos"],
            # Motor
            "motor_voltaje":  snap["motor_v"],
            "motor_corriente":snap["motor_i"],
            "motor_potencia": snap["motor_p"],
            "motor_rpm":      snap["motor_rpm"],
            "motor_temp":     snap["motor_temp"],
        })

        restante = ENVIO_INTERVALO - (time.monotonic() - t0)
        if restante > 0:
            time.sleep(restante)


# ══════════════════════════════════════════════════════════════════════════════
# SERVIDOR
# ══════════════════════════════════════════════════════════════════════════════

def _enviar_servidor(datos: dict) -> None:
    """
    Envía datos al servidor.
    Si hay interfaz SIM activa, fuerza el envío por esa interfaz
    vinculando el socket a su IP, para no salir por WiFi accidentalmente.
    """
    import socket

    def _obtener_ip_interfaz(iface: str) -> str | None:
        try:
            resultado = subprocess.run(
                ["ip", "-4", "addr", "show", iface],
                capture_output=True, text=True
            )
            for linea in resultado.stdout.splitlines():
                linea = linea.strip()
                if linea.startswith("inet "):
                    return linea.split()[1].split("/")[0]
        except Exception:
            pass
        return None

    session = requests.Session()
    _orig_create = None
    ip_sim = None

    if _sim_interfaz:
        ip_sim = _obtener_ip_interfaz(_sim_interfaz)
        if ip_sim:
            _orig_create = socket.create_connection
            def _bound_create(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):
                return _orig_create(address, timeout=timeout, source_address=(ip_sim, 0))
            socket.create_connection = _bound_create

    try:
        r = session.post(SERVER_URL, json=datos, timeout=8)
        if r.status_code in (200, 201):
            via = f"SIM({_sim_interfaz})" if _sim_interfaz else "red"
            print(f"[SERVER] ✓ Enviado vía {via} ({datos['timestamp']})")
        else:
            print(f"[SERVER] ✗ Error {r.status_code}")
    except requests.exceptions.ConnectionError:
        print("[SERVER] ✗ Sin conexión.")
    except requests.exceptions.Timeout:
        print("[SERVER] ✗ Timeout.")
    except Exception as e:
        print(f"[SERVER] ✗ {e}")
    finally:
        if _orig_create:
            socket.create_connection = _orig_create
        session.close()


# ══════════════════════════════════════════════════════════════════════════════
# SUPERVISOR — reinicia threads que mueran inesperadamente
# ══════════════════════════════════════════════════════════════════════════════

def supervisor():
    """
    Lanza todos los threads de trabajo y los vigila. Si alguno muere por una
    excepción no controlada (puerto desconectado, error de parseo, etc.),
    lo vuelve a lanzar automáticamente en vez de dejarlo muerto para siempre.
    """
    definiciones = {
        "bateria":        thread_bateria,
        "motor":          thread_motor,
        "gps":            thread_gps,
        "watchdog_cel":   thread_watchdog_celular,
        "envio_servidor": thread_envio_servidor,
    }

    vivos: dict[str, threading.Thread] = {}
    for nombre, fn in definiciones.items():
        t = threading.Thread(target=fn, daemon=True, name=nombre)
        t.start()
        vivos[nombre] = t

    while True:
        time.sleep(10)
        for nombre, fn in definiciones.items():
            if not vivos[nombre].is_alive():
                print(f"[SUPERVISOR] ⚠ Thread '{nombre}' murió — reiniciando...")
                t = threading.Thread(target=fn, daemon=True, name=nombre)
                t.start()
                vivos[nombre] = t


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=== Relieve Monitor ===")
    print(f"Servidor : {SERVER_URL}")
    print(f"GPS      : {GPS_PORT}")
    print(f"Celular  : {CEL_PORT}")
    print(f"Batería  : {BAT_PORT}")
    print("Presiona Ctrl+C para detener.\n")

    # 1. Activar internet celular antes de todo
    if not activar_datos_celular():
        print("[WARN] Sin internet celular — los datos se enviarán cuando haya conexión.")

    # 2. Lanzar supervisor (este arranca y vigila todos los demás threads)
    threading.Thread(target=supervisor, daemon=True, name="supervisor").start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO] Detenido por el usuario.")