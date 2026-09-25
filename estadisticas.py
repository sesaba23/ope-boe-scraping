import re
import unicodedata

import pandas as pd
from tipo_personal import TIPOS_PERSONAL

from consultas_boe import oposiciones


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
MESES_NOMBRES = ("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                 "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre")


def calcular_estadisticas_sqlite(ruta_bd="datos/boe.db", **filtros):
    """Flujo productivo: obtiene la selección desde SQLite, nunca desde Excel."""
    datos = oposiciones(ruta_bd, **filtros)
    return calcular_estadisticas(datos, puesto_seleccionado=filtros.get("puesto"))


def calcular_comparacion_puestos_sqlite(ruta_bd="datos/boe.db", puesto_principal=None, comparadores=(), **filtros):
    """Construye hasta seis series con una única consulta base y filtros compartidos."""
    comparadores = [str(valor).strip() for valor in comparadores if str(valor).strip()]
    if len(comparadores) > 5:
        raise ValueError("Se permiten como máximo cinco puestos comparativos.")
    if len(set(comparadores)) != len(comparadores):
        raise ValueError("No se permiten puestos comparativos duplicados.")
    if puesto_principal and puesto_principal in comparadores:
        raise ValueError("El puesto principal no puede repetirse como comparador.")
    filtros_sin_puesto = {clave: valor for clave, valor in filtros.items() if clave != "puesto" and valor}
    datos = oposiciones(ruta_bd, **filtros_sin_puesto)
    datos = normalizar_datos(datos)
    columna = "Puesto_normalizado" if "Puesto_normalizado" in datos.columns else "Puesto"
    puestos = datos[columna].fillna(datos["Puesto"]).astype(str).str.strip()
    if puesto_principal:
        principal = filtrar_datos(datos, puesto=puesto_principal)
        etiquetas = [(str(puesto_principal), principal)]
    else:
        principal = None
        etiquetas = []
    for comparador in comparadores:
        etiquetas.append((comparador, datos[puestos == comparador]))
    if not etiquetas:
        return _evolucion_puestos(datos)
    union = pd.concat([fila for _, fila in etiquetas], ignore_index=True) if etiquetas else datos.iloc[0:0]
    fechas = pd.to_datetime(union["Fecha_dt"], errors="coerce")
    anios = fechas.dropna().dt.year
    if anios.empty:
        return {"mode": "selected" if puesto_principal else "manual", "puesto": puesto_principal, "years": [], "series": []}
    years = list(range(int(anios.min()), int(anios.max()) + 1))
    series = []
    for etiqueta, frame in etiquetas:
        frame = frame.copy()
        frame["_anio"] = pd.to_datetime(frame["Fecha_dt"], errors="coerce").dt.year
        totals = frame.dropna(subset=["_anio"]).groupby("_anio")["Num_plazas_num"].sum().to_dict()
        series.append({"label": etiqueta, "values": [_numero_python(totals.get(year, 0)) for year in years]})
    mode = "selected" if puesto_principal else "manual"
    return {"mode": mode, "puesto": puesto_principal, "years": years, "series": series}


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
    tipo_personal=None,
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
    if tipo_personal:
        valores = {tipo_personal} if isinstance(tipo_personal, str) else set(tipo_personal)
        if "Tipo_personal" in resultado.columns:
            resultado = resultado[resultado["Tipo_personal"].fillna("No determinado").isin(valores)]
        else:
            resultado = resultado.iloc[0:0]

    return resultado.copy()


def obtener_opciones_filtros(df):
    """Devuelve valores válidos y ordenados para los filtros exactos."""
    resultado = {
        "provincias": _valores_validos(df, "Provincia"),
        "sistemas": _valores_validos(df, "Sistema"),
        "turnos": _valores_validos(df, "Turno"),
    }
    return resultado


def calcular_estadisticas(df, top_administraciones=5, top_puestos=10, puesto_seleccionado=None):
    """Calcula los indicadores y agrupaciones sobre los registros recibidos."""
    datos = df.copy(deep=True)
    if "Fecha_dt" not in datos.columns or "Num_plazas_num" not in datos.columns:
        datos = normalizar_datos(datos)

    columna_puesto = "Puesto_normalizado" if "Puesto_normalizado" in datos.columns else "Puesto"
    if columna_puesto == "Puesto_normalizado":
        datos["Puesto_normalizado"] = datos["Puesto_normalizado"].fillna(datos["Puesto"])
    calidad_datos = {
        "fecha_no_utilizable": int(datos["Fecha_dt"].isna().sum()),
        "numero_plazas_no_utilizable": int(datos["Num_plazas_num"].isna().sum()),
        "puesto_no_utilizable": _contar_no_disponibles(datos, columna_puesto),
        "provincia_no_disponible": _contar_no_disponibles(
            datos, "Provincia", marcadores=("sin provincia",)
        ),
        "administracion_no_disponible": _contar_no_disponibles(datos, "Administración"),
        "sistema_no_disponible": _contar_no_disponibles(datos, "Sistema"),
        "turno_no_disponible": _contar_no_disponibles(datos, "Turno"),
    }
    if "Ambito" in datos.columns:
        calidad_datos["municipio_no_disponible"] = _contar_no_disponibles(datos, "Municipio")
        calidad_datos["ambito_indeterminado"] = _contar_no_disponibles(datos, "Ambito", marcadores=("indeterminado",))
    total_plazas = _numero_python(datos["Num_plazas_num"].sum(min_count=1))
    if pd.isna(total_plazas):
        total_plazas = 0

    administraciones_validas = datos[
        ~_mascara_no_disponible(datos, "Administración")
    ]
    top_administraciones_datos = _agrupar(
        administraciones_validas, "Administración", top_administraciones
    )
    top_puestos_datos = _agrupar(datos, columna_puesto, top_puestos)

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

    comunidades = datos[
        ~_mascara_no_disponible(datos, "Comunidad_autonoma")
    ].copy()
    plazas_por_comunidad_completas = _agrupar(
        comunidades, "Comunidad_autonoma"
    )
    plazas_por_comunidad_completas = plazas_por_comunidad_completas[
        plazas_por_comunidad_completas["Num_plazas_num"] > 0
    ]
    # Representar todas las comunidades disponibles, sin agruparlas en
    # una categoría artificial «Resto».
    plazas_por_comunidad = plazas_por_comunidad_completas

    provincias_reales = plazas_por_provincia[
        plazas_por_provincia["Provincia"].astype(str).str.strip().str.casefold()
        != "sin provincia"
    ]
    administraciones = _agrupar(administraciones_validas, "Administración")
    administraciones = administraciones[
        (administraciones["Num_plazas_num"] > 0)
        & (administraciones["Administración"].astype(str).str.strip() != "")
    ]

    fechas_validas = datos.dropna(subset=["Fecha_dt"]).copy()
    fechas_validas["Anio"] = pd.to_datetime(fechas_validas["Fecha_dt"]).dt.year
    evolucion_agrupada = (
        fechas_validas.groupby("Anio", as_index=False, dropna=False)["Num_plazas_num"]
        .sum()
    )
    if evolucion_agrupada.empty:
        evolucion = evolucion_agrupada
    else:
        primer_anio = int(evolucion_agrupada["Anio"].min())
        ultimo_anio = int(evolucion_agrupada["Anio"].max())
        evolucion = pd.DataFrame({"Anio": range(primer_anio, ultimo_anio + 1)}).merge(
            evolucion_agrupada, on="Anio", how="left"
        )
        evolucion["Num_plazas_num"] = evolucion["Num_plazas_num"].fillna(0)

    plazas_por_mes = _plazas_por_mes(fechas_validas)
    evolucion_puestos = _evolucion_puestos(fechas_validas, puesto_seleccionado)
    resultado = {
        "total_plazas": total_plazas,
        "total_registros": int(len(datos)),
        "total_provincias": int(len(provincias_reales)),
        "total_administraciones": int(len(administraciones)),
        "top_administraciones": _registros_agrupados(
            top_administraciones_datos, "Administración", "administracion"
        ),
        "top_puestos": _registros_agrupados(top_puestos_datos, columna_puesto, "puesto"),
        "plazas_por_provincia": _registros_agrupados(
            plazas_por_provincia, "Provincia", "provincia"
        ),
        "plazas_por_comunidad": _registros_agrupados(
            plazas_por_comunidad, "Comunidad_autonoma", "comunidad"
        ),
        "evolucion_anual": [
            {"anio": int(fila["Anio"]), "plazas": _numero_python(fila["Num_plazas_num"])}
            for _, fila in evolucion.iterrows()
        ],
        "plazas_por_mes": plazas_por_mes,
        "evolucion_anual_puestos": evolucion_puestos,
        "calidad_datos": calidad_datos,
    }
    if "Tipo_personal" in datos.columns and datos["Tipo_personal"].notna().any():
        resultado["distribucion_tipo_personal"] = _distribucion_tipo_personal(datos)
    return resultado


def _distribucion_tipo_personal(datos):
    if "Tipo_personal" not in datos.columns:
        conteos = {}
    else:
        conteos = datos["Tipo_personal"].fillna("No determinado").astype(str).value_counts().to_dict()
    return [{"tipo_personal": categoria, "registros": int(conteos.get(categoria, 0))}
            for categoria in TIPOS_PERSONAL]


def _plazas_por_mes(datos):
    """Acumula todo el histórico filtrado por mes del año, siempre 12 meses."""
    valores = {i: 0 for i in range(1, 13)}
    if not datos.empty:
        meses = pd.to_datetime(datos["Fecha_dt"], errors="coerce").dt.month
        for mes, plazas in datos.assign(_mes=meses).dropna(subset=["_mes"]).groupby("_mes")["Num_plazas_num"].sum().items():
            valores[int(mes)] = _numero_python(plazas)
    return [{"mes": i, "nombre": MESES_NOMBRES[i - 1], "plazas": valores[i]} for i in range(1, 13)]


def _evolucion_puestos(datos, puesto_seleccionado=None):
    """Devuelve una serie por puesto seleccionado o el TOP 5 del universo filtrado."""
    if datos.empty:
        return {"mode": "selected" if puesto_seleccionado else "top5", "puesto": str(puesto_seleccionado) if puesto_seleccionado else None, "years": [], "series": []}
    columna = "Puesto_normalizado" if "Puesto_normalizado" in datos.columns else "Puesto"
    datos = datos.copy()
    datos[columna] = datos[columna].fillna(datos.get("Puesto", ""))
    fechas = pd.to_datetime(datos["Fecha_dt"], errors="coerce")
    datos = datos.assign(_anio=fechas.dt.year).dropna(subset=["_anio"])
    if datos.empty:
        return {"mode": "selected" if puesto_seleccionado else "top5", "puesto": str(puesto_seleccionado) if puesto_seleccionado else None, "years": [], "series": []}
    if puesto_seleccionado:
        labels = [str(puesto_seleccionado)]
    else:
        ranking = datos.groupby(columna)["Num_plazas_num"].sum().sort_values(ascending=False)
        labels = sorted(ranking.head(5).index.tolist(), key=lambda value: (-(ranking[value]), str(value)))
    years = list(range(int(datos["_anio"].min()), int(datos["_anio"].max()) + 1))
    series = []
    for label in labels:
        subset = datos if puesto_seleccionado else datos[datos[columna] == label]
        # Con un filtro textual, todas las filas ya pertenecen al puesto consultado.
        totals = subset.groupby("_anio")["Num_plazas_num"].sum().to_dict()
        series.append({"label": label, "values": [_numero_python(totals.get(year, 0)) for year in years]})
    return {"mode": "selected" if puesto_seleccionado else "top5", "puesto": str(puesto_seleccionado) if puesto_seleccionado else None, "years": years, "series": series}


def _convertir_fecha(valor):
    if pd.isna(valor):
        return pd.NaT
    if isinstance(valor, int) and re.fullmatch(r"\d{8}", str(valor)):
        return pd.to_datetime(str(valor), format="%Y%m%d", errors="coerce")
    if not isinstance(valor, str):
        return pd.to_datetime(valor, errors="coerce")

    fecha = valor.strip().lower()
    if re.fullmatch(r"\d{8}", fecha):
        return pd.to_datetime(fecha, format="%Y%m%d", errors="coerce")
    for mes, numero in MESES.items():
        fecha = re.sub(rf"\s+de\s+{mes}\s+de\s+", f"/{numero}/", fecha)
    fecha_convertida = pd.to_datetime(fecha, format="%d/%m/%Y", errors="coerce")
    if pd.isna(fecha_convertida):
        fecha_convertida = pd.to_datetime(fecha, format="%Y-%m-%d", errors="coerce")
    return fecha_convertida


def _mascara_no_disponible(datos, columna, marcadores=()):
    if columna not in datos.columns:
        return pd.Series(True, index=datos.index, dtype=bool)
    valores = datos[columna]
    textos = valores.fillna("").astype(str).str.strip().str.casefold()
    return valores.isna() | textos.isin(("", "--", "no disponible", *marcadores))


def _contar_no_disponibles(datos, columna, marcadores=()):
    return int(_mascara_no_disponible(datos, columna, marcadores).sum())


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
