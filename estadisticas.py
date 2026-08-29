from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile
import re
import unicodedata

import pandas as pd
from openpyxl.utils.exceptions import InvalidFileException


class ErrorLecturaOposiciones(Exception):
    """Error al leer la hoja de datos estadísticos."""


class ExcelCorruptoError(ErrorLecturaOposiciones):
    """El archivo indicado no es un libro Excel válido."""


class HojaOposicionesAusenteError(ErrorLecturaOposiciones):
    """El libro no contiene la hoja Oposiciones."""


MESES = {
    "enero": "01",
    "febrero": "02",
    "marzo": "03",
    "abril": "04",
    "mayo": "05",
    "junio": "06",
    "julio": "07",
    "agosto": "08",
    "septiembre": "09",
    "octubre": "10",
    "noviembre": "11",
    "diciembre": "12",
}


def leer_oposiciones(ruta_excel):
    """Lee una instantánea en memoria de la hoja Oposiciones."""
    ruta = Path(ruta_excel)
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe el archivo Excel: {ruta}")

    contenido = ruta.read_bytes()
    try:
        with pd.ExcelFile(BytesIO(contenido), engine="openpyxl") as libro:
            if "Oposiciones" not in libro.sheet_names:
                raise HojaOposicionesAusenteError(
                    "El archivo Excel no contiene la hoja 'Oposiciones'."
                )
            return libro.parse("Oposiciones")
    except HojaOposicionesAusenteError:
        raise
    except (BadZipFile, InvalidFileException, OSError, ValueError) as error:
        raise ExcelCorruptoError(
            f"No se puede leer el archivo Excel '{ruta}': archivo corrupto o no válido."
        ) from error


def normalizar_datos(df):
    """Añade columnas auxiliares tolerantes sin modificar el DataFrame recibido."""
    columnas_faltantes = [
        columna for columna in ("Fecha_boe", "Num_plazas") if columna not in df.columns
    ]
    if columnas_faltantes:
        raise ValueError(
            "Faltan columnas obligatorias: " + ", ".join(columnas_faltantes)
        )

    resultado = df.copy(deep=True)
    resultado["Fecha_dt"] = resultado["Fecha_boe"].map(_convertir_fecha)
    resultado["Num_plazas_num"] = pd.to_numeric(
        resultado["Num_plazas"], errors="coerce"
    )
    return resultado


def filtrar_datos(
    df,
    fecha_inicio=None,
    fecha_final=None,
    puesto=None,
    provincia=None,
    sistema=None,
    turno=None,
):
    """Filtra por fechas inclusivas y por todas las palabras indicadas en el puesto."""
    resultado = df.copy(deep=True)
    if "Fecha_dt" not in resultado.columns:
        resultado = normalizar_datos(resultado)

    fechas = pd.to_datetime(resultado["Fecha_dt"], errors="coerce")
    if fecha_inicio is not None:
        inicio = _convertir_fecha_filtro(fecha_inicio, "fecha inicial")
        resultado = resultado[fechas.dt.normalize() >= inicio]
        fechas = fechas.loc[resultado.index]
    if fecha_final is not None:
        final = _convertir_fecha_filtro(fecha_final, "fecha final")
        resultado = resultado[fechas.dt.normalize() <= final]

    palabras = _normalizar_texto(puesto).split() if puesto else []
    if palabras:
        if "Puesto" not in resultado.columns:
            raise ValueError("Falta la columna obligatoria: Puesto")
        puestos_normalizados = resultado["Puesto"].fillna("").map(_normalizar_texto)
        mascara = puestos_normalizados.map(
            lambda texto: all(palabra in texto for palabra in palabras)
        )
        resultado = resultado[mascara]

    for valor, columna in (
        (provincia, "Provincia"),
        (sistema, "Sistema"),
        (turno, "Turno"),
    ):
        if valor:
            if columna not in resultado.columns:
                raise ValueError(f"Falta la columna obligatoria: {columna}")
            resultado = resultado[
                resultado[columna].fillna("").astype(str).str.strip() == valor
            ]

    return resultado.copy()


def obtener_opciones_filtros(df):
    """Devuelve valores válidos y ordenados para los filtros exactos."""
    return {
        "provincias": _valores_validos(df, "Provincia"),
        "sistemas": _valores_validos(df, "Sistema"),
        "turnos": _valores_validos(df, "Turno"),
    }


