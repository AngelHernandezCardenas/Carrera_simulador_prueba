"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  app_relieve.py — Módulo independiente para datos de Raspberry Pi           ║
║  Puerto: 5001  (no interfiere con el servidor principal en 5000)            ║
║  Arranca con:  python relieve/app_relieve.py                                ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import csv
import json
import time
import threading
import requests as _requests
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string
from flask_socketio import SocketIO

# ── Puente al mapa principal ──────────────────────────────────────────────────
# Pon BRIDGE_ENABLED = True para que los datos de la Rasp aparezcan
# también en el mapa de corredores (localhost:5000/mapa).
BRIDGE_ENABLED    = True
BRIDGE_GPS_URL    = os.environ.get("BRIDGE_GPS_URL", "http://localhost:5000/gps")
BRIDGE_PARTICIPANTE = "Raspberry_Relieve"   # nombre que aparecerá en el mapa


def _nmea_a_decimal(coord: str, hemisferio: str) -> float | None:
    """
    Convierte coordenadas NMEA (DDMM.MMMM o DDDMM.MMMM) a grados decimales.
    Ejemplo: '1912.3456', 'N'  →  19.205760
    """
    try:
        coord = coord.strip()
        if not coord:
            return None
        punto = coord.index('.')
        # Los minutos son siempre los últimos 2 dígitos antes del punto
        grados  = int(coord[:punto - 2])
        minutos = float(coord[punto - 2:])
        decimal = grados + minutos / 60.0
        if hemisferio.strip().upper() in ('S', 'W'):
            decimal = -decimal
        return round(decimal, 5)
    except Exception:
        return None


def _reenviar_al_mapa(datos: dict) -> None:
    """
    Convierte el paquete de la Rasp al formato del endpoint /gps
    del servidor principal y lo reenvía.
    """
    if not BRIDGE_ENABLED:
        return

    lat_nmea = datos.get("latitud",  "")
    lon_nmea = datos.get("longitud", "")

    # El SIM7600 devuelve NMEA (ej. '1912.3456') SIN hemisferio separado.
    # Por simplicidad asumimos N/W para México; ajusta si la Rasp ya manda
    # decimales puros (en ese caso se usan directamente).
    try:
        lat = round(float(lat_nmea), 5)
        lon = round(float(lon_nmea), 5)
        # Si el valor tiene más de 2 dígitos antes del punto decimal
        # probablemente sea NMEA; si es razonable como decimal, lo usamos tal cual.
        if abs(lat) > 90:
            lat = _nmea_a_decimal(lat_nmea, 'N')
            lon = _nmea_a_decimal(lon_nmea, 'W')
    except (ValueError, TypeError):
        lat = _nmea_a_decimal(lat_nmea, 'N')
        lon = _nmea_a_decimal(lon_nmea, 'W')

    if lat is None or lon is None:
        return

    payload = {
        "latitude":     lat,
        "longitude":    lon,
        "device_id":    datos.get("dispositivo_id", "rasp"),
        "device_label": f"Bicicleta {datos.get('dispositivo_id', 'rasp')}",
        "participante": f"bicicleta_{datos.get('dispositivo_id', 'rasp')}",
        "speed_kmh":    None,
        # Batería principal
        "voltaje":          datos.get("voltaje"),
        "corriente":        datos.get("corriente"),
        "potencia":         datos.get("potencia"),
        "soc":              datos.get("soc"),
        "ttg_min":          datos.get("ttg_min"),
        "ah_consumidos":    datos.get("ah_consumidos"),
        # Motor
        "motor_voltaje":    datos.get("motor_voltaje"),
        "motor_corriente":  datos.get("motor_corriente"),
        "motor_potencia":   datos.get("motor_potencia"),
        "motor_rpm":        datos.get("motor_rpm"),
        "motor_temp":       datos.get("motor_temp"),
    }

    try:
        print(f"[BRIDGE] [INFO] Intentando enviar datos al servidor principal: {BRIDGE_GPS_URL} ...")
        r = _requests.post(BRIDGE_GPS_URL, json=payload, timeout=3)
        if r.status_code == 200:
            print(f"[BRIDGE] [EXITO] Punto enviado al mapa principal ({lat:.5f}, {lon:.5f}). Datos: {payload}")
        else:
            print(f"[BRIDGE] [ERROR] Servidor respondio con codigo {r.status_code}. Respuesta: {r.text}")
    except _requests.exceptions.Timeout:
        print(f"[BRIDGE] [ERROR] Timeout (tiempo de espera agotado) al conectar al mapa principal.")
    except _requests.exceptions.ConnectionError:
        print(f"[BRIDGE] [ERROR] Falla de conexion al intentar alcanzar el mapa principal.")
    except Exception as e:
        print(f"[BRIDGE] [ERROR] Excepcion desconocida al conectar al mapa principal: {e}")

