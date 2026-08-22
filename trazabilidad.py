from datetime import datetime
import re
from urllib.parse import parse_qs, urlparse

import pandas as pd


VERSION_EXTRACTOR = "1"
COLUMNAS_TRAZABILIDAD = ["Publicacion_ID", "Version_extractor", "Fecha_analisis"]
PATRON_PUBLICACION_ID = re.compile(r"BOE-[A-Z]-\d{4}-\d+")


def necesita_reprocesamiento(version_publicacion, version_actual=VERSION_EXTRACTOR):
    """Indica si una publicación requiere una versión más reciente del extractor."""
    version_guardada = _convertir_version(version_publicacion)
    version_objetivo = _convertir_version(version_actual)
    if version_guardada is None or version_objetivo is None:
        return True
    return version_guardada < version_objetivo


def comparar_versiones(version_publicacion, version_actual=VERSION_EXTRACTOR):
    """Compara versiones enteras: -1 anterior, 0 igual, 1 posterior o None inválida."""
    version_guardada = _convertir_version(version_publicacion)
    version_objetivo = _convertir_version(version_actual)
    if version_guardada is None or version_objetivo is None:
        return None
    return (version_guardada > version_objetivo) - (
        version_guardada < version_objetivo
    )


def extraer_publicacion_id(enlace):
    """Extrae un identificador oficial del parámetro id de un enlace BOE."""
    if not isinstance(enlace, str):
        return None
    valores = parse_qs(urlparse(enlace).query, keep_blank_values=True).get("id", [])
    if len(valores) != 1 or PATRON_PUBLICACION_ID.fullmatch(valores[0]) is None:
        return None
    return valores[0]


def añadir_trazabilidad_convocatorias(resultados, enlace, momento=None):
    """Añade la misma trazabilidad a todos los resultados de una publicación."""
    fecha_analisis = (momento or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    trazabilidad = {
        "Publicacion_ID": extraer_publicacion_id(enlace),
        "Version_extractor": VERSION_EXTRACTOR,
        "Fecha_analisis": fecha_analisis,
    }
    return [{**resultado, **trazabilidad} for resultado in resultados]


def enriquecer_historico_oposiciones(df):
    """Completa la trazabilidad desconocida del histórico sobre una copia."""
    resultado = df.copy(deep=True)
    columnas_originales = [
        columna for columna in resultado.columns if columna not in COLUMNAS_TRAZABILIDAD
    ]

    if "Publicacion_ID" not in resultado.columns:
        resultado["Publicacion_ID"] = pd.Series(pd.NA, index=resultado.index, dtype="object")
    ids_ausentes = resultado["Publicacion_ID"].isna() | (
        resultado["Publicacion_ID"].astype(str).str.strip() == ""
    )
    if "Enlace" in resultado.columns:
        resultado.loc[ids_ausentes, "Publicacion_ID"] = resultado.loc[
            ids_ausentes, "Enlace"
        ].map(extraer_publicacion_id)

    if "Version_extractor" not in resultado.columns:
        resultado["Version_extractor"] = "legacy"
    else:
        versiones_ausentes = resultado["Version_extractor"].isna() | (
            resultado["Version_extractor"].astype(str).str.strip() == ""
        )
        resultado.loc[versiones_ausentes, "Version_extractor"] = "legacy"

    if "Fecha_analisis" not in resultado.columns:
        resultado["Fecha_analisis"] = pd.Series(pd.NA, index=resultado.index, dtype="object")

    return resultado[columnas_originales + COLUMNAS_TRAZABILIDAD]


def _convertir_version(version):
    if version is None or pd.isna(version):
        return None
    texto = str(version).strip()
    if re.fullmatch(r"[1-9]\d*", texto) is None:
        return None
    return int(texto)
