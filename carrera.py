"""
Reto Internacional Alleycat – Bicicletas Eléctricas
Visualizador de Carrera en Tiempo Real
===============================================
Uso:
    python rally_app.py --csv datos.csv [--intervalo 10] [--port 8050]

Columnas del CSV:
    numParticipante, tiempo, longitud, latitud,
    bateriaBicicleta, consumo, emisiones, cargaDeObjetos
Columna opcional: _name
"""

import argparse, os
from datetime import datetime
import pandas as pd
import folium
import dash
from dash import dcc, html, dash_table, Input, Output, State, no_update

# ──────────────────────────────────────────────
#  Paleta
# ──────────────────────────────────────────────
RIDER_COLORS = [
    "#2D6A4F","#1A759F","#D62828","#F4A261","#6A994E",
    "#9B2335","#0A9396","#5E548E","#AE2012","#52B788",
    "#457B9D","#F77F00","#6D6875","#3D405B","#74C69D",
]
C_BG     = "#F0F7F0"
C_WHITE  = "#FFFFFF"
C_GREEN  = "#2D6A4F"
C_LIME   = "#52B788"
C_SUN    = "#F4A261"
C_RED    = "#D62828"
C_TEXT   = "#1B2B1B"
C_MUTED  = "#6B8F6B"
C_BORDER = "#C5DFC5"
C_HEADER = "#1B3A2D"

def rcolor(pid_list, pid):
    return RIDER_COLORS[sorted(pid_list).index(int(pid)) % len(RIDER_COLORS)]

# ──────────────────────────────────────────────
#  CSV helpers
# ──────────────────────────────────────────────
CSV_PATH = ""   # se asigna en main()

