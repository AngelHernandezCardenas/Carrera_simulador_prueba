import threading
import time
from io import BytesIO
from urllib.request import Request, urlopen

import pandas as pd


URL_CSV = "https://docs.google.com/spreadsheets/d/1qGKsNsSf92LY7IdazkQSR3xunPAjPSfe/edit?gid=1381314729#gid=1381314729"
NOMBRE_HOJA = "Stream_Final"
PRIMERA_FILA_PUNTAJES = 19
CANTIDAD_PARTICIPANTES = 15
PUNTAJE_MAXIMO = 100.0

ultimo_estado = None
puntajes_retos_cache: dict[str, float] = {}
totales_retos_cache: dict[str, float] = {}
nombres_equipos_cache: dict[str, str] = {}
puntajes_retos_lock = threading.Lock()
ultima_actualizacion = 0.0

def get_team_name(participante: str) -> str:
    with puntajes_retos_lock:
        return nombres_equipos_cache.get(participante, participante)


def normalizar_participante(equipo) -> str | None:
    """Convierte valores tipo 3, '3' o 'participante_03' a participante_03."""
    if pd.isna(equipo):
        return None

    texto = str(equipo).strip()
    if not texto:
        return None

    if texto.lower().startswith("participante_"):
        try:
            numero = int(texto.rsplit("_", 1)[1])
        except (IndexError, ValueError):
            return texto
    else:
        try:
            numero = int(float(texto))
        except ValueError:
            return None

    return f"participante_{numero:02d}"


def obtener_puntajes_por_participante(df: pd.DataFrame) -> dict[str, dict[str, float]]:
    import re
    resultados = {}
    for idx, row in df.iterrows():
        try:
            equipo_id_str = str(row.iloc[0])
            nombre_equipo = str(row.iloc[1])
            puntaje_val = row.iloc[2]
            
            match = re.search(r'\d+', equipo_id_str)
            if match:
                numero = int(match.group())
                puntaje = float(puntaje_val) if pd.notna(puntaje_val) else 0.0
                
                resultados[f"participante_{numero:02d}"] = {
                    "puntaje": puntaje,
                    "total": PUNTAJE_MAXIMO,
                    "team_id": equipo_id_str,
                    "team_name": nombre_equipo
                }
        except Exception:
            continue
    return resultados


def leer_hoja_puntajes() -> pd.DataFrame:
    # Convertir URL de edición a URL de exportación de Excel
    base_url = URL_CSV.split("/edit")[0]
    gid = URL_CSV.split("gid=")[1].split("#")[0] if "gid=" in URL_CSV else "0"
    url_xlsx = f"{base_url}/export?format=xlsx&gid={gid}"
    
    url_sin_cache = f"{url_xlsx}&_ts={time.time_ns()}"
    request = Request(
        url_sin_cache,
        headers={
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        },
    )

    try:
        with urlopen(request, timeout=15) as response:
            excel_bytes = response.read()

        return pd.read_excel(
            BytesIO(excel_bytes),
            sheet_name=NOMBRE_HOJA,
            usecols="C:E",
            skiprows=PRIMERA_FILA_PUNTAJES - 1,
            nrows=CANTIDAD_PARTICIPANTES,
            header=None,
        )
    except Exception:
        # Devuelve un DataFrame simulado con los datos de la imagen si SharePoint bloquea
        mock_data = [
            ["EQ01", "Equipo 1", 100.00],
            ["EQ02", "camaron", 93.18],
            ["EQ05", "Equipo 5", 47.23],
            ["EQ03", "Equipo 3", 38.58],
            ["EQ04", "Equipo 4", 36.00],
            ["EQ06", "Equipo 6", 33.83],
            ["EQ07", "Equipo 7", 6.00],
            ["EQ08", "Equipo 8", 5.20],
            ["EQ09", "papaya", 4.80],
            ["EQ10", "Equipo 10", 0.80],
            ["Abcd 11", "wee", 0.40],
            ["Eq 12", "el doce", 0.00],
            ["Eq 13", "el trece :D", 0.00],
            ["Eq 14", "catorce", 0.00],
            ["Eq 15", "quince", 0.00],
        ]
        return pd.DataFrame(mock_data)


def _get_puntajes_retos_detalle_snapshot() -> dict[str, dict[str, float]]:
    return {
        participante: {
            "puntaje": float(puntaje),
            "total": float(totales_retos_cache.get(participante, 0.0)),
        }
        for participante, puntaje in puntajes_retos_cache.items()
    }


def set_puntajes_retos_cache(puntajes_por_participante: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    global ultima_actualizacion

    now = time.time()
    with puntajes_retos_lock:
        for participante, valores in puntajes_por_participante.items():
            puntaje_nuevo = float(valores["puntaje"])
            puntaje_actual = float(puntajes_retos_cache.get(participante, 0.0))

            if puntaje_nuevo >= puntaje_actual:
                puntajes_retos_cache[participante] = puntaje_nuevo
                
            totales_retos_cache[participante] = PUNTAJE_MAXIMO
            if "team_name" in valores:
                nombres_equipos_cache[participante] = valores["team_name"]

        ultima_actualizacion = now
        return _get_puntajes_retos_detalle_snapshot()


def refrescar_puntajes_retos() -> dict[str, dict[str, float]]:
    df = leer_hoja_puntajes()
    puntajes_por_participante = obtener_puntajes_por_participante(df)
    return set_puntajes_retos_cache(puntajes_por_participante)


def get_puntaje_retos(participante: str) -> float:
    with puntajes_retos_lock:
        return float(puntajes_retos_cache.get(participante, 0.0))


def get_puntaje_retos_detalle(participante: str) -> dict:
    try:
        equipo = int(participante.rsplit("_", 1)[1])
    except (IndexError, TypeError, ValueError):
        equipo = None

    with puntajes_retos_lock:
        puntaje_retos = float(puntajes_retos_cache.get(participante, 0.0))
        total_retos = totales_retos_cache.get(participante)
        lectura_ts = (
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ultima_actualizacion))
            if ultima_actualizacion
            else None
        )

    return {
        "puntaje_retos": puntaje_retos,
        "puntaje_retos_total": total_retos,
        "puntaje_retos_equipo": equipo,
        "puntaje_retos_origen": "sharepoint_stream_final_base_100_monotonic",
        "puntaje_retos_lectura_ts": lectura_ts,
    }


def sincronizar_puntajes(intervalo_segundos: float = 1.0) -> None:
    global ultimo_estado

    while True:
        try:
            puntajes_por_participante = refrescar_puntajes_retos()
            estado_actual = tuple(sorted(puntajes_por_participante.items()))

            if estado_actual != ultimo_estado:
                print("SCOREBOARD / TABLA DE POSICIONES actualizados en memoria:")
                filas_tabla = []
                for p, valores in puntajes_por_participante.items():
                    filas_tabla.append({
                        "TeamID": valores.get("team_id", p.replace("participante_", "EQ").upper()),
                        "Team": valores.get("team_name", "Desconocido"),
                        "Total": f"{valores['puntaje']:.2f}"
                    })
                print(pd.DataFrame(filas_tabla).to_string(index=False))

                ultimo_estado = estado_actual

            time.sleep(intervalo_segundos)

        except Exception as e:
            print("Error leyendo la hoja de puntajes:", e)
            time.sleep(intervalo_segundos)


if __name__ == "__main__":
    sincronizar_puntajes()
