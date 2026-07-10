import threading
import time
from io import BytesIO
from urllib.request import Request, urlopen

import pandas as pd


URL_CSV = "https://docs.google.com/spreadsheets/d/12XWCYO1ZQnaXqPCrHneu70BThHSja_hduYWnIFZxQYw/export?format=xlsx"
NOMBRE_HOJA = "Stream"

ultimo_estado = None
puntajes_retos_cache: dict[str, float] = {}
activity_points_cache: dict[str, float] = {}
time_s_cache: dict[str, float] = {}
load_percent_cache: dict[str, float] = {}
energy_percent_cache: dict[str, float] = {}
time_percent_cache: dict[str, float] = {}
challenges_percent_cache: dict[str, float] = {}
totales_retos_cache: dict[str, float] = {}
scoreboard_rank_cache: dict[str, int] = {}
nombres_equipos_cache: dict[str, str] = {}
team_id_cache: dict[str, str] = {}
team_name_to_participant_id: dict[str, str] = {}
participant_id_to_team_name: dict[str, str] = {}
puntajes_retos_lock = threading.Lock()
ultima_actualizacion = 0.0

def resolve_participant_by_name(team_name: str) -> str | None:
    if not team_name:
        return None
    name_cleaned = str(team_name).strip().lower()
    
    with puntajes_retos_lock:
        if name_cleaned in team_name_to_participant_id:
            return team_name_to_participant_id[name_cleaned]
        if name_cleaned.replace(" ", "") in team_name_to_participant_id:
            return team_name_to_participant_id[name_cleaned.replace(" ", "")]
            
    import re
    match = re.search(r"\d+", name_cleaned)
    if match:
        num = int(match.group())
        return f"participante_{num:02d}"
        
    return None

def build_team_name_mappings(df_teams: pd.DataFrame):
    global team_name_to_participant_id, participant_id_to_team_name
    if df_teams is None or df_teams.empty:
        return
        
    header_idx = None
    for idx, row in df_teams.iterrows():
        row_vals = [str(x).strip().lower() for x in row.tolist() if pd.notna(x)]
        if any('teamid' in x or 'team id' in x or 'equipoid' in x for x in row_vals) and any('team' in x or 'equipo' in x for x in row_vals):
            header_idx = idx
            break
            
    if header_idx is None:
        header_idx = 10 if len(df_teams) > 10 else 0
        
    header_row = df_teams.iloc[header_idx].tolist()
    col_id = 0
    col_name = 1
    for col_i, val in enumerate(header_row):
        val_str = str(val).strip().lower()
        if 'teamid' in val_str or 'team id' in val_str or 'equipoid' in val_str:
            col_id = col_i
        elif 'team' in val_str or 'equipo' in val_str:
            col_name = col_i
            
    mappings = {}
    rev_mappings = {}
    import re
    for idx in range(header_idx + 1, len(df_teams)):
        row = df_teams.iloc[idx]
        id_val = row[col_id]
        name_val = row[col_name]
        if pd.isna(id_val) or pd.isna(name_val):
            continue
            
        match = re.search(r'\d+', str(id_val))
        if not match:
            continue
            
        num = int(match.group())
        part_key = f"participante_{num:02d}"
        
        norm_name = str(name_val).strip().lower()
        mappings[norm_name] = part_key
        mappings[norm_name.replace(" ", "")] = part_key
        
        rev_mappings[part_key] = str(name_val).strip()
        
    with puntajes_retos_lock:
        team_name_to_participant_id.update(mappings)
        participant_id_to_team_name.update(rev_mappings)

loads_cache: dict[str, dict] = {}
loads_lock = threading.Lock()

def get_loads_data() -> dict[str, dict]:
    with loads_lock:
        return dict(loads_cache)

energy_cache: dict[str, dict] = {}
energy_lock = threading.Lock()

def get_energy_data() -> dict[str, dict]:
    with energy_lock:
        return dict(energy_cache)

