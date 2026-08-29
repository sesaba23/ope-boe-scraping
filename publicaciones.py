from datetime import datetime
import re

import pandas as pd

from trazabilidad import (
    VERSION_EXTRACTOR,
    comparar_versiones,
    enriquecer_historico_oposiciones,
    extraer_publicacion_id,
    necesita_reprocesamiento,
)
from resolucion_administraciones import VERSION_RESOLUCION, resolver_administracion


COLUMNAS_PUBLICACIONES = [
    "Publicacion_ID",
    "Enlace",
    "Fecha_BOE",
    "Titulo_original",
    "Fecha_ultimo_analisis",
    "Version_extractor",
    "Estado_analisis",
    "Coincidencias",
    "Departamento_BOE",
    "Administracion_resuelta",
    "Familia_administrativa",
    "Estado_resolucion",
    "Metodo_resolucion",
    "Confianza_resolucion",
    "Version_resolucion",
]


def publicaciones_desde_oposiciones(df_oposiciones):
    """Reconstruye publicaciones históricas respaldadas por filas de Oposiciones."""
    oposiciones = enriquecer_historico_oposiciones(df_oposiciones)
    if oposiciones.empty:
        return pd.DataFrame(columns=COLUMNAS_PUBLICACIONES)

    filas = []
    for publicacion_id, grupo in oposiciones.dropna(
        subset=["Publicacion_ID"]
    ).groupby("Publicacion_ID", sort=False):
        filas.append(
            {
                "Publicacion_ID": publicacion_id,
                "Enlace": _primer_valor(grupo, "Enlace"),
                "Fecha_BOE": _primer_valor(grupo, "Fecha_boe"),
                "Titulo_original": "",
                "Fecha_ultimo_analisis": _ultimo_valor(
                    grupo, "Fecha_analisis"
                ),
                "Version_extractor": _primer_valor(
                    grupo, "Version_extractor", "legacy"
                ),
                "Estado_analisis": "con_coincidencias",
                "Coincidencias": int(len(grupo)),
            }
        )
    return pd.DataFrame(filas, columns=COLUMNAS_PUBLICACIONES)