def load_df():
    df = pd.read_csv(CSV_PATH)
    df["numParticipante"] = df["numParticipante"].astype(int)
    df.sort_values(["numParticipante","tiempo"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df

def latest_snap(df):
    return df.groupby("numParticipante").last().reset_index()

def rider_name(df, pid):
    if "_name" not in df.columns:
        return ""
    rows = df[df["numParticipante"] == int(pid)]
    if rows.empty:
        return ""
    n = str(rows.iloc[-1]["_name"])
    return "" if n == "nan" else n

# ──────────────────────────────────────────────
#  Mapa Folium → HTML string
# ──────────────────────────────────────────────
def build_map(df, selected_pid=None):
    snap     = latest_snap(df)
    pid_list = sorted(df["numParticipante"].unique().tolist())

    if selected_pid is not None:
        row = snap[snap["numParticipante"] == int(selected_pid)]
        if not row.empty:
            clat, clon, zoom = float(row.iloc[0]["latitud"]), float(row.iloc[0]["longitud"]), 16
        else:
            clat, clon, zoom = snap["latitud"].mean(), snap["longitud"].mean(), 14
    else:
        clat, clon, zoom = snap["latitud"].mean(), snap["longitud"].mean(), 14

    m = folium.Map(
        location=[clat, clon],
        zoom_start=zoom,
        tiles="OpenStreetMap",
        prefer_canvas=True,
    )

    for pid in pid_list:
        color   = rcolor(pid_list, pid)
        pdf     = df[df["numParticipante"] == pid].sort_values("tiempo")
        is_sel  = (selected_pid is None or int(selected_pid) == pid)
        opacity = 1.0 if is_sel else 0.2
        weight  = 4   if is_sel else 1.5

        coords = list(zip(pdf["latitud"], pdf["longitud"]))
        name   = rider_name(df, pid)
        label  = f"#{pid}" + (f" {name}" if name else "")

        # Trazar ruta
        if len(coords) >= 2:
            folium.PolyLine(
                locations=coords,
                color=color, weight=weight, opacity=opacity,
                tooltip=label,
            ).add_to(m)

        # Marcador posición actual
        last = pdf.iloc[-1]
        bat  = float(last["bateriaBicicleta"])
        bat_c = C_LIME if bat > 50 else (C_SUN if bat > 20 else C_RED)
        radius = 10 if is_sel else 6

        popup_html = f"""
        <div style="font-family:monospace;min-width:190px">
          <div style="font-size:14px;font-weight:800;color:{color};
                      border-bottom:2px solid {color};padding-bottom:5px;margin-bottom:8px">
            {label}
          </div>
          <div style="display:grid;grid-template-columns:auto 1fr;gap:3px 10px;font-size:11px">
            <span style="color:#666">🕒 Tiempo</span>
            <span style="font-weight:600">{last['tiempo']}</span>
            <span style="color:#666">🔋 Batería</span>
            <span style="font-weight:700;color:{bat_c}">{bat:.1f}%</span>
            <span style="color:#666">⚡ Consumo</span>
            <span style="font-weight:600">{last['consumo']} kWh</span>
            <span style="color:#666">🌿 CO₂</span>
            <span style="font-weight:600">{last['emisiones']} kg</span>
            <span style="color:#666">📦 Carga</span>
            <span style="font-weight:600">{last['cargaDeObjetos']}</span>
          </div>
        </div>
        """

        folium.CircleMarker(
            location=[last["latitud"], last["longitud"]],
            radius=radius,
            color="white", weight=2,
            fill=True, fill_color=color, fill_opacity=opacity,
            tooltip=label,
            popup=folium.Popup(popup_html, max_width=230),
        ).add_to(m)

        # Etiqueta #N
        if is_sel or selected_pid is None:
            folium.Marker(
                location=[last["latitud"], last["longitud"]],
                icon=folium.DivIcon(
                    html=f"""<div style="font-family:sans-serif;font-size:11px;
                        font-weight:800;color:{color};
                        text-shadow:0 0 4px #fff,0 0 4px #fff,0 0 4px #fff;
                        white-space:nowrap;margin-left:13px;margin-top:-8px;
                        pointer-events:none">#{pid}</div>""",
                    icon_size=(40, 20), icon_anchor=(0, 10),
                ),
            ).add_to(m)

    return m.get_root().render()

# ──────────────────────────────────────────────
#  Tabla
# ──────────────────────────────────────────────
TABLE_COLS = [
    {"name":"#",        "id":"numParticipante"},
    {"name":"Tiempo",   "id":"tiempo"},
    {"name":"Lat",      "id":"latitud"},
    {"name":"Lon",      "id":"longitud"},
    {"name":"Bat %",    "id":"bateriaBicicleta"},
    {"name":"kWh",      "id":"consumo"},
    {"name":"CO₂ kg",   "id":"emisiones"},
    {"name":"Carga",    "id":"cargaDeObjetos"},
]

def snap_records(snap):
    cols = ["numParticipante","tiempo","latitud","longitud",
            "bateriaBicicleta","consumo","emisiones","cargaDeObjetos"]
    r = snap[[c for c in cols if c in snap.columns]].copy()
    for col in ["latitud","longitud"]:
        r[col] = r[col].round(5)
    r["bateriaBicicleta"] = r["bateriaBicicleta"].round(1)
    r["consumo"]    = r["consumo"].round(3)
    r["emisiones"]  = r["emisiones"].round(4)
    return r.to_dict("records")

# ──────────────────────────────────────────────
#  Tarjeta detalle
# ──────────────────────────────────────────────
def _stat(icon, label, value, val_color=None):
    return html.Div(
        style={"backgroundColor":C_BG,"borderRadius":"8px",
               "padding":"8px 10px","border":f"1px solid {C_BORDER}"},
        children=[
            html.Div(f"{icon} {label}", style={
                "fontFamily":"IBM Plex Mono,monospace","fontSize":"8px",
                "color":C_MUTED,"letterSpacing":"1px","marginBottom":"3px",
                "textTransform":"uppercase"}),
            html.Div(str(value), style={
                "fontFamily":"IBM Plex Mono,monospace","fontSize":"12px",
                "fontWeight":"700","color":val_color or C_TEXT}),
        ],
    )

def build_detail(pid, df):
    snap = latest_snap(df)
    row  = snap[snap["numParticipante"] == int(pid)]
    if row.empty:
        return html.Div()
    r        = row.iloc[0]
    pid_list = sorted(df["numParticipante"].unique().tolist())
    color    = rcolor(pid_list, pid)
    bat      = float(r["bateriaBicicleta"])
    bat_c    = C_LIME if bat > 50 else (C_SUN if bat > 20 else C_RED)
    name     = rider_name(df, pid)

    return html.Div([
        html.Div(style={"display":"flex","alignItems":"center","gap":"10px",
                        "marginBottom":"10px","paddingBottom":"10px",
                        "borderBottom":f"1px solid {C_BORDER}"},
            children=[
                html.Div(f"#{pid}", style={"fontFamily":"Space Grotesk,sans-serif",
                    "fontSize":"24px","fontWeight":"800","color":color,"lineHeight":"1"}),
                html.Div([
                    html.Div(name or f"Participante {pid}", style={
                        "fontFamily":"Space Grotesk,sans-serif","fontSize":"13px",
                        "fontWeight":"600","color":C_TEXT}),
                    html.Div(str(r["cargaDeObjetos"]), style={
                        "fontFamily":"IBM Plex Mono,monospace","fontSize":"10px",
                        "color":C_MUTED}),
                ], style={"flex":"1"}),
                html.Div([
                    html.Div("BATERÍA", style={"fontFamily":"IBM Plex Mono,monospace",
                        "fontSize":"8px","color":C_MUTED,"letterSpacing":"1px",
                        "marginBottom":"3px"}),
                    html.Div(style={"width":"80px","height":"8px","backgroundColor":C_BORDER,
                                    "borderRadius":"4px","overflow":"hidden"},
                        children=[html.Div(style={"width":f"{min(bat,100)}%","height":"100%",
                            "backgroundColor":bat_c,"borderRadius":"4px"})]),
                    html.Div(f"{bat:.1f}%", style={"fontFamily":"IBM Plex Mono,monospace",
                        "fontSize":"12px","fontWeight":"700","color":bat_c,"marginTop":"2px"}),
                ]),
            ],
        ),
        html.Div(style={"display":"grid","gridTemplateColumns":"1fr 1fr 1fr","gap":"5px"},
            children=[
                _stat("🕒","Tiempo",   str(r["tiempo"])),
                _stat("⚡","Consumo",  f"{r['consumo']} kWh"),
                _stat("🌿","CO₂",      f"{r['emisiones']} kg"),
                _stat("📍","Lat",      f"{r['latitud']:.5f}"),
                _stat("📍","Lon",      f"{r['longitud']:.5f}"),
                _stat("📦","Carga",    str(r["cargaDeObjetos"]), C_GREEN),
            ],
        ),
    ], style={"padding":"12px 14px","backgroundColor":C_WHITE})

# ──────────────────────────────────────────────
#  Layout
# ──────────────────────────────────────────────
GF  = "https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;800&family=IBM+Plex+Mono:wght@400;600&display=swap"
CSS = """
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(1.5)}}
*{box-sizing:border-box;margin:0;padding:0}
body{background:#F0F7F0;overflow:hidden}
::-webkit-scrollbar{width:5px}
::-webkit-scrollbar-track{background:#F0F7F0}
::-webkit-scrollbar-thumb{background:#C5DFC5;border-radius:3px}
.dash-table-container .row{margin:0!important}
"""

def _hstat(label, value, eid=None):
    val_style = {"fontFamily":"IBM Plex Mono,monospace","fontSize":"18px",
                 "fontWeight":"600","color":"#FFFFFF"}
    val = html.Div(value, id=eid, style=val_style) if eid else html.Div(value, style=val_style)
    return html.Div(style={"textAlign":"center"}, children=[
        html.Div(label, style={"fontFamily":"IBM Plex Mono,monospace","fontSize":"8px",
                               "color":C_MUTED,"letterSpacing":"2px","marginBottom":"2px"}),
        val,
    ])

def create_layout():
    return html.Div(
        style={"backgroundColor":C_BG,"height":"100vh","display":"flex",
               "flexDirection":"column","overflow":"hidden",
               "fontFamily":"Space Grotesk, sans-serif","color":C_TEXT},
        children=[
            html.Link(rel="stylesheet", href=GF),

            # HEADER
            html.Div(
                style={"backgroundColor":C_HEADER,"height":"60px","flexShrink":"0",
                       "display":"flex","alignItems":"center","padding":"0 24px",
                       "justifyContent":"space-between","borderBottom":f"3px solid {C_LIME}"},
                children=[
                    html.Div(style={"display":"flex","alignItems":"center","gap":"10px"}, children=[
                        html.Span("⚡", style={"fontSize":"20px"}),
                        html.Div([
                            html.Div("RETO ALLEYCAT", style={"fontWeight":"800","fontSize":"16px",
                                "color":"#FFFFFF","letterSpacing":"3px"}),
                            html.Div("BICICLETAS ELÉCTRICAS · EN VIVO", style={
                                "fontFamily":"IBM Plex Mono,monospace","fontSize":"9px",
                                "color":C_LIME,"letterSpacing":"2px","marginTop":"1px"}),
                        ]),
                    ]),
                    html.Div(style={"display":"flex","gap":"32px"}, children=[
                        _hstat("PARTICIPANTES","15"),
                        _hstat("EMISIONES TOTAL","—","h-emisiones"),
                        _hstat("CONSUMO TOTAL",  "—","h-consumo"),
                    ]),
                    html.Div(id="clock", style={"fontFamily":"IBM Plex Mono,monospace",
                        "fontSize":"22px","fontWeight":"600","color":C_LIME,"letterSpacing":"2px"}),
                ],
            ),

            # BODY
            html.Div(style={"flex":"1","display":"flex","overflow":"hidden","height":"0"},
                children=[

                    # Mapa
                    html.Div(style={"flex":"1","position":"relative","overflow":"hidden"},
                        children=[
                            html.Iframe(id="map-iframe", srcDoc="<p>Cargando mapa...</p>",
                                style={"width":"100%","height":"100%","border":"none","display":"block"}),
                            html.Div(
                                style={"position":"absolute","top":"10px","left":"10px","zIndex":"999",
                                       "backgroundColor":"rgba(255,255,255,0.95)",
                                       "border":f"1px solid {C_BORDER}","borderRadius":"20px",
                                       "padding":"5px 14px","display":"flex","alignItems":"center",
                                       "gap":"7px","boxShadow":"0 2px 8px rgba(0,0,0,0.12)"},
                                children=[
                                    html.Div(style={"width":"7px","height":"7px","borderRadius":"50%",
                                                    "backgroundColor":C_LIME,
                                                    "animation":"pulse 1.5s infinite"}),
                                    html.Span("EN VIVO", style={"fontFamily":"IBM Plex Mono,monospace",
                                        "fontSize":"10px","fontWeight":"600",
                                        "color":C_GREEN,"letterSpacing":"2px"}),
                                ],
                            ),
                        ],
                    ),

                    # Sidebar
                    html.Div(
                        style={"width":"370px","flexShrink":"0","backgroundColor":C_WHITE,
                               "borderLeft":f"1px solid {C_BORDER}","display":"flex",
                               "flexDirection":"column","overflow":"hidden"},
                        children=[
                            html.Div(
                                style={"padding":"10px 14px","flexShrink":"0","backgroundColor":C_BG,
                                       "borderBottom":f"1px solid {C_BORDER}","display":"flex",
                                       "alignItems":"center","justifyContent":"space-between"},
                                children=[
                                    html.Span("CLASIFICACIÓN", style={"fontFamily":"IBM Plex Mono,monospace",
                                        "fontSize":"10px","fontWeight":"600","color":C_GREEN,"letterSpacing":"2px"}),
                                    html.Div(style={"display":"flex","gap":"8px","alignItems":"center"}, children=[
                                        html.Span(id="last-update", style={"fontFamily":"IBM Plex Mono,monospace",
                                            "fontSize":"9px","color":C_MUTED}),
                                        html.Button("TODOS", id="btn-reset", n_clicks=0, style={
                                            "backgroundColor":"transparent","border":f"1px solid {C_GREEN}",
                                            "color":C_GREEN,"cursor":"pointer",
                                            "fontFamily":"IBM Plex Mono,monospace","fontSize":"8px",
                                            "letterSpacing":"1px","padding":"3px 8px","borderRadius":"4px"}),
                                    ]),
                                ],
                            ),
                            html.Div(style={"flex":"1","overflow":"auto"}, children=[
                                dash_table.DataTable(
                                    id="riders-table",
                                    columns=TABLE_COLS,
                                    data=[],
                                    sort_action="native",
                                    row_selectable="single",
                                    selected_rows=[],
                                    style_table={"backgroundColor":"transparent","border":"none","minWidth":"100%"},
                                    style_header={"backgroundColor":C_BG,"color":C_GREEN,
                                        "fontFamily":"IBM Plex Mono,monospace","fontWeight":"600",
                                        "fontSize":"9px","letterSpacing":"1px",
                                        "border":f"1px solid {C_BORDER}","textAlign":"center","padding":"8px 4px"},
                                    style_cell={"backgroundColor":C_WHITE,"color":C_TEXT,
                                        "fontFamily":"IBM Plex Mono,monospace","fontSize":"10px",
                                        "border":f"1px solid {C_BORDER}","padding":"6px 4px",
                                        "textAlign":"center","maxWidth":"65px",
                                        "overflow":"hidden","textOverflow":"ellipsis"},
                                    style_data_conditional=[
                                        {"if":{"state":"selected"},
                                         "backgroundColor":"#EBF5EE","border":f"1px solid {C_GREEN}"},
                                        {"if":{"row_index":"odd"},"backgroundColor":C_BG},
                                        {"if":{"filter_query":"{bateriaBicicleta} < 20",
                                               "column_id":"bateriaBicicleta"},
                                         "color":C_RED,"fontWeight":"bold"},
                                        {"if":{"filter_query":"{bateriaBicicleta} >= 20 && {bateriaBicicleta} < 50",
                                               "column_id":"bateriaBicicleta"},
                                         "color":C_SUN,"fontWeight":"bold"},
                                    ],
                                ),
                            ]),
                            html.Div(id="detail-card",
                                style={"borderTop":f"2px solid {C_BORDER}","flexShrink":"0"},
                                children=[html.Div("← Selecciona un participante en la tabla",
                                    style={"fontFamily":"IBM Plex Mono,monospace","fontSize":"10px",
                                           "color":C_MUTED,"padding":"14px","fontStyle":"italic",
                                           "textAlign":"center"})],
                            ),
                        ],
                    ),
                ],
            ),

            # Solo guarda el pid seleccionado — NO hay store de datos
            dcc.Store(id="store-pid", data=None),
            dcc.Interval(id="iv-data",  interval=10_000, n_intervals=0),
            dcc.Interval(id="iv-clock", interval=1_000,  n_intervals=0),
        ],
    )

# ──────────────────────────────────────────────
#  App + Callbacks
# ──────────────────────────────────────────────
def build_app(intervalo):
    app = dash.Dash(__name__, title="Reto Alleycat ⚡", suppress_callback_exceptions=True)
    app.index_string = f"""<!DOCTYPE html>
<html><head>{{%metas%}}<title>{{%title%}}</title>{{%favicon%}}{{%css%}}
<style>{CSS}</style></head>
<body>{{%app_entry%}}<footer>{{%config%}}{{%scripts%}}{{%renderer%}}</footer></body></html>"""
    app.layout = create_layout()
    app.layout["iv-data"].interval = intervalo * 1000

    # Reloj
    @app.callback(Output("clock","children"), Input("iv-clock","n_intervals"))
    def tick(_):
        return datetime.now().strftime("%H:%M:%S")

    # Tabla + stats header — lee CSV directamente
    @app.callback(
        Output("riders-table","data"),
        Output("last-update","children"),
        Output("h-emisiones","children"),
        Output("h-consumo","children"),
        Input("iv-data","n_intervals"),
    )
    def refresh_table(_):
        if not os.path.exists(CSV_PATH):
            return [], "CSV no encontrado", "—", "—"
        try:
            df   = load_df()
            snap = latest_snap(df)
            ts   = datetime.now().strftime("%H:%M:%S")
            em   = f"{snap['emisiones'].sum():.3f} kg"
            con  = f"{snap['consumo'].sum():.2f} kWh"
            return snap_records(snap), f"Act: {ts}", em, con
        except Exception as e:
            return [], f"Error: {e}", "—", "—"

    # Selección de participante
    @app.callback(
        Output("store-pid","data"),
        Input("riders-table","selected_rows"),
        Input("riders-table","data"),
        Input("btn-reset","n_clicks"),
        State("store-pid","data"),
        prevent_initial_call=True,
    )
    def pick(sel_rows, tdata, btn, cur):
        from dash import callback_context as ctx
        if not ctx.triggered:
            return no_update
        tid = ctx.triggered[0]["prop_id"]
        if "btn-reset" in tid:
            return None
        if sel_rows and tdata and sel_rows[0] < len(tdata):
            return int(tdata[sel_rows[0]]["numParticipante"])
        return no_update

    # Mapa — lee CSV directamente, devuelve HTML puro
    @app.callback(
        Output("map-iframe","srcDoc"),
        Input("iv-data","n_intervals"),
        Input("store-pid","data"),
    )
    def update_map(_, pid):
        if not os.path.exists(CSV_PATH):
            return "<html><body style='padding:20px;font-family:sans-serif'>CSV no encontrado</body></html>"
        try:
            df = load_df()
            return build_map(df, int(pid) if pid is not None else None)
        except Exception as e:
            return f"<html><body style='padding:20px;font-family:monospace;color:red'><b>Error:</b> {e}</body></html>"

    # Detalle del rider
    @app.callback(
        Output("detail-card","children"),
        Output("riders-table","selected_rows"),
        Input("store-pid","data"),
        Input("iv-data","n_intervals"),
        State("riders-table","data"),
    )
    def update_detail(pid, _, tdata):
        if pid is None:
            return (html.Div("← Selecciona un participante en la tabla",
                style={"fontFamily":"IBM Plex Mono,monospace","fontSize":"10px",
                       "color":C_MUTED,"padding":"14px","fontStyle":"italic","textAlign":"center"}),
                [])
        try:
            df   = load_df()
            card = build_detail(int(pid), df)
            sel  = []
            if tdata:
                for i, r in enumerate(tdata):
                    if int(r.get("numParticipante",-1)) == int(pid):
                        sel = [i]; break
            return card, sel
        except Exception as e:
            return html.Div(str(e), style={"color":C_RED,"padding":"10px"}), []

    return app

# ──────────────────────────────────────────────
def main():
    global CSV_PATH
    p = argparse.ArgumentParser()
    p.add_argument("--csv",       required=True)
    p.add_argument("--intervalo", type=int, default=10)
    p.add_argument("--port",      type=int, default=8050)
    p.add_argument("--debug",     action="store_true")
    a = p.parse_args()
    if not os.path.exists(a.csv):
        print(f"[ERROR] No se encontró: {a.csv}"); return
    CSV_PATH = a.csv
    print(f"\n  ⚡  Reto Alleycat – Visualizador de Carrera")
    print(f"  📂  CSV: {a.csv}  |  🔄 {a.intervalo}s  |  🌐 http://localhost:{a.port}\n")
    app = build_app(a.intervalo)
    app.run(debug=a.debug, port=a.port, host="0.0.0.0")

if __name__ == "__main__":
    main()