def get_team_name(participante: str) -> str:
    with puntajes_retos_lock:
        name = nombres_equipos_cache.get(participante, participante)
    try:
        import re
        match = re.search(r"\d+", participante)
        if match:
            num = int(match.group())
            if name.lower().startswith("participante_"):
                return f"Team {num}"
            if name.lower().replace(" ", "").startswith(f"team{num}"):
                return name
            return f"Team {num} - {name}"
    except Exception:
        pass
    return name

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
    cols = {normalizar_columna(c): orig for c, orig in zip(str_columns, df.columns)}

    def buscar_columna(*opciones: str, default=None):
        for opcion in opciones:
            clave = normalizar_columna(opcion)
            if clave in cols:
                return cols[clave]
        return default

    def buscar_columna_por_tokens(*tokens: str, default=None):
        tokens_norm = [normalizar_columna(token) for token in tokens]
        for clave, orig in cols.items():
            if all(token in clave for token in tokens_norm):
                return orig
        return default

    col_team_id = (
        buscar_columna('teamidequipoid', 'team id', 'equipo id')
        or buscar_columna_por_tokens('team', 'id')
        or buscar_columna_por_tokens('equipo', 'id')
        or df.columns[0]
    )
    col_team_name = (
        buscar_columna('teamequipo', 'team', 'equipo')
        or buscar_columna_por_tokens('team')
        or buscar_columna_por_tokens('equipo')
        or (df.columns[1] if len(df.columns) > 1 else df.columns[0])
    )
    col_total = (
        buscar_columna('totaltotal', 'total (-/100)', 'total')
        or buscar_columna_por_tokens('total')
        or (df.columns[17] if len(df.columns) > 17 else df.columns[-1])
    )
    col_time_s = (
        buscar_columna('time_stiempo_s', 'time_s', 'tiempo_s')
        or buscar_columna_por_tokens('time', 's')
        or buscar_columna_por_tokens('tiempo', 's')
        or (df.columns[3] if len(df.columns) > 3 else None)
    )
    col_load_percent = buscar_columna('load (%)', 'loading', 'load', 'carga (%)') or buscar_columna_por_tokens('load')
    col_energy_percent = buscar_columna('energy (%)', 'energy', 'energia', 'energía') or buscar_columna_por_tokens('energy') or buscar_columna_por_tokens('energia')
    col_time_percent = buscar_columna('time (%)', 'time', 'tiempo (%)') or buscar_columna_por_tokens('time')
    col_challenges_percent = buscar_columna('challenges (%)', 'challenges', 'retos (%)') or buscar_columna_por_tokens('challenge') or buscar_columna_por_tokens('reto')

    # Compatibility fallback for older sheets with individual challenge columns.
    challenge_col_indices = [i for i in range(4, 14) if i < len(df.columns)]

    for idx, row in df.iterrows():
        try:
            equipo_id_str = str(row[col_team_id])
            nombre_equipo = str(row[col_team_name])
            puntaje_val   = row[col_total]
            time_val      = row[col_time_s] if col_time_s is not None else None
            
            # Sum all individual challenge columns (E to N = indices 4 to 13)
            challenge_total = 0.0
            for ci in challenge_col_indices:
                val = row[df.columns[ci]]
                if pd.notna(val):
                    try:
                        challenge_total += float(val)
                    except (ValueError, TypeError):
                        pass
            
            part_key = resolve_participant_by_name(nombre_equipo)
            if not part_key:
                match = re.search(r'\d+', equipo_id_str)
                if match:
                    numero = int(match.group())
                    part_key = f"participante_{numero:02d}"
            
            if part_key:
                try:
                    rank_val = int(float(str(row[df.columns[0]]).strip().split()[0]))
                except Exception:
                    rank_val = 99
                    
                puntaje  = float(puntaje_val)  if pd.notna(puntaje_val)  else 0.0
                time_s   = float(time_val)     if (time_val is not None and pd.notna(time_val)) else 0.0
                
                resultados[part_key] = {
                    "puntaje":         puntaje,
                    "activity_points": challenge_total,
                    "time_s":          time_s,
                    "total":           100.0,
                    "team_id":         equipo_id_str,
                    "team_name":       nombre_equipo,
                    "scoreboard_rank": rank_val,
                    "load_percent": safe_float(row[col_load_percent]) if col_load_percent is not None else 0.0,
                    "energy_percent": safe_float(row[col_energy_percent]) if col_energy_percent is not None else 0.0,
                    "time_percent": safe_float(row[col_time_percent]) if col_time_percent is not None else 0.0,
                    "challenges_percent": safe_float(row[col_challenges_percent]) if col_challenges_percent is not None else challenge_total,
                }
        except Exception:
            continue
    return resultados


def normalizar_columna(valor) -> str:
    import unicodedata

    texto = str(valor or "").strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(char for char in texto if not unicodedata.combining(char))
    return "".join(char for char in texto if char.isalnum())


def safe_float(valor, default: float = 0.0) -> float:
    if pd.isna(valor):
        return default
    try:
        if isinstance(valor, str):
            valor = valor.strip().replace("%", "").replace(",", ".")
        return float(valor)
    except (TypeError, ValueError):
        return default


