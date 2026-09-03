from datetime import datetime

import pandas as pd

from fechas import convertir_fecha
from trazabilidad import (
    PATRON_PUBLICACION_ID,
    VERSION_EXTRACTOR,
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
ESTADO_INCOHERENCIA_HISTORICA_VERIFICADA = "incoherencia_historica_verificada"
ESTADOS_VALIDOS = {"consultado", "sin_edicion"}
ESTADOS_REUTILIZABLES = ESTADOS_VALIDOS | {ESTADO_INCOHERENCIA_HISTORICA_VERIFICADA}
ESTADOS_COBERTURA = ESTADOS_REUTILIZABLES | {"error"}


def puede_reutilizar_cobertura(
    fecha,
    df_cobertura,
    df_publicaciones,
    df_oposiciones,
    version_actual=VERSION_EXTRACTOR,
):
    """Compatibilidad: decide si un índice diario puede omitirse.

    La versión se mantiene en la firma por compatibilidad, pero corresponde a
    la fase de análisis, no a la cobertura del índice BOE.
    """
    return cobertura_indice_reutilizable(fecha, df_cobertura, df_publicaciones)


def cobertura_indice_reutilizable(fecha, df_cobertura, df_publicaciones):
    """Valida exclusivamente la cobertura y el descubrimiento del índice BOE."""
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
    if fila_cobertura["Estado"] not in ESTADOS_REUTILIZABLES:
        return False
    numero_publicaciones = _numero_publicaciones_valido(
        fila_cobertura["Numero_publicaciones"]
    )
    if numero_publicaciones is None:
        return False
    if fila_cobertura["Estado"] == ESTADO_INCOHERENCIA_HISTORICA_VERIFICADA:
        # La discrepancia entre el índice actual y el histórico se ha revisado
        # explícitamente; se conserva, pero no debe reabrir un scraping.
        return True
    publicaciones = _publicaciones_de_fecha(df_publicaciones, fecha_objetivo)
    if fila_cobertura["Estado"] == "sin_edicion":
        return numero_publicaciones == 0 and publicaciones.empty
    if numero_publicaciones == 0:
        return publicaciones.empty
    if publicaciones.empty:
        return False
    if not publicaciones["Publicacion_ID"].map(_id_valido).all():
        return False
    publicaciones = publicaciones.drop_duplicates(
        subset=["Publicacion_ID"], keep="last"
    )
    if len(publicaciones) != numero_publicaciones:
        return False
    return True


def crear_verificador_cobertura_indice(df_cobertura, df_publicaciones):
    """Prepara un verificador O(1) por fecha sin cambiar los DataFrames."""
    cobertura = normalizar_cobertura(df_cobertura)
    filas = {
        _fecha_comparable_segura(fila["Fecha"]): fila
        for fila in cobertura.to_dict(orient="records")
    }
    publicaciones_por_fecha = {}
    if df_publicaciones is not None and not df_publicaciones.empty:
        if {"Publicacion_ID", "Fecha_BOE"}.issubset(df_publicaciones.columns):
            for fila in df_publicaciones[["Publicacion_ID", "Fecha_BOE"]].to_dict(orient="records"):
                fecha_publicacion = _fecha_comparable_segura(fila["Fecha_BOE"])
                if fecha_publicacion is not None:
                    publicaciones_por_fecha.setdefault(fecha_publicacion, []).append(fila["Publicacion_ID"])

    def verificar(fecha):
        try:
            fecha_objetivo = _fecha_comparable(fecha)
        except (TypeError, ValueError):
            return False
        fila = filas.get(fecha_objetivo)
        if fila is None or fila["Estado"] not in ESTADOS_REUTILIZABLES:
            return False
        numero = _numero_publicaciones_valido(fila["Numero_publicaciones"])
        if numero is None:
            return False
        if fila["Estado"] == ESTADO_INCOHERENCIA_HISTORICA_VERIFICADA:
            return True
        ids = publicaciones_por_fecha.get(fecha_objetivo, [])
        if fila["Estado"] == "sin_edicion":
            return numero == 0 and not ids
        if numero == 0:
            return not ids
        return len(ids) == numero and len(set(ids)) == numero and all(
            _id_valido(publicacion_id) for publicacion_id in ids
        )

    return verificar


def _publicaciones_de_fecha(df_publicaciones, fecha_objetivo):
    if df_publicaciones is None or df_publicaciones.empty:
        return pd.DataFrame(columns=["Publicacion_ID", "Fecha_BOE"])
    if not {"Publicacion_ID", "Fecha_BOE"}.issubset(df_publicaciones.columns):
        return pd.DataFrame(columns=["Publicacion_ID", "Fecha_BOE"])
    publicaciones = df_publicaciones[["Publicacion_ID", "Fecha_BOE"]].copy(deep=True)
    return publicaciones[
        publicaciones["Fecha_BOE"].map(_fecha_comparable_segura) == fecha_objetivo
    ]


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
        if estado == "error" and estado_anterior in ESTADOS_REUTILIZABLES:
            cobertura.at[indice, "Fecha_ultima_consulta"] = fecha_consulta
            return cobertura[COLUMNAS_COBERTURA]
    else:
        indice = len(cobertura)
        cobertura.loc[indice, "Fecha"] = fecha_normalizada

    cobertura.at[indice, "Estado"] = estado
    cobertura.at[indice, "Fecha_ultima_consulta"] = fecha_consulta
    if estado in ESTADOS_REUTILIZABLES:
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

    por_fecha = {}
    for fila in origen[COLUMNAS_COBERTURA].to_dict(orient="records"):
        try:
            fecha = _normalizar_fecha(fila["Fecha"])
        except (TypeError, ValueError):
            continue
        anterior = por_fecha.get(fecha)
        if anterior is not None:
            if fila["Estado"] == "error" and anterior["Estado"] in ESTADOS_REUTILIZABLES:
                anterior["Fecha_ultima_consulta"] = fila["Fecha_ultima_consulta"]
                continue
        fila["Fecha"] = fecha
        por_fecha.pop(fecha, None)
        por_fecha[fecha] = fila
    resultado = pd.DataFrame(list(por_fecha.values()), columns=COLUMNAS_COBERTURA)
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
