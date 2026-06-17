import threading
import time
from io import StringIO
from urllib.request import Request, urlopen

import pandas as pd


URL_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRiFEjEX7cGEjyR857KLj3nli2q6T0S0BeBXFAXIqsOJxfOfonj8-Ue32620vI2_OTwkAda-i7oKONL/pub?gid=0&single=true&output=csv"

ultimo_estado = None
puntajes_retos_cache: dict[str, float] = {}
totales_retos_cache: dict[str, float] = {}
puntajes_retos_lock = threading.Lock()
ultima_actualizacion = 0.0


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


def get_column_name(df: pd.DataFrame, expected_name: str) -> str:
    normalized_expected = expected_name.strip().lower()
    for column in df.columns:
        if str(column).strip().lower() == normalized_expected:
            return column
    raise KeyError(f"No existe la columna '{expected_name}' en la hoja")


def obtener_puntajes_por_participante(df: pd.DataFrame) -> dict[str, dict[str, float]]:
    equipo_col = get_column_name(df, "Equipo")
    puntaje_col = get_column_name(df, "Puntaje")
    total_col = get_column_name(df, "Total")

    datos = df[[equipo_col, puntaje_col, total_col]].copy()
    datos = datos.rename(columns={
        equipo_col: "Equipo",
        puntaje_col: "Puntaje",
        total_col: "Total",
    })
    datos["participante"] = datos["Equipo"].apply(normalizar_participante)
    datos["Puntaje"] = pd.to_numeric(datos["Puntaje"], errors="coerce")
    datos["Total"] = pd.to_numeric(datos["Total"], errors="coerce")
    datos = datos.dropna(subset=["participante", "Puntaje", "Total"])

    return {
        row["participante"]: {
            "puntaje": float(row["Puntaje"]),
            "total": float(row["Total"]),
        }
        for _, row in datos.iterrows()
    }


def leer_hoja_puntajes() -> pd.DataFrame:
    separador = "&" if "?" in URL_CSV else "?"
    url_sin_cache = f"{URL_CSV}{separador}_ts={time.time_ns()}"
    request = Request(
        url_sin_cache,
        headers={
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "User-Agent": "carrera-simulador/1.0",
        },
    )

    with urlopen(request, timeout=10) as response:
        csv_text = response.read().decode("utf-8-sig")

    return pd.read_csv(StringIO(csv_text))


def set_puntajes_retos_cache(puntajes_por_participante: dict[str, dict[str, float]]) -> dict[str, float]:
    global ultima_actualizacion

    now = time.time()
    with puntajes_retos_lock:
        for participante, valores in puntajes_por_participante.items():
            puntaje_nuevo = float(valores["puntaje"])
            total_nuevo = float(valores["total"])
            puntaje_actual = puntajes_retos_cache.get(participante)
            total_actual = totales_retos_cache.get(participante)

            if puntaje_actual is None or total_actual is None:
                puntajes_retos_cache[participante] = puntaje_nuevo
                totales_retos_cache[participante] = total_nuevo
                continue

            if total_nuevo < total_actual:
                continue

            if total_nuevo == total_actual:
                continue

            puntajes_retos_cache[participante] = puntaje_nuevo
            totales_retos_cache[participante] = total_nuevo

        ultima_actualizacion = now
        return dict(puntajes_retos_cache)


def refrescar_puntajes_retos() -> dict[str, float]:
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
        "puntaje_retos_origen": "google_sheet_total_monotonic_v5",
        "puntaje_retos_lectura_ts": lectura_ts,
    }


def sincronizar_puntajes(intervalo_segundos: float = 1.0) -> None:
    global ultimo_estado

    while True:
        try:
            puntajes_por_participante = refrescar_puntajes_retos()
            estado_actual = tuple(sorted(puntajes_por_participante.items()))

            if estado_actual != ultimo_estado:
                print("Puntajes de retos actualizados en memoria:")
                print(pd.DataFrame(
                    [
                        {
                            "participante": participante,
                            "puntaje_retos": valores["puntaje"],
                            "total": valores["total"],
                        }
                        for participante, valores in puntajes_por_participante.items()
                    ]
                ))

                ultimo_estado = estado_actual

            time.sleep(intervalo_segundos)

        except Exception as e:
            print("Error leyendo la hoja de puntajes:", e)
            time.sleep(intervalo_segundos)


if __name__ == "__main__":
    sincronizar_puntajes()
