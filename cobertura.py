from datetime import datetime

import pandas as pd

from trazabilidad import VERSION_EXTRACTOR


COLUMNAS_COBERTURA = [
    "Fecha",
    "Estado",
    "Version_extractor",
    "Fecha_ultima_consulta",
    "Numero_publicaciones",
]
ESTADOS_VALIDOS = {"consultado", "sin_edicion"}
ESTADOS_COBERTURA = ESTADOS_VALIDOS | {"error"}


def registrar_cobertura(
    df_cobertura,
    fecha,
    estado,
    numero_publicaciones=None,
    momento=None,
    version_actual=VERSION_EXTRACTOR,
):
    """Registra un intento diario sin destruir una cobertura válida anterior."""
    if estado not in ESTADOS_COBERTURA:
        raise ValueError(f"Estado de cobertura no válido: {estado}")

    cobertura = normalizar_cobertura(df_cobertura)
    fecha_normalizada = _normalizar_fecha(fecha)
    fecha_consulta = _formatear_momento(momento)
    indices = cobertura.index[cobertura["Fecha"] == fecha_normalizada].tolist()

    if indices:
        indice = indices[-1]
        estado_anterior = cobertura.at[indice, "Estado"]
        if estado == "error" and estado_anterior in ESTADOS_VALIDOS:
            cobertura.at[indice, "Fecha_ultima_consulta"] = fecha_consulta
            return cobertura[COLUMNAS_COBERTURA]
    else:
        indice = len(cobertura)
        cobertura.loc[indice, "Fecha"] = fecha_normalizada

    cobertura.at[indice, "Estado"] = estado
    cobertura.at[indice, "Fecha_ultima_consulta"] = fecha_consulta
    if estado in ESTADOS_VALIDOS:
        cobertura.at[indice, "Version_extractor"] = version_actual
        cobertura.at[indice, "Numero_publicaciones"] = int(
            numero_publicaciones or 0
        )
    else:
        cobertura.at[indice, "Version_extractor"] = pd.NA
        cobertura.at[indice, "Numero_publicaciones"] = pd.NA
    return cobertura[COLUMNAS_COBERTURA]


def normalizar_cobertura(df_cobertura):
    """Normaliza el esquema y deja una única fila por fecha sobre una copia."""
    if df_cobertura is None:
        return pd.DataFrame(columns=COLUMNAS_COBERTURA)
    origen = df_cobertura.copy(deep=True)
    for columna in COLUMNAS_COBERTURA:
        if columna not in origen.columns:
            origen[columna] = pd.Series(pd.NA, index=origen.index, dtype="object")

    resultado = pd.DataFrame(columns=COLUMNAS_COBERTURA)
    for fila in origen[COLUMNAS_COBERTURA].to_dict(orient="records"):
        try:
            fecha = _normalizar_fecha(fila["Fecha"])
        except (TypeError, ValueError):
            continue
        coincidencias = resultado.index[resultado["Fecha"] == fecha].tolist()
        if coincidencias:
            indice = coincidencias[-1]
            if (
                fila["Estado"] == "error"
                and resultado.at[indice, "Estado"] in ESTADOS_VALIDOS
            ):
                resultado.at[indice, "Fecha_ultima_consulta"] = fila[
                    "Fecha_ultima_consulta"
                ]
                continue
            resultado = resultado.drop(index=coincidencias).reset_index(drop=True)
        fila["Fecha"] = fecha
        resultado = pd.concat([resultado, pd.DataFrame([fila])], ignore_index=True)
    return resultado[COLUMNAS_COBERTURA]


def _normalizar_fecha(fecha):
    if isinstance(fecha, datetime):
        return fecha.strftime("%Y-%m-%d")
    if not isinstance(fecha, str) or not fecha.strip():
        raise ValueError("La fecha de cobertura no es válida")
    texto = fecha.strip().replace("/", "-")
    try:
        return datetime.strptime(texto, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError as error:
        raise ValueError("La fecha de cobertura no es válida") from error


def _formatear_momento(momento):
    if momento is None:
        momento = datetime.now()
    if isinstance(momento, datetime):
        return momento.strftime("%Y-%m-%d %H:%M:%S")
    return str(momento)
