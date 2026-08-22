from datetime import datetime

import pandas as pd

from fechas import convertir_fecha
from trazabilidad import (
    PATRON_PUBLICACION_ID,
    VERSION_EXTRACTOR,
    comparar_versiones,
)


COLUMNAS_COBERTURA = [
    "Fecha",
    "Estado",
    "Version_extractor",
    "Fecha_ultima_consulta",
    "Numero_publicaciones",
]
COLUMNAS_TEXTO_COBERTURA = [
    "Fecha",
    "Estado",
    "Version_extractor",
    "Fecha_ultima_consulta",
]
ESTADOS_VALIDOS = {"consultado", "sin_edicion"}
ESTADOS_COBERTURA = ESTADOS_VALIDOS | {"error"}


def puede_reutilizar_cobertura(
    fecha,
    df_cobertura,
    df_publicaciones,
    df_oposiciones,
    version_actual=VERSION_EXTRACTOR,
):
    """Decide conservadoramente si un índice diario puede omitirse."""
    try:
        fecha_objetivo = _fecha_comparable(fecha)
    except (TypeError, ValueError):
        return False

    cobertura = normalizar_cobertura(df_cobertura)
    filas_cobertura = cobertura[
        cobertura["Fecha"].map(_fecha_comparable_segura) == fecha_objetivo
    ]
    if filas_cobertura.empty:
        return False
    fila_cobertura = filas_cobertura.iloc[-1]
    if fila_cobertura["Estado"] not in ESTADOS_VALIDOS:
        return False
    comparacion = comparar_versiones(
        fila_cobertura["Version_extractor"], version_actual
    )
    if comparacion is None or comparacion < 0:
        return False
    numero_publicaciones = _numero_publicaciones_valido(
        fila_cobertura["Numero_publicaciones"]
    )
    if numero_publicaciones is None:
        return False
    if fila_cobertura["Estado"] == "sin_edicion":
        return numero_publicaciones == 0
    if numero_publicaciones == 0:
        return True

    if df_publicaciones is None or df_publicaciones.empty:
        return False
    columnas_necesarias = {
        "Publicacion_ID",
        "Fecha_BOE",
        "Version_extractor",
        "Estado_analisis",
        "Coincidencias",
    }
    if not columnas_necesarias.issubset(df_publicaciones.columns):
        return False
    publicaciones = df_publicaciones.copy(deep=True)
    publicaciones = publicaciones[
        publicaciones["Fecha_BOE"].map(_fecha_comparable_segura)
        == fecha_objetivo
    ]
    if publicaciones.empty:
        return False
    if not publicaciones["Publicacion_ID"].map(_id_valido).all():
        return False
    publicaciones = publicaciones.drop_duplicates(
        subset=["Publicacion_ID"], keep="last"
    )
    if len(publicaciones) != numero_publicaciones:
        return False

    for publicacion in publicaciones.to_dict(orient="records"):
        comparacion_publicacion = comparar_versiones(
            publicacion["Version_extractor"], version_actual
        )
        if comparacion_publicacion is None or comparacion_publicacion < 0:
            return False
        estado = publicacion["Estado_analisis"]
        numero_coincidencias = _numero_publicaciones_valido(
            publicacion["Coincidencias"]
        )
        if estado == "sin_coincidencias":
            if numero_coincidencias != 0:
                return False
            continue
        if estado != "con_coincidencias" or not numero_coincidencias:
            return False
        if (
            df_oposiciones is None
            or "Publicacion_ID" not in df_oposiciones.columns
            or not (
                df_oposiciones["Publicacion_ID"] == publicacion["Publicacion_ID"]
            ).any()
        ):
            return False
    return True


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
        return _ajustar_tipos_cobertura(pd.DataFrame(columns=COLUMNAS_COBERTURA))
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
        resultado.loc[len(resultado)] = [fila[columna] for columna in COLUMNAS_COBERTURA]
    return _ajustar_tipos_cobertura(resultado[COLUMNAS_COBERTURA])


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


def _fecha_comparable(fecha):
    if isinstance(fecha, datetime):
        return fecha.date()
    if isinstance(fecha, pd.Timestamp):
        return fecha.date()
    if not isinstance(fecha, str) or not fecha.strip():
        raise ValueError("La fecha no es válida")
    texto = fecha.strip()
    for formato in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            pass
    return convertir_fecha(texto).date()


def _fecha_comparable_segura(fecha):
    try:
        return _fecha_comparable(fecha)
    except (TypeError, ValueError, AttributeError):
        return None


def _numero_publicaciones_valido(valor):
    if valor is None or pd.isna(valor) or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    if not numero.is_integer() or numero < 0:
        return None
    return int(numero)


def _id_valido(publicacion_id):
    return isinstance(publicacion_id, str) and bool(
        PATRON_PUBLICACION_ID.fullmatch(publicacion_id)
    )


def _ajustar_tipos_cobertura(df_cobertura):
    resultado = df_cobertura.copy(deep=True)
    for columna in COLUMNAS_TEXTO_COBERTURA:
        resultado[columna] = resultado[columna].astype("object")
    return resultado
