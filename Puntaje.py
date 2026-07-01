import threading
import time
from io import BytesIO
from urllib.request import Request, urlopen

import pandas as pd


URL_CSV = "https://tecmx-my.sharepoint.com/:x:/g/personal/a00573396_tec_mx/IQCr9sj8DS4NQ6Vd5oTOoCjxAaaXAOP2xLiWAHV8Popp_JM?e=rpwVLK"
NOMBRE_HOJA = "Stream_Final"
PRIMERA_FILA_PUNTAJES = 19
CANTIDAD_PARTICIPANTES = 15
PUNTAJE_MAXIMO = 100.0

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


def obtener_puntajes_por_participante(df: pd.DataFrame) -> dict[str, dict[str, float]]:
    return {
        f"participante_{numero:02d}": {
            "puntaje": float(puntaje),
            "total": PUNTAJE_MAXIMO,
        }
        for numero, puntaje in enumerate(
            pd.to_numeric(df.iloc[:, 0], errors="coerce"), start=1
        )
        if pd.notna(puntaje)
    }


def leer_hoja_puntajes() -> pd.DataFrame:
    separador = "&" if "?" in URL_CSV else "?"
    url_sin_cache = f"{URL_CSV}{separador}download=1&_ts={time.time_ns()}"
    request = Request(
        url_sin_cache,
        headers={
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "User-Agent": "carrera-simulador/1.0",
        },
    )

    with urlopen(request, timeout=15) as response:
        excel_bytes = response.read()

    return pd.read_excel(
        BytesIO(excel_bytes),
        sheet_name=NOMBRE_HOJA,
        usecols="E",
        skiprows=PRIMERA_FILA_PUNTAJES - 1,
        nrows=CANTIDAD_PARTICIPANTES,
        header=None,
    )


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
            puntaje_actual = puntajes_retos_cache.get(participante)

            if puntaje_actual is not None and puntaje_nuevo < puntaje_actual:
                continue

            puntajes_retos_cache[participante] = puntaje_nuevo
            totales_retos_cache[participante] = PUNTAJE_MAXIMO

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
                print("Puntajes de retos actualizados en memoria:")
                print(pd.DataFrame(
                    [
                        {
                            "participante": participante,
                            "puntaje_retos": valores
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