def crear_registro_publicacion(enlace, fecha_boe, titulo, coincidencias, momento=None,
                               version_extractor=VERSION_EXTRACTOR, departamento_boe="",
                               titulo_sumario=None):
    """Crea el registro de un análisis correcto de una publicación."""
    fecha_analisis = (momento or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    titulo_boe = titulo_sumario if isinstance(titulo_sumario, str) and titulo_sumario.strip() else titulo
    resolucion = resolver_administracion(titulo_boe, departamento_boe)
    return {
        "Publicacion_ID": extraer_publicacion_id(enlace),
        "Enlace": enlace,
        "Fecha_BOE": _extraer_fecha_oficial(fecha_boe),
        "Titulo_original": titulo_boe,
        "Fecha_ultimo_analisis": fecha_analisis,
        "Version_extractor": version_extractor or VERSION_EXTRACTOR,
        "Estado_analisis": (
            "con_coincidencias" if coincidencias > 0 else "sin_coincidencias"
        ),
        "Coincidencias": int(coincidencias),
        "Departamento_BOE": departamento_boe or "",
        "Administracion_resuelta": resolucion.administracion,
        "Familia_administrativa": resolucion.familia,
        "Estado_resolucion": resolucion.estado,
        "Metodo_resolucion": resolucion.metodo,
        "Confianza_resolucion": resolucion.confianza,
        "Version_resolucion": VERSION_RESOLUCION,
    }


def registrar_publicacion(df_publicaciones, registro):
    """Inserta o actualiza una publicación sin duplicar su identificador."""
    publicaciones = _normalizar_columnas(df_publicaciones)
    publicacion_id = registro.get("Publicacion_ID")
    if not publicacion_id:
        return publicaciones

    coincidencias = publicaciones.index[
        publicaciones["Publicacion_ID"] == publicacion_id
    ].tolist()
    if not coincidencias:
        nueva = {columna: registro.get(columna, pd.NA) for columna in COLUMNAS_PUBLICACIONES}
        return pd.concat([publicaciones, pd.DataFrame([nueva])], ignore_index=True)

    indice = coincidencias[-1]
    if len(coincidencias) > 1:
        publicaciones = publicaciones.drop(index=coincidencias[:-1]).reset_index(drop=True)
        indice = publicaciones.index[publicaciones["Publicacion_ID"] == publicacion_id][-1]

    for columna in ("Enlace", "Fecha_BOE", "Titulo_original", "Departamento_BOE"):
        if _esta_vacio(publicaciones.at[indice, columna]) and not _esta_vacio(
            registro.get(columna)
        ):
            publicaciones.at[indice, columna] = registro[columna]
    for columna in (
        "Fecha_ultimo_analisis",
        "Version_extractor",
        "Estado_analisis",
        "Coincidencias",
        "Administracion_resuelta",
        "Familia_administrativa",
        "Estado_resolucion",
        "Metodo_resolucion",
        "Confianza_resolucion",
        "Version_resolucion",
    ):
        publicaciones.at[indice, columna] = registro.get(columna, pd.NA)
    return publicaciones[COLUMNAS_PUBLICACIONES]


def normalizar_publicaciones(df_publicaciones):
    """Normaliza el esquema y consolida identificadores repetidos conservando datos válidos."""
    resultado = pd.DataFrame(columns=COLUMNAS_PUBLICACIONES)
    for registro in _normalizar_columnas(df_publicaciones).to_dict(orient="records"):
        resultado = registrar_publicacion(resultado, registro)
    return resultado


def debe_procesar_publicacion(codigo, codigos_procesados, enlace, df_publicaciones):
    """Combina la exclusión histórica con la versión conocida de la publicación."""
    if codigo not in codigos_procesados:
        return True
    publicacion_id = extraer_publicacion_id(enlace)
    if publicacion_id is None:
        return False

    publicaciones = _normalizar_columnas(df_publicaciones)
    coincidencias = publicaciones[
        publicaciones["Publicacion_ID"] == publicacion_id
    ]
    version = (
        coincidencias.iloc[-1]["Version_extractor"]
        if not coincidencias.empty
        else None
    )
    return necesita_reprocesamiento(version)


def puede_reutilizar_publicacion(
    publicacion_id,
    df_publicaciones,
    df_oposiciones,
    version_actual=VERSION_EXTRACTOR,
):
    """Comprueba si el último análisis permite reutilizar los datos locales."""
    if publicacion_id is None:
        return False
    publicaciones = _normalizar_columnas(df_publicaciones)
    coincidencias = publicaciones[
        publicaciones["Publicacion_ID"] == publicacion_id
    ]
    if coincidencias.empty:
        return False

    publicacion = coincidencias.iloc[-1]
    comparacion = comparar_versiones(
        publicacion["Version_extractor"], version_actual
    )
    if comparacion is None or comparacion < 0:
        return False

    estado = publicacion["Estado_analisis"]
    try:
        numero_coincidencias = int(publicacion["Coincidencias"])
    except (TypeError, ValueError):
        return False
    if estado == "sin_coincidencias":
        return numero_coincidencias == 0
    if estado != "con_coincidencias" or numero_coincidencias <= 0:
        return False
    if comparacion > 0:
        return True
    if "Publicacion_ID" not in df_oposiciones.columns:
        return False
    return bool((df_oposiciones["Publicacion_ID"] == publicacion_id).any())


def _normalizar_columnas(df):
    resultado = df.copy(deep=True)
    for columna in COLUMNAS_PUBLICACIONES:
        if columna not in resultado.columns:
            resultado[columna] = pd.Series(pd.NA, index=resultado.index, dtype="object")
    return resultado[COLUMNAS_PUBLICACIONES]


def _esta_vacio(valor):
    return valor is None or pd.isna(valor) or str(valor).strip() == ""


def _primer_valor(datos, columna, predeterminado=pd.NA):
    if columna not in datos.columns:
        return predeterminado
    valores = datos[columna].dropna()
    valores = valores[valores.astype(str).str.strip() != ""]
    return valores.iloc[0] if not valores.empty else predeterminado


def _ultimo_valor(datos, columna):
    if columna not in datos.columns:
        return pd.NA
    valores = datos[columna].dropna()
    valores = valores[valores.astype(str).str.strip() != ""]
    return valores.max() if not valores.empty else pd.NA


def _extraer_fecha_oficial(texto):
    if not isinstance(texto, str):
        return pd.NA
    coincidencia = re.search(r"(?:de\s+)?(\d{1,2} de \w+ de \d{4})", texto)
    return coincidencia.group(1) if coincidencia else pd.NA