def calcular_estadisticas(df, top_administraciones=5, top_puestos=10):
    """Calcula los indicadores y agrupaciones sobre los registros recibidos."""
    datos = df.copy(deep=True)
    if "Fecha_dt" not in datos.columns or "Num_plazas_num" not in datos.columns:
        datos = normalizar_datos(datos)

    calidad_datos = {
        "fechas_invalidas": int(datos["Fecha_dt"].isna().sum()),
        "numeros_plazas_invalidos": int(datos["Num_plazas_num"].isna().sum()),
    }
    total_plazas = _numero_python(datos["Num_plazas_num"].sum(min_count=1))
    if pd.isna(total_plazas):
        total_plazas = 0

    top_administraciones_datos = _agrupar(
        datos, "Administración", top_administraciones
    )
    top_puestos_datos = _agrupar(datos, "Puesto", top_puestos)

    provincias = datos.copy()
    if "Provincia" not in provincias.columns:
        provincias["Provincia"] = "Sin provincia"
    provincias["Provincia"] = provincias["Provincia"].fillna("Sin provincia")
    provincias.loc[
        provincias["Provincia"].astype(str).str.strip() == "", "Provincia"
    ] = "Sin provincia"
    plazas_por_provincia = _agrupar(provincias, "Provincia")
    plazas_por_provincia = plazas_por_provincia[
        plazas_por_provincia["Num_plazas_num"] > 0
    ]

    provincias_reales = plazas_por_provincia[
        plazas_por_provincia["Provincia"].astype(str).str.strip().str.casefold()
        != "sin provincia"
    ]
    administraciones = _agrupar(datos, "Administración")
    administraciones = administraciones[
        (administraciones["Num_plazas_num"] > 0)
        & (administraciones["Administración"].astype(str).str.strip() != "")
    ]

    fechas_validas = datos.dropna(subset=["Fecha_dt"]).copy()
    fechas_validas["Mes"] = pd.to_datetime(fechas_validas["Fecha_dt"]).dt.to_period(
        "M"
    )
    evolucion = (
        fechas_validas.groupby("Mes", as_index=False, dropna=False)["Num_plazas_num"]
        .sum()
        .sort_values("Mes")
    )

    return {
        "total_plazas": total_plazas,
        "total_registros": int(len(datos)),
        "total_provincias": int(len(provincias_reales)),
        "total_administraciones": int(len(administraciones)),
        "top_administraciones": _registros_agrupados(
            top_administraciones_datos, "Administración", "administracion"
        ),
        "top_puestos": _registros_agrupados(top_puestos_datos, "Puesto", "puesto"),
        "plazas_por_provincia": _registros_agrupados(
            plazas_por_provincia, "Provincia", "provincia"
        ),
        "evolucion_mensual": [
            {"mes": str(fila["Mes"]), "plazas": _numero_python(fila["Num_plazas_num"])}
            for _, fila in evolucion.iterrows()
        ],
        "calidad_datos": calidad_datos,
    }


def _convertir_fecha(valor):
    if pd.isna(valor):
        return pd.NaT
    if not isinstance(valor, str):
        return pd.to_datetime(valor, errors="coerce")

    fecha = valor.strip().lower()
    for mes, numero in MESES.items():
        fecha = re.sub(rf"\s+de\s+{mes}\s+de\s+", f"/{numero}/", fecha)
    fecha_convertida = pd.to_datetime(fecha, format="%d/%m/%Y", errors="coerce")
    if pd.isna(fecha_convertida):
        fecha_convertida = pd.to_datetime(fecha, format="%Y-%m-%d", errors="coerce")
    return fecha_convertida


def _convertir_fecha_filtro(valor, nombre):
    fecha = pd.to_datetime(valor, errors="coerce")
    if pd.isna(fecha):
        raise ValueError(f"La {nombre} no es válida: {valor}")
    return fecha.normalize()


def _normalizar_texto(texto):
    if texto is None or pd.isna(texto):
        return ""
    return "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", str(texto).casefold())
        if unicodedata.category(caracter) != "Mn"
    )


def _valores_validos(datos, columna):
    if columna not in datos.columns:
        return []
    valores = datos[columna].dropna().astype(str).str.strip()
    valores = valores[
        ~valores.str.casefold().isin(["", "--", "no disponible"])
    ].drop_duplicates()
    return sorted(valores.tolist(), key=_normalizar_texto)


def _agrupar(datos, columna, limite=None):
    if columna not in datos.columns:
        return pd.DataFrame(columns=[columna, "Num_plazas_num"])
    agrupado = (
        datos.dropna(subset=[columna])
        .groupby(columna, as_index=False)["Num_plazas_num"]
        .sum()
        .sort_values(["Num_plazas_num", columna], ascending=[False, True])
    )
    return agrupado.head(limite) if limite is not None else agrupado


def _registros_agrupados(datos, columna, clave):
    return [
        {clave: fila[columna], "plazas": _numero_python(fila["Num_plazas_num"])}
        for _, fila in datos.iterrows()
    ]


def _numero_python(valor):
    if pd.isna(valor):
        return valor
    numero = valor.item() if hasattr(valor, "item") else valor
    return int(numero) if float(numero).is_integer() else float(numero)
