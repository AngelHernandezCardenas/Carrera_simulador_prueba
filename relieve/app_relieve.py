"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  app_relieve.py — Módulo independiente para datos de Raspberry Pi           ║
║  Puerto: 5001  (no interfiere con el servidor principal en 5000)            ║
║  Arranca con:  python relieve/app_relieve.py                                ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import json
import time
import threading
import requests as _requests
from datetime import datetime
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
        return round(decimal, 7)
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
        lat = float(lat_nmea)
        lon = float(lon_nmea)
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
        "device_label": BRIDGE_PARTICIPANTE,
        "speed_kmh":    None,
        # Campos extra (visibles en el log del servidor principal)
        "voltaje":      datos.get("voltaje"),
        "soc":          datos.get("soc"),
    }

    try:
        r = _requests.post(BRIDGE_GPS_URL, json=payload, timeout=3)
        if r.status_code == 200:
            print(f"[BRIDGE] ✓ Punto enviado al mapa principal ({lat:.5f}, {lon:.5f})")
        else:
            print(f"[BRIDGE] ✗ Servidor respondió {r.status_code}")
    except Exception as e:
        print(f"[BRIDGE] ✗ No se pudo conectar al mapa principal: {e}")

# ── App ────────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = "relieve-secret-key"
socketio = SocketIO(app, cors_allowed_origins="*")

# ── Estado en memoria ─────────────────────────────────────────────────────────
_lock = threading.Lock()
# Almacena el último paquete por dispositivo
dispositivos: dict[str, dict] = {}
# Historial de los últimos 200 paquetes (todos los dispositivos mezclados)
historial: list[dict] = []
HISTORIAL_MAX = 200

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
    <h1>🛰️ Relieve Monitor</h1>
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
      <div class="icon">📡</div>
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
            <th>Dispositivo</th>
            <th>Latitud</th>
            <th>Longitud</th>
            <th>V (V)</th>
            <th>I (A)</th>
            <th>W</th>
            <th>SOC %</th>
            <th>TTG min</th>
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
    const latRaw  = d.latitud  ?? '—';
    const lonRaw  = d.longitud ?? '—';
    const mapsUrl = (d.latitud && d.longitud)
      ? `https://www.google.com/maps?q=${latRaw},${lonRaw}`
      : null;

    card.innerHTML = `
      <div class="device-name">📡 ${id}</div>
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
          <div class="metric-label">Voltaje</div>
          <div class="metric-value accent">${fmt(d.voltaje, 2)} V</div>
        </div>
        <div class="metric">
          <div class="metric-label">Corriente</div>
          <div class="metric-value yellow">${fmt(d.corriente, 2)} A</div>
        </div>
        <div class="metric">
          <div class="metric-label">Potencia</div>
          <div class="metric-value">${fmt(d.potencia, 1)} W</div>
        </div>
        <div class="metric">
          <div class="metric-label">Tiempo restante</div>
          <div class="metric-value ${d.ttg_min > 0 ? 'green' : 'muted'}">${d.ttg_min != null ? d.ttg_min + ' min' : '—'}</div>
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
      ${mapsUrl ? `<a href="${mapsUrl}" target="_blank" class="gps-link">🗺️ Ver en Google Maps</a>` : ''}
    `;
  }

  // ── Agregar fila a la tabla ────────────────────────────────────────────────
  function agregarFila(p, isNew = false) {
    const tbody = document.getElementById('logBody');
    const tr = document.createElement('tr');
    if (isNew) tr.className = 'new-row';
    tr.innerHTML = `
      <td class="muted">${p.timestamp ?? '—'}</td>
      <td>${p.dispositivo_id ?? '—'}</td>
      <td>${p.latitud  ?? '—'}</td>
      <td>${p.longitud ?? '—'}</td>
      <td>${fmt(p.voltaje, 2)}</td>
      <td>${fmt(p.corriente, 2)}</td>
      <td>${fmt(p.potencia, 1)}</td>
      <td>${fmt(p.soc, 1)}</td>
      <td>${p.ttg_min ?? '—'}</td>
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
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"status": "error", "msg": "JSON inválido"}), 400

    # Aseguramos timestamp si la Rasp no lo manda
    if "timestamp" not in data:
        data["timestamp"] = datetime.now().isoformat()

    dispositivo_id = data.get("dispositivo_id", "desconocido")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(
        f"[{ts}] 📡 {dispositivo_id} | "
        f"GPS: {data.get('latitud','?')},{data.get('longitud','?')} | "
        f"SOC: {data.get('soc','?')}% | "
        f"{data.get('voltaje','?')}V / {data.get('corriente','?')}A / {data.get('potencia','?')}W"
    )

    # Guardar en memoria
    with _lock:
        dispositivos[dispositivo_id] = data
        historial.append(data)
        if len(historial) > HISTORIAL_MAX:
            historial.pop(0)

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
    print("  🛰️  Relieve Monitor — Servidor de Raspberry Pi")
    print("=" * 60)
    print(f"  Dashboard : http://localhost:{port}/")
    print(f"  Endpoint  : http://localhost:{port}/datos  (POST)")
    print(f"  Estado    : http://localhost:{port}/estado (GET)")
    print("=" * 60)
    print("  En la Raspberry Pi, cambia SERVER_URL a:")
    print(f"  https://<tu-tunel>.trycloudflare.com/datos")
    print("=" * 60)
    socketio.run(app, host="0.0.0.0", port=port, debug=False)