# ── CSV ───────────────────────────────────────────────────────────────────────
# Los CSV se guardan junto al script: relieve/relieve_datos_YYYYMMDD.csv
CSV_DIR = Path(__file__).parent

CSV_COLUMNAS = [
    "timestamp", "dispositivo_id",
    "latitud", "longitud",
    "voltaje", "corriente", "potencia", "potencia_calculada", "soc", "ttg_min",
    "ah_consumidos",
    "motor_voltaje", "motor_corriente", "motor_potencia",
    "motor_rpm", "motor_temp",
    # Campos calculados en servidor
    "tiempo_acumulado(s)", "delta_t_s", "energia_wh", "energia_acumulada_wh",
]


def _guardar_csv(datos: dict) -> None:
    """
    Añade una fila al CSV diario.  Si el archivo no existe lo crea con cabecera.
    Cualquier campo extra que llegue en 'datos' y no esté en CSV_COLUMNAS
    se guarda igualmente al final.
    """
    hoy = datetime.now().strftime("%Y%m%d")
    ruta = CSV_DIR / f"relieve_datos_{hoy}.csv"

    # Columnas = las predefinidas + cualquier campo extra que llegue
    campos_extra = [k for k in datos if k not in CSV_COLUMNAS]
    columnas = CSV_COLUMNAS + campos_extra

    nuevo = not ruta.exists()
    try:
        with open(ruta, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
            if nuevo:
                writer.writeheader()
                print(f"[CSV] Archivo creado: {ruta}")
            writer.writerow(datos)
    except Exception as e:
        print(f"[CSV] [ERROR] No se pudo escribir en el CSV: {e}")


# ── App ────────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = "relieve-secret-key"
socketio = SocketIO(app, cors_allowed_origins="*")

# ── Estado en memoria ─────────────────────────────────────────────────────────
_lock = threading.Lock()
_last_known_telemetry: dict[str, dict] = {}
# Almacena el último paquete por dispositivo
dispositivos: dict[str, dict] = {}
# Historial de los últimos 200 paquetes (todos los dispositivos mezclados)
historial: list[dict] = []
HISTORIAL_MAX = 200

# ── Stats acumulados por dispositivo (calculados en servidor) ─────────────────
# _device_stats[id] = { "start": datetime, "last": datetime, "energia_acum_wh": float }
_device_stats: dict[str, dict] = {}

# ── HTML del dashboard (todo en este mismo archivo, sin dependencias) ─────────
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Relieve Monitor · Dashboard</title>
  <script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    :root {
      --bg:       #0d0f14;
      --surface:  #161920;
      --card:     #1d2130;
      --border:   #2a2f42;
      --accent:   #6c8eff;
      --green:    #3de8a0;
      --yellow:   #f5c542;
      --red:      #ff5f6d;
      --text:     #e2e8f0;
      --muted:    #6b7280;
      --radius:   14px;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: 'Inter', sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
    }

    /* ── Header ── */
    header {
      background: linear-gradient(135deg, #1a1f35 0%, #0d0f14 100%);
      border-bottom: 1px solid var(--border);
      padding: 18px 32px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      position: sticky;
      top: 0;
      z-index: 100;
      backdrop-filter: blur(10px);
    }
    header h1 {
      font-size: 1.4rem;
      font-weight: 700;
      background: linear-gradient(90deg, var(--accent), var(--green));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }
    header .subtitle { font-size: 0.78rem; color: var(--muted); margin-top: 2px; }

    .status-dot {
      width: 10px; height: 10px; border-radius: 50%;
      background: var(--red);
      box-shadow: 0 0 8px var(--red);
      transition: all 0.3s ease;
      display: inline-block;
      margin-right: 8px;
    }
    .status-dot.vivo { background: var(--green); box-shadow: 0 0 10px var(--green); }

    /* ── Layout ── */
    main { padding: 28px 32px; max-width: 1400px; margin: 0 auto; }

    .grid-devices { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 20px; }

    /* ── Tarjeta de dispositivo ── */
    .device-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 20px;
      transition: border-color 0.3s, box-shadow 0.3s;
      position: relative;
      overflow: hidden;
    }
    .device-card::before {
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0;
      height: 3px;
      background: linear-gradient(90deg, var(--accent), var(--green));
    }
    .device-card.pulse { border-color: var(--accent); box-shadow: 0 0 20px rgba(108,142,255,0.15); }

    .device-name {
      font-size: 1rem;
      font-weight: 600;
      color: var(--text);
      margin-bottom: 4px;
    }
    .device-ts {
      font-size: 0.73rem;
      color: var(--muted);
      font-family: 'JetBrains Mono', monospace;
      margin-bottom: 18px;
    }

    /* ── Métricas ── */
    .metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

    .metric {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px 14px;
    }
    .metric.full { grid-column: 1 / -1; }
    .metric-label {
      font-size: 0.68rem;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      color: var(--muted);
      margin-bottom: 5px;
    }
    .metric-value {
      font-family: 'JetBrains Mono', monospace;
      font-size: 1.25rem;
      font-weight: 500;
      color: var(--text);
    }
    .metric-value.accent { color: var(--accent); }
    .metric-value.green  { color: var(--green);  }
    .metric-value.yellow { color: var(--yellow); }
    .metric-value.red    { color: var(--red);    }

    /* ── SOC bar ── */
    .soc-bar-wrap { margin-top: 8px; }
    .soc-bar-bg {
      background: var(--border);
      border-radius: 99px;
      height: 6px;
      overflow: hidden;
    }
    .soc-bar-fill {
      height: 100%;
      border-radius: 99px;
      transition: width 0.6s ease, background 0.3s;
    }

    /* ── GPS map link ── */
    .gps-link {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 0.78rem;
      color: var(--accent);
      text-decoration: none;
      margin-top: 8px;
      padding: 5px 10px;
      border: 1px solid rgba(108,142,255,0.3);
      border-radius: 6px;
      transition: background 0.2s;
    }
    .gps-link:hover { background: rgba(108,142,255,0.1); }

    /* ── Sin dispositivos ── */
    .empty-state {
      text-align: center;
      padding: 80px 20px;
      color: var(--muted);
    }
    .empty-state .icon { font-size: 3rem; margin-bottom: 16px; }
    .empty-state p { font-size: 0.95rem; line-height: 1.7; }

    /* ── Log de paquetes ── */
    .log-section { margin-top: 36px; }
    .log-section h2 { font-size: 1rem; font-weight: 600; color: var(--muted); margin-bottom: 14px; }
    .log-table-wrap { overflow-x: auto; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.78rem;
      font-family: 'JetBrains Mono', monospace;
    }
    thead th {
      text-align: left;
      padding: 10px 12px;
      color: var(--muted);
      border-bottom: 1px solid var(--border);
      font-weight: 500;
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }
    tbody tr { border-bottom: 1px solid rgba(255,255,255,0.04); transition: background 0.15s; }
    tbody tr:hover { background: rgba(255,255,255,0.03); }
    tbody td { padding: 8px 12px; color: var(--text); }
    tbody td.muted { color: var(--muted); }
    .new-row td { animation: fadeRow 1s ease-out; }
    @keyframes fadeRow {
      from { background: rgba(108,142,255,0.12); }
      to   { background: transparent; }
    }

    /* ── Responsive ── */
    @media (max-width: 640px) {
      main { padding: 16px; }
      header { padding: 14px 16px; }
      .grid-devices { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>

<header>
  <div>
    <h1>️ Relieve Monitor</h1>
    <div class="subtitle">Raspberry Pi · Telemetría en tiempo real</div>
  </div>
  <div style="display:flex;align-items:center;font-size:0.82rem;color:var(--muted)">
    <span class="status-dot" id="connDot"></span>
    <span id="connLabel">Conectando…</span>
  </div>
</header>

<main>
  <div class="grid-devices" id="devicesGrid">
    <div class="empty-state" id="emptyState">
      <div class="icon"></div>
      <p>Esperando datos de la Raspberry Pi…<br>
         Asegúrate de que el servidor esté corriendo<br>
         y que la URL del servidor en la Rasp apunte aquí.</p>
    </div>
  </div>

  <div class="log-section">
    <h2>▸ Últimos paquetes recibidos</h2>
    <div class="log-table-wrap">
      <table>
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>T. Acum. (s)</th>
            <th>Dispositivo</th>
            <th>Latitud</th>
            <th>Longitud</th>
            <th>V (V)</th>
            <th>I (A)</th>
            <th>W (Rasp)</th>
            <th>W (Calc)</th>
            <th>SOC %</th>
            <th>TTG min</th>
            <th title="Intervalo entre paquetes">Δt (s)</th>
            <th>E (Wh)</th>
            <th>E acum. (Wh)</th>
          </tr>
        </thead>
        <tbody id="logBody"></tbody>
      </table>
    </div>
  </div>
</main>

<script>
  const socket = io();
  const devices = {};

  // ── Conexión ──────────────────────────────────────────────────────────────
  socket.on('connect', () => {
    document.getElementById('connDot').classList.add('vivo');
    document.getElementById('connLabel').textContent = 'Conectado';
  });
  socket.on('disconnect', () => {
    document.getElementById('connDot').classList.remove('vivo');
    document.getElementById('connLabel').textContent = 'Desconectado';
  });

  // ── Datos iniciales al cargar ──────────────────────────────────────────────
  socket.on('estado_inicial', (data) => {
    data.dispositivos.forEach(d => actualizarTarjeta(d));
    data.historial.slice().reverse().forEach(p => agregarFila(p));
  });

  // ── Paquete nuevo ──────────────────────────────────────────────────────────
  socket.on('nuevo_paquete', (paquete) => {
    actualizarTarjeta(paquete);
    agregarFila(paquete, true);
  });

  // ── Construir / actualizar tarjeta ─────────────────────────────────────────
  function actualizarTarjeta(d) {
    document.getElementById('emptyState')?.remove();

    const id = d.dispositivo_id;
    let card = document.getElementById('card-' + id);
    if (!card) {
      card = document.createElement('div');
      card.className = 'device-card';
      card.id = 'card-' + id;
      document.getElementById('devicesGrid').appendChild(card);
    }

    // Animación de pulso
    card.classList.add('pulse');
    setTimeout(() => card.classList.remove('pulse'), 800);

    const soc = d.soc ?? 0;
    const socColor = soc > 60 ? '#3de8a0' : soc > 25 ? '#f5c542' : '#ff5f6d';
    const latRaw  = d.latitud  != null ? Number(d.latitud).toFixed(5)  : '—';
    const lonRaw  = d.longitud != null ? Number(d.longitud).toFixed(5) : '—';
    const mapsUrl = (d.latitud && d.longitud)
      ? `https://www.google.com/maps?q=${latRaw},${lonRaw}`
      : null;

    card.innerHTML = `
      <div class="device-name"> ${id}</div>
      <div class="device-ts">Último dato: ${d.timestamp ?? '—'}</div>
      <div class="metrics">
        <div class="metric full">
          <div class="metric-label">Estado de Carga (SOC)</div>
          <div class="metric-value" style="color:${socColor}">${fmt(soc, 1)} %</div>
          <div class="soc-bar-wrap">
            <div class="soc-bar-bg">
              <div class="soc-bar-fill" style="width:${Math.min(soc,100)}%;background:${socColor}"></div>
            </div>
          </div>
        </div>
        <div class="metric">
          <div class="metric-label">Voltaje Bat</div>
          <div class="metric-value accent">${fmt(d.voltaje, 2)} V</div>
        </div>
        <div class="metric">
          <div class="metric-label">Corriente Bat</div>
          <div class="metric-value yellow">${fmt(d.corriente, 2)} A</div>
        </div>
        <div class="metric">
          <div class="metric-label">Potencia Bat</div>
          <div class="metric-value">${fmt(d.potencia, 1)} W</div>
        </div>
        <div class="metric">
          <div class="metric-label">Latitud</div>
          <div class="metric-value" style="font-size:0.85rem">${latRaw}</div>
        </div>
        <div class="metric">
          <div class="metric-label">Longitud</div>
          <div class="metric-value" style="font-size:0.85rem">${lonRaw}</div>
        </div>
      </div>
      ${mapsUrl ? `<a href="${mapsUrl}" target="_blank" class="gps-link">️ Ver en Google Maps</a>` : ''}
    `;
  }

  // ── Estado acumulado por dispositivo (energía y tiempo) ───────────────────
  const devStats = {};
  // devStats[id] = { startMs, lastMs, energiaAcumuladaWh }

  function fmtDuracion(ms) {
    const s = Math.max(0, Math.floor(ms / 1000));
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return [h, m, sec].map(v => String(v).padStart(2, '0')).join(':');
  }

  // ── Agregar fila a la tabla ────────────────────────────────────────────────
  function agregarFila(p, isNew = false) {
    const tbody = document.getElementById('logBody');
    const tr = document.createElement('tr');
    if (isNew) tr.className = 'new-row';

    const devId = p.dispositivo_id ?? 'desconocido';
    const ahora = Date.now();
    let tiempoAcum = '—';
    let eWh        = '—';
    let eAcumStr   = '—';
    let deltaS     = '—';

    if (isNew) {
      if (!devStats[devId]) {
        devStats[devId] = { startMs: ahora, lastMs: ahora, energiaAcumuladaWh: 0 };
      }
      const st = devStats[devId];

      // Tiempo acumulado desde el primer paquete del dispositivo en segundos
      tiempoAcum = Math.max(0, Math.floor((ahora - st.startMs) / 1000));

      // Δt entre paquetes
      const deltaMs = ahora - st.lastMs;
      if (st.lastMs !== st.startMs && deltaMs > 0) {
        deltaS = (deltaMs / 1000).toFixed(1);
      }

      // E(Wh) = P × (Δt / 3_600_000)   [Δt en ms]
      const potencia = Number(p.potencia_calculada != null ? p.potencia_calculada : p.potencia);
      if (Number.isFinite(potencia) && deltaMs > 0 && st.lastMs !== st.startMs) {
        const sampleWh = potencia * (deltaMs / 3_600_000);
        st.energiaAcumuladaWh += sampleWh;
        eWh = sampleWh.toFixed(4);
      }
      eAcumStr = Number.isFinite(st.energiaAcumuladaWh) ? st.energiaAcumuladaWh.toFixed(4) : '—';
      st.lastMs = ahora;
    }

    const latStr = p.latitud  != null ? Number(p.latitud).toFixed(5)  : '—';
    const lonStr = p.longitud != null ? Number(p.longitud).toFixed(5) : '—';

    tr.innerHTML = `
      <td class="muted">${p.timestamp ?? '—'}</td>
      <td style="color:var(--accent);font-weight:500">${tiempoAcum}</td>
      <td>${devId}</td>
      <td>${latStr}</td>
      <td>${lonStr}</td>
      <td>${fmt(p.voltaje, 2)}</td>
      <td>${fmt(p.corriente, 2)}</td>
      <td>${fmt(p.potencia, 1)}</td>
      <td>${fmt(p.potencia_calculada, 2)}</td>
      <td>${fmt(p.soc, 1)}</td>
      <td>${p.ttg_min ?? '—'}</td>
      <td class="muted">${deltaS}</td>
      <td style="color:var(--yellow)">${eWh}</td>
      <td style="color:var(--green);font-weight:600">${eAcumStr}</td>
    `;
    tbody.insertBefore(tr, tbody.firstChild);
    // Limitar filas en pantalla a 100
    while (tbody.rows.length > 100) tbody.deleteRow(tbody.rows.length - 1);
  }

  function fmt(val, dec) {
    return (val != null && val !== '') ? Number(val).toFixed(dec) : '—';
  }
</script>
</body>
</html>
"""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    """Dashboard web en tiempo real."""
    return render_template_string(DASHBOARD_HTML)


@app.route("/datos", methods=["POST"])
def recibir_datos():
    """
    Recibe un JSON de la Raspberry Pi con los campos:
      dispositivo_id, timestamp, latitud, longitud,
      voltaje, corriente, potencia, soc, ttg_min
    """
    try:
        data = request.get_json(force=True, silent=False)
        print(f"[INFO] Datos recibidos en /datos: {data}")
    except Exception as e:
        print(f"[ERROR] Falla al decodificar JSON recibido de la Rasp: {e}")
        return jsonify({"status": "error", "msg": "JSON invalido"}), 400

    if not data:
        print("[ERROR] Peticion sin datos (JSON vacio).")
        return jsonify({"status": "error", "msg": "JSON vacio"}), 400

    # Aseguramos timestamp si la Rasp no lo manda
    if "timestamp" not in data:
        data["timestamp"] = datetime.now().isoformat()
        print("[WARN] Timestamp faltante en los datos de la Rasp, agregando localmente.")

    dispositivo_id = data.get("dispositivo_id", "desconocido")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Guardar en memoria y aplicar parche de hardware
    with _lock:
        if dispositivo_id not in _last_known_telemetry:
            _last_known_telemetry[dispositivo_id] = {}
            
        last = _last_known_telemetry[dispositivo_id]
        
        for k, v in list(data.items()):
            if k in ["dispositivo_id", "timestamp"]:
                continue
            # Si el hardware mandó vacío o nulo, recuperamos el último valor válido
            if v in [None, ""]:
                if k in last:
                    data[k] = last[k]
            else:
                last[k] = v
                
        # --- GPS FALSO TEMPORAL ELIMINADO ---
        # Ya no inyectamos una coordenada falsa de Monterrey. Si no hay fix GPS,
        # simplemente no tendra ubicacion y no se reenviara al mapa principal.

        dispositivos[dispositivo_id] = data
        historial.append(data)
        if len(historial) > HISTORIAL_MAX:
            historial.pop(0)

    print(
        f"[{ts}] [RECIBIDO] Dispositivo: {dispositivo_id} | "
        f"GPS: {data.get('latitud','?')},{data.get('longitud','?')} | "
        f"BAT: {data.get('voltaje','?')}V {data.get('corriente','?')}A {data.get('potencia','?')}W SOC:{data.get('soc','?')}% TTG:{data.get('ttg_min','?')}m | "
        f"MOT: {data.get('motor_voltaje','?')}V {data.get('motor_corriente','?')}A {data.get('motor_potencia','?')}W RPM:{data.get('motor_rpm','?')} T:{data.get('motor_temp','?')}C"
    )

    # ── Calcular campos de energía y tiempo en el servidor ──────────────────
    ahora = datetime.now()
    with _lock:
        if dispositivo_id not in _device_stats:
            _device_stats[dispositivo_id] = {
                "start":           ahora,
                "last":            ahora,
                "energia_acum_wh": 0.0,
                "last_potencia":   0.0  # <--- Agregamos esto para recordar la potencia previa
            }
        st = _device_stats[dispositivo_id]

        # Tiempo acumulado desde el primer paquete
        delta_total = (ahora - st["start"]).total_seconds()
        data["tiempo_acumulado(s)"] = int(delta_total)

        # Δt entre paquetes consecutivos
        delta_s = (ahora - st["last"]).total_seconds()
        if st["last"] != st["start"] and delta_s > 0:
            data["delta_t_s"] = round(delta_s, 2)
        else:
            data["delta_t_s"] = None

        # ── NUEVO CÁLCULO DE ENERGÍA (Filtro de ceros + Regla del Trapecio) ──
        try:
            v_val = float(data.get("voltaje") or 0.0)
            i_val = float(data.get("corriente") or 0.0)
            potencia_actual = v_val * i_val
        except (TypeError, ValueError):
            potencia_actual = 0.0
            
        data["potencia_calculada"] = round(potencia_actual, 2)

        potencia_anterior = st["last_potencia"]
 
        # Filtro: Si cae a 0 abruptamente, asumimos que es un microcorte del sensor y usamos el valor anterior
        if potencia_actual == 0.0 and potencia_anterior > 0.0:
            potencia_actual = potencia_anterior
            data["potencia_calculada"] = round(potencia_actual, 2)  # Sobreescribimos el payload para que el CSV y UI vean el dato corregido

        if data["delta_t_s"] is not None and delta_s > 0:
            # Integración trapezoidal
            potencia_promedio = (potencia_actual + potencia_anterior) / 2.0
            e_wh = potencia_promedio * (delta_s / 3600.0)
            
            st["energia_acum_wh"] += e_wh
            data["energia_wh"]           = round(e_wh, 6)
            data["energia_acumulada_wh"] = round(st["energia_acum_wh"], 6)
        else:
            data["energia_wh"]           = None
            data["energia_acumulada_wh"] = round(st["energia_acum_wh"], 6)

        # Actualizar estado para la siguiente iteración
        st["last_potencia"] = potencia_actual
        st["last"] = ahora

    # Guardar en CSV
    _guardar_csv(data)

    # Emitir al dashboard propio
    socketio.emit("nuevo_paquete", data)

    # ── Puente: reenviar al mapa principal de corredores ──────────────────
    threading.Thread(
        target=_reenviar_al_mapa,
        args=(data,),
        daemon=True
    ).start()

    return jsonify({"status": "ok", "ts": ts}), 200


@app.route("/estado", methods=["GET"])
def estado_actual():
    """Devuelve el estado actual de todos los dispositivos (útil para debugging)."""
    with _lock:
        return jsonify({
            "dispositivos": list(dispositivos.values()),
            "total_paquetes": len(historial),
        })


# ── WebSocket: enviar estado inicial al conectarse ────────────────────────────

@socketio.on("connect")
def on_connect():
    with _lock:
        socketio.emit("estado_inicial", {
            "dispositivos": list(dispositivos.values()),
            "historial":    historial[-50:],   # últimos 50
        }, to=request.sid)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("RELIEVE_PORT", 5001))
    print("=" * 60)
    print("  ️  Relieve Monitor — Servidor de Raspberry Pi")
    print("=" * 60)
    print(f"  Dashboard : http://localhost:{port}/")
    print(f"  Endpoint  : http://localhost:{port}/datos  (POST)")
    print(f"  Estado    : http://localhost:{port}/estado (GET)")
    print("=" * 60)
    print("  En la Raspberry Pi, cambia SERVER_URL a:")
    print(f"  https://<tu-tunel>.trycloudflare.com/datos")
    print("=" * 60)
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)