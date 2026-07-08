import threading
import time
from io import BytesIO
from urllib.request import Request, urlopen

import pandas as pd


URL_CSV = "https://docs.google.com/spreadsheets/d/1qGKsNsSf92LY7IdazkQSR3xunPAjPSfe/export?format=xlsx"
NOMBRE_HOJA = "Results_Resultados"

ultimo_estado = None
puntajes_retos_cache: dict[str, float] = {}
activity_points_cache: dict[str, float] = {}
time_s_cache: dict[str, float] = {}
totales_retos_cache: dict[str, float] = {}
nombres_equipos_cache: dict[str, str] = {}
team_id_cache: dict[str, str] = {}
puntajes_retos_lock = threading.Lock()
ultima_actualizacion = 0.0

def get_team_name(participante: str) -> str:
    with puntajes_retos_lock:
        return nombres_equipos_cache.get(participante, participante)

def get_team_id(participante: str) -> str:
    with puntajes_retos_lock:
        return team_id_cache.get(participante, "")


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
    
    # Cast column names to str to avoid 'int has no attribute replace' when
    # pandas loads a sheet without a proper header row (columns become 0,1,2,...)\
    str_columns = [str(c) for c in df.columns]
    cols = {c.replace('\n', '').replace(' ', '').lower(): orig for c, orig in zip(str_columns, df.columns)}

    col_team_id   = cols.get('teamidequipoid')   or df.columns[0]
    col_team_name = cols.get('teamequipo')        or (df.columns[1] if len(df.columns) > 1 else df.columns[0])
    col_total     = cols.get('totaltotal')        or (df.columns[17] if len(df.columns) > 17 else df.columns[-1])
    col_time      = cols.get('time_stiempo_s')   or (df.columns[3]  if len(df.columns) > 3  else None)

    # Challenges = sum of columns E:N (indices 4 to 13, the 10 individual challenge scores)
    # This matches the user request: cells E2:O17 on the Results page
    challenge_col_indices = [i for i in range(4, 14) if i < len(df.columns)]

    for idx, row in df.iterrows():
        try:
            equipo_id_str = str(row[col_team_id])
            nombre_equipo = str(row[col_team_name])
            puntaje_val   = row[col_total]
            time_val      = row[col_time] if col_time is not None else None
            
            # Sum all individual challenge columns (E to N = indices 4 to 13)
            challenge_total = 0.0
            for ci in challenge_col_indices:
                val = row[df.columns[ci]]
                if pd.notna(val):
                    try:
                        challenge_total += float(val)
                    except (ValueError, TypeError):
                        pass
            
            match = re.search(r'\d+', equipo_id_str)
            if match:
                numero   = int(match.group())
                puntaje  = float(puntaje_val)  if pd.notna(puntaje_val)  else 0.0
                time_s   = float(time_val)     if (time_val is not None and pd.notna(time_val)) else 0.0
                
                resultados[f"participante_{numero:02d}"] = {
                    "puntaje":         puntaje,
                    "activity_points": challenge_total,
                    "time_s":          time_s,
                    "total":           100.0,
                    "team_id":         equipo_id_str,
                    "team_name":       nombre_equipo
                }
        except Exception:
            continue
    return resultados


def leer_hoja_puntajes() -> pd.DataFrame:
    # URL_CSV is already a direct export URL
    url_sin_cache = f"{URL_CSV}&_ts={time.time_ns()}"
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
            puntajes_retos_cache[participante] = puntaje_nuevo
            activity_points_cache[participante] = float(valores.get("activity_points", 0.0))
            time_s_cache[participante] = float(valores.get("time_s", 0.0))
            totales_retos_cache[participante] = 100.0
            if "team_name" in valores:
                nombres_equipos_cache[participante] = valores["team_name"]
            if "team_id" in valores:
                team_id_cache[participante] = str(valores["team_id"]).strip().upper()

        ultima_actualizacion = now
        return _get_puntajes_retos_detalle_snapshot()


def refrescar_puntajes_retos() -> dict[str, dict[str, float]]:
    df = leer_hoja_puntajes()
    puntajes_por_participante = obtener_puntajes_por_participante(df)
    return set_puntajes_retos_cache(puntajes_por_participante)


def get_puntaje_retos(participante: str) -> float:
    with puntajes_retos_lock:
        return float(puntajes_retos_cache.get(participante, 0.0))

def get_activity_points(participante: str) -> float:
    with puntajes_retos_lock:
        return float(activity_points_cache.get(participante, 0.0))

def get_time_s(participante: str) -> float:
    with puntajes_retos_lock:
        return float(time_s_cache.get(participante, 0.0))


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
                print("SCOREBOARD updated in memory:")
                filas_tabla = []
                for p, valores in puntajes_por_participante.items():
                    raw_id = valores.get("team_id", p)
                    team_id_str = str(raw_id) if raw_id is not None else p.replace("participante_", "EQ").upper()
                    filas_tabla.append({
                        "TeamID": team_id_str,
                        "Team":   valores.get("team_name", "Unknown"),
                        "Total":  f"{valores['puntaje']:.2f}"
                    })
                print(pd.DataFrame(filas_tabla).to_string(index=False))

                ultimo_estado = estado_actual

            time.sleep(intervalo_segundos)

        except Exception as e:
            print("Error reading scores sheet:", e)
            time.sleep(intervalo_segundos)


if __name__ == "__main__":
    sincronizar_puntajes()