def normalizar_dataframe_puntajes(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    working = df.dropna(how="all").reset_index(drop=True)
    if working.empty:
        return working

    for idx, row in working.iterrows():
        values = [str(value).strip() for value in row.tolist() if pd.notna(value) and str(value).strip()]
        normalized = " ".join(normalizar_columna(value) for value in values)
        has_header_words = (
            ("team" in normalized or "equipo" in normalized)
            and ("total" in normalized or "challenge" in normalized or "reto" in normalized)
        )
        if len(values) >= 3 and has_header_words:
            normalized_df = working.iloc[idx + 1:].copy()
            normalized_df.columns = [str(value).strip() if pd.notna(value) and str(value).strip() else f"col_{i}" for i, value in enumerate(row.tolist())]
            return normalized_df.dropna(how="all").reset_index(drop=True)

    return working


def leer_hojas_excel() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
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

    with urlopen(request, timeout=15) as response:
        excel_bytes = response.read()

    xl = pd.ExcelFile(BytesIO(excel_bytes))
    
    df_stream = pd.DataFrame()
    if NOMBRE_HOJA in xl.sheet_names:
        df_stream = xl.parse(NOMBRE_HOJA, header=None)
        df_stream = normalizar_dataframe_puntajes(df_stream)
    else:
        print(f"Error: La hoja {NOMBRE_HOJA} no se encontró en el Excel.")

    df_loads = pd.DataFrame()
    if "Loads" in xl.sheet_names:
        df_loads = xl.parse("Loads", header=None)
    else:
        print("Warning: La hoja Loads no se encontró en el Excel.")

    df_energy = pd.DataFrame()
    if "Energy" in xl.sheet_names:
        df_energy = xl.parse("Energy", header=None)
    else:
        print("Warning: La hoja Energy no se encontró en el Excel.")

    df_teams = pd.DataFrame()
    if "Teams" in xl.sheet_names:
        df_teams = xl.parse("Teams", header=None)
    else:
        print("Warning: La hoja Teams no se encontró en el Excel.")

    return df_stream, df_loads, df_energy, df_teams


def obtener_loads_por_participante_local(df: pd.DataFrame) -> dict[str, dict]:
    import re
    resultados = {}
    if df.empty:
        return resultados
    
    header_idx = None
    for idx, row in df.iterrows():
        row_vals = [str(x).strip().lower() for x in row.tolist() if pd.notna(x)]
        if any('team' in x for x in row_vals) and any('load at home' in x or 'home' in x for x in row_vals):
            header_idx = idx
            break
            
    if header_idx is None:
        header_idx = 12 if len(df) > 12 else 0

    header_row = df.iloc[header_idx].tolist()
    
    col_team = 0
    col_load_home = 1
    col_curr_load = 2
    col_target = 3
    col_status = 4
    
    for col_i, val in enumerate(header_row):
        val_str = str(val).strip().lower()
        if 'team' in val_str:
            col_team = col_i
        elif 'home' in val_str:
            col_load_home = col_i
        elif 'current' in val_str:
            col_curr_load = col_i
        elif 'target' in val_str:
            col_target = col_i
        elif 'status' in val_str:
            col_status = col_i

    for idx in range(header_idx + 1, len(df)):
        row = df.iloc[idx]
        try:
            team_val = row[col_team]
            if pd.isna(team_val):
                continue
            
            part_key = resolve_participant_by_name(team_val)
            if not part_key:
                continue
            
            load_home = safe_float(row[col_load_home])
            curr_load = safe_float(row[col_curr_load])
            target = safe_float(row[col_target])
            status_val = str(row[col_status]).strip() if pd.notna(row[col_status]) else "unknown"
            
            resultados[part_key] = {
                "load_at_home": load_home,
                "current_load": curr_load,
                "target": target,
                "status": status_val
            }
        except Exception as e:
            print(f"Error parsing loads row {idx}: {e}")
            continue
            
    return resultados


def obtener_energy_por_participante_local(df: pd.DataFrame) -> dict[str, dict]:
    import re
    resultados = {}
    if df.empty:
        return resultados
        
    header_idx = None
    for idx, row in df.iterrows():
        row_vals = [str(x).strip().lower() for x in row.tolist() if pd.notna(x)]
        if any('teamid' in x or 'team id' in x for x in row_vals) and any('energy' in x for x in row_vals):
            header_idx = idx
            break
            
    if header_idx is None:
        header_idx = 9 if len(df) > 9 else 0
        
    header_row = df.iloc[header_idx].tolist()
    
    col_team = 0
    col_time = 2
    col_energy = 3
    
    for col_i, val in enumerate(header_row):
        val_str = str(val).strip().lower()
        if 'teamid' in val_str or 'team id' in val_str:
            col_team = col_i
        elif 'time' in val_str or 'tiempo' in val_str:
            col_time = col_i
        elif 'energy' in val_str or 'energia' in val_str or 'energía' in val_str:
            col_energy = col_i

    for idx in range(header_idx + 1, len(df)):
        row = df.iloc[idx]
        try:
            team_val = row[col_team]
            if pd.isna(team_val):
                continue
                
            energy_val = row[col_energy]
            if str(energy_val).strip().lower() == 'wh':
                continue
                
            part_key = resolve_participant_by_name(team_val)
            if not part_key:
                continue
            
            time_val = row[col_time]
            import datetime
            if pd.isna(time_val):
                time_str = "--"
            elif isinstance(time_val, (datetime.time, time)):
                time_str = time_val.strftime("%H:%M:%S")
            elif isinstance(time_val, datetime.datetime):
                time_str = time_val.time().strftime("%H:%M:%S")
            else:
                time_str = str(time_val).strip()
                
            energy_num = safe_float(energy_val)
            
            percent_val = row[5] if len(row) > 5 else None
            percent_num = safe_float(percent_val) * 100.0 if percent_val is not None else 0.0
            
            resultados[part_key] = {
                "energy_time": time_str,
                "energy_val": energy_num,
                "energy_percent": percent_num
            }
        except Exception as e:
            print(f"Error parsing energy row {idx}: {e}")
            continue
            
    return resultados


def leer_hoja_puntajes() -> pd.DataFrame:
    try:
        df_stream, _, _ = leer_hojas_excel()
        return df_stream
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
            load_percent_cache[participante] = float(valores.get("load_percent", 0.0))
            energy_percent_cache[participante] = float(valores.get("energy_percent", 0.0))
            time_percent_cache[participante] = float(valores.get("time_percent", 0.0))
            challenges_percent_cache[participante] = float(valores.get("challenges_percent", 0.0))
            totales_retos_cache[participante] = 100.0
            if "team_name" in valores:
                nombres_equipos_cache[participante] = valores["team_name"]
            if "team_id" in valores:
                team_id_cache[participante] = str(valores["team_id"]).strip().upper()
            if "scoreboard_rank" in valores:
                scoreboard_rank_cache[participante] = int(valores["scoreboard_rank"])

        ultima_actualizacion = now
        return _get_puntajes_retos_detalle_snapshot()


def refrescar_puntajes_retos() -> dict[str, dict[str, float]]:
    try:
        df_stream, df_loads, df_energy, df_teams = leer_hojas_excel()
        build_team_name_mappings(df_teams)
    except Exception as e:
        print("Error downloading/reading Excel workbook:", e)
        df_stream = leer_hoja_puntajes()
        df_loads = pd.DataFrame()
        df_energy = pd.DataFrame()
        df_teams = pd.DataFrame()

    if not df_stream.empty:
        puntajes_por_participante = obtener_puntajes_por_participante(df_stream)
        set_puntajes_retos_cache(puntajes_por_participante)

    if not df_loads.empty:
        parsed_loads = obtener_loads_por_participante_local(df_loads)
        with loads_lock:
            global loads_cache
            loads_cache = parsed_loads

    if not df_energy.empty:
        parsed_energy = obtener_energy_por_participante_local(df_energy)
        with energy_lock:
            global energy_cache
            energy_cache = parsed_energy

    return _get_puntajes_retos_detalle_snapshot()


def get_puntaje_retos(participante: str) -> float:
    with puntajes_retos_lock:
        return float(puntajes_retos_cache.get(participante, 0.0))

def get_scoreboard_rank(participante: str) -> int:
    with puntajes_retos_lock:
        return scoreboard_rank_cache.get(participante, 99)

def get_activity_points(participante: str) -> float:
    with puntajes_retos_lock:
        return float(activity_points_cache.get(participante, 0.0))

def get_time_s(participante: str) -> float:
    with puntajes_retos_lock:
        return float(time_s_cache.get(participante, 0.0))

def get_load_percent(participante: str) -> float:
    with puntajes_retos_lock:
        return float(load_percent_cache.get(participante, 0.0))

def get_energy_percent(participante: str) -> float:
    with puntajes_retos_lock:
        return float(energy_percent_cache.get(participante, 0.0))

def get_time_percent(participante: str) -> float:
    with puntajes_retos_lock:
        return float(time_percent_cache.get(participante, 0.0))

def get_challenges_percent(participante: str) -> float:
    with puntajes_retos_lock:
        return float(challenges_percent_cache.get(participante, 0.0))


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


def sincronizar_puntajes(intervalo_segundos: float = 15.0) -> None:
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
