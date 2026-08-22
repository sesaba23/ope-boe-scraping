import argparse
from collections import Counter
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
import re
import unicodedata

import pandas as pd

from fechas import convertir_fecha
from trazabilidad import PATRON_PUBLICACION_ID, VERSION_EXTRACTOR, comparar_versiones


COLUMNAS_CALIDAD = [
    "Num_plazas", "Puesto", "Administración", "Escala", "Subescala",
    "Clase", "Sistema", "Turno", "Fecha_boe", "Publicación", "Enlace",
    "Municipio", "Provincia", "Latitud", "Longitud", "Habitantes",
    "Publicacion_ID", "Version_extractor", "Fecha_analisis",
]
COLUMNAS_CATEGORICAS = ["Sistema", "Turno", "Escala", "Subescala", "Clase"]
CLAVE_DEDUPLICACION = [
    "Puesto", "Fecha_boe", "Administración", "Enlace", "Num_plazas",
    "Turno", "Sistema", "Escala", "Subescala", "Clase",
]
COLUMNAS_CASOS = [
    "Publicacion_ID", "Puesto", "Administración", "Municipio", "Provincia",
    "Latitud", "Longitud",
]
MARCADORES_AUSENTES = {"", "--", "no disponible"}


def leer_excel_auditoria(ruta_excel):
    """Lee el libro desde una instantánea en memoria sin abrirlo para escritura."""
    ruta = Path(ruta_excel)
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el archivo Excel: {ruta}")
    contenido = ruta.read_bytes()
    try:
        hojas = pd.read_excel(BytesIO(contenido), sheet_name=None)
    except Exception as error:
        raise ValueError(f"No se puede leer el archivo Excel: {error}") from error
    if "Oposiciones" not in hojas:
        raise ValueError("El libro no contiene la hoja obligatoria 'Oposiciones'")
    return hojas


def auditar_datos(ruta_excel="BOE-oposiciones.xlsx"):
    """Analiza el libro y devuelve todas las métricas sin modificarlo."""
    hojas = leer_excel_auditoria(ruta_excel)
    oposiciones = hojas["Oposiciones"].copy(deep=True)
    publicaciones = hojas.get("Publicaciones", pd.DataFrame()).copy(deep=True)
    cobertura = hojas.get("Cobertura", pd.DataFrame()).copy(deep=True)
    busquedas = hojas.get("Búsquedas", pd.DataFrame()).copy(deep=True)
    errores = hojas.get("Log-errores", pd.DataFrame()).copy(deep=True)

    diagnostico_segundo_nivel = {
        "versiones": _diagnosticar_versiones(publicaciones),
        "convocatorias_duplicadas": _diagnosticar_publicacion_puesto(oposiciones),
        "multiconvocatorias": _diagnosticar_multiconvocatorias(oposiciones),
        "estado_errores": _diagnosticar_log_errores(
            errores, publicaciones, oposiciones, cobertura
        ),
        "geolocalizacion_por_tipo": _diagnosticar_geolocalizacion(oposiciones),
    }

    return {
        "archivo": str(Path(ruta_excel)),
        "resumen": _resumen(oposiciones),
        "calidad_columnas": _calidad_columnas(oposiciones),
        "geolocalizacion": _auditar_geolocalizacion(oposiciones),
        "categoricos": {
            columna: _auditar_valores(oposiciones, columna)
            for columna in COLUMNAS_CATEGORICAS
        },
        "puestos": _auditar_entidad(oposiciones, "Puesto", puesto=True),
        "administraciones": _auditar_administraciones(oposiciones),
        "fechas": _auditar_fechas(oposiciones, publicaciones),
        "publicaciones": _auditar_publicaciones(publicaciones, oposiciones),
        "cobertura": _auditar_cobertura(cobertura, publicaciones),
        "busquedas": _auditar_busquedas(busquedas),
        "errores": _auditar_errores(errores, publicaciones),
        "duplicados": _auditar_duplicados(oposiciones),
        "diagnostico_segundo_nivel": diagnostico_segundo_nivel,
        "hojas_presentes": list(hojas),
    }


def generar_informe_markdown(auditoria, ruta_salida="informe_auditoria_datos.md"):
    """Genera el único artefacto de salida permitido: el informe Markdown."""
    r = auditoria["resumen"]
    geo = auditoria["geolocalizacion"]
    lineas = [
        "# Informe de auditoría de datos BOE", "", "## Resumen ejecutivo", "",
        _tabla_dict(r), "", "### Incidencias principales", "",
        _tabla_dict(_incidencias(auditoria)), "", "## Calidad por columnas", "",
        _tabla(auditoria["calidad_columnas"]), "", "## Geolocalización", "",
        _tabla_dict({k: v for k, v in geo.items() if k != "casos_problematicos"}),
        "", "### Casos problemáticos", "", _tabla(geo["casos_problematicos"]),
        "", "## Valores categóricos", "",
    ]
    for columna, datos in auditoria["categoricos"].items():
        lineas += [f"### {columna}", "", "Frecuencias:", "", _tabla(datos["frecuencias"]),
                   "", "Posibles variantes:", "", _tabla(datos["variantes"]), ""]
    lineas += _seccion_entidad("Puestos", auditoria["puestos"])
    lineas += _seccion_entidad("Administraciones", auditoria["administraciones"])
    for titulo, clave in [
        ("Fechas", "fechas"), ("Publicaciones", "publicaciones"),
        ("Cobertura", "cobertura"), ("Búsquedas", "busquedas"),
        ("Log de errores", "errores"),
        ("Duplicados e inconsistencias", "duplicados"),
    ]:
        lineas += [f"## {titulo}", "", _render_bloque(auditoria[clave]), ""]
    lineas += _seccion_diagnostico_segundo_nivel(
        auditoria["diagnostico_segundo_nivel"]
    )
    lineas += ["## Recomendaciones", "", _tabla(_recomendaciones(auditoria))]
    Path(ruta_salida).write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return Path(ruta_salida)


def ejecutar_auditoria(
    ruta_excel="BOE-oposiciones.xlsx",
    ruta_informe="informe_auditoria_datos.md",
):
    auditoria = auditar_datos(ruta_excel)
    generar_informe_markdown(auditoria, ruta_informe)
    return auditoria


def _resumen(df):
    return {
        "Filas de Oposiciones": len(df),
        "Publicaciones BOE únicas": len(set(_serie(df, "Publicacion_ID")[_ids_validos(df)])),
        "Puestos únicos": _nunique_validos(df, "Puesto"),
        "Administraciones únicas": _nunique_validos(df, "Administración"),
        "Provincias únicas": _nunique_validos(df, "Provincia"),
        "Filas con Publicacion_ID válido": int(_ids_validos(df).sum()),
        "Filas legacy": _contar_igual(df, "Version_extractor", "legacy"),
        "Filas con versión actual": _contar_igual(df, "Version_extractor", VERSION_EXTRACTOR),
        "Filas sin Fecha_analisis": int(_mascara_ausente(df, "Fecha_analisis").sum()),
    }


def _calidad_columnas(df):
    filas = []
    total = len(df)
    for columna in COLUMNAS_CALIDAD:
        serie = df[columna] if columna in df else pd.Series(pd.NA, index=df.index)
        nulos = int(serie.isna().sum())
        texto = serie.astype("string").str.strip()
        vacias = int((texto == "").sum())
        guiones = int((texto == "--").sum())
        no_disponible = int(texto.str.casefold().eq("no disponible").sum())
        problematicos = nulos + vacias + guiones + no_disponible
        filas.append({
            "Columna": columna, "Nulos": nulos, "Vacíos": vacias,
            "--": guiones, "No disponible": no_disponible,
            "% problemáticos": round(100 * problematicos / total, 2) if total else 0.0,
        })
    return filas


def _auditar_geolocalizacion(df):
    lat = pd.to_numeric(_serie(df, "Latitud"), errors="coerce")
    lon = pd.to_numeric(_serie(df, "Longitud"), errors="coerce")
    hab = pd.to_numeric(_serie(df, "Habitantes"), errors="coerce")
    lat_aus = _mascara_ausente(df, "Latitud")
    lon_aus = _mascara_ausente(df, "Longitud")
    lat_no_num = ~lat_aus & lat.isna()
    lon_no_num = ~lon_aus & lon.isna()
    fuera = lat.notna() & ~lat.between(-90, 90) | lon.notna() & ~lon.between(-180, 180)
    hab_aus = _mascara_ausente(df, "Habitantes")
    problematica = (_mascara_ausente(df, "Municipio") | _mascara_ausente(df, "Provincia") |
                    lat_aus | lon_aus | lat_no_num | lon_no_num | fuera |
                    (~hab_aus & hab.isna()))
    casos = df.loc[problematica].copy()
    return {
        "Filas sin municipio": int(_mascara_ausente(df, "Municipio").sum()),
        "Filas sin provincia": int(_mascara_ausente(df, "Provincia").sum()),
        "Filas sin latitud": int(lat_aus.sum()), "Filas sin longitud": int(lon_aus.sum()),
        "Latitud sin longitud": int((~lat_aus & lon_aus).sum()),
        "Longitud sin latitud": int((lat_aus & ~lon_aus).sum()),
        "Coordenadas no numéricas": int((lat_no_num | lon_no_num).sum()),
        "Coordenadas fuera de rango": int(fuera.sum()),
        "Habitantes ausentes o no numéricos": int((hab_aus | hab.isna()).sum()),
        "Municipios con varias coordenadas": _grupos_multiples(df, "Municipio", ["Latitud", "Longitud"]),
        "Municipios con varias administraciones": _grupos_multiples(df, "Municipio", ["Administración"]),
        "casos_problematicos": _registros(casos, COLUMNAS_CASOS),
    }


def _auditar_valores(df, columna):
    valores = _valores_validos(_serie(df, columna))
    return {"frecuencias": _frecuencias(valores), "variantes": _variantes(valores)}


def _auditar_entidad(df, columna, puesto=False):
    valores = _valores_validos(_serie(df, columna))
    plazas = pd.to_numeric(_serie(df, "Num_plazas"), errors="coerce")
    temporal = pd.DataFrame({columna: _serie(df, columna), "Plazas": plazas})
    temporal = temporal[~_mascara_ausente(df, columna)]
    por_plazas = temporal.groupby(columna, dropna=True)["Plazas"].sum(min_count=1)
    normalizador = _clave_puesto if puesto else _clave_simple
    return {
        "top_registros": _frecuencias(valores, 30),
        "top_plazas": [
            {columna: str(indice), "Plazas": _numero_json(valor)}
            for indice, valor in por_plazas.sort_values(ascending=False).head(30).items()
        ],
        "variantes": _variantes(valores, normalizador),
    }


def _auditar_administraciones(df):
    datos = _auditar_entidad(df, "Administración")
    datos["varias_localizaciones"] = _grupos_multiples(
        df, "Administración", ["Provincia", "Municipio"]
    )
    datos["geolocalizaciones_inconsistentes"] = _grupos_multiples(
        df, "Administración", ["Latitud", "Longitud"]
    )
    return datos


def _auditar_fechas(oposiciones, publicaciones):
    fechas_boe = _serie(oposiciones, "Fecha_boe").map(_fecha_segura)
    analisis = pd.to_datetime(_serie(oposiciones, "Fecha_analisis"), errors="coerce")
    analisis_ausente = _mascara_ausente(oposiciones, "Fecha_analisis")
    futuras = fechas_boe.map(lambda valor: valor is not None and valor > date.today())
    inconsistencias = 0
    if {"Publicacion_ID", "Fecha_BOE"}.issubset(publicaciones.columns) and "Publicacion_ID" in oposiciones:
        mapa = publicaciones.drop_duplicates("Publicacion_ID", keep="last").set_index("Publicacion_ID")["Fecha_BOE"].map(_fecha_segura)
        for _, fila in oposiciones.iterrows():
            pid = fila.get("Publicacion_ID")
            if pid in mapa.index:
                fecha_opo, fecha_pub = _fecha_segura(fila.get("Fecha_boe")), mapa.loc[pid]
                inconsistencias += int(fecha_opo is not None and fecha_pub is not None and fecha_opo != fecha_pub)
    fecha_ultimo = pd.to_datetime(_serie(publicaciones, "Fecha_ultimo_analisis"), errors="coerce")
    ultimo_ausente = _mascara_ausente(publicaciones, "Fecha_ultimo_analisis")
    return {
        "Fecha_boe inválidas": int(fechas_boe.isna().sum()),
        "Fechas BOE futuras": int(futuras.sum()),
        "Fecha_analisis inválidas": int((~analisis_ausente & analisis.isna()).sum()),
        "Fecha_ultimo_analisis inválidas": int((~ultimo_ausente & fecha_ultimo.isna()).sum()),
        "Fechas inconsistentes Oposiciones/Publicaciones": inconsistencias,
    }


def _auditar_publicaciones(publicaciones, oposiciones):
    if publicaciones.empty:
        return {"Filas": 0, "Hoja ausente o vacía": True}
    ids = _serie(publicaciones, "Publicacion_ID")
    coincidencias = pd.to_numeric(_serie(publicaciones, "Coincidencias"), errors="coerce")
    filas_opo = Counter(_serie(oposiciones, "Publicacion_ID").dropna())
    clasificacion = Counter()
    sin_filas, sin_con_filas = 0, 0
    for _, fila in publicaciones.iterrows():
        pid, estado = fila.get("Publicacion_ID"), fila.get("Estado_analisis")
        declarado = pd.to_numeric(pd.Series([fila.get("Coincidencias")]), errors="coerce").iloc[0]
        reales = filas_opo.get(pid, 0)
        if estado == "con_coincidencias" and reales == 0:
            sin_filas += 1
        if estado == "sin_coincidencias" and reales > 0:
            sin_con_filas += 1
        if pd.isna(declarado) or declarado < 0 or (estado == "con_coincidencias" and reales == 0) or (estado == "sin_coincidencias" and reales > 0):
            clasificacion["revisar"] += 1
        elif int(declarado) == reales:
            clasificacion["consistente"] += 1
        elif declarado > 0 and reales > 0:
            clasificacion["diferencia explicable"] += 1
        else:
            clasificacion["revisar"] += 1
    return {
        "Filas": len(publicaciones),
        "Publicacion_ID duplicados": int(publicaciones.duplicated("Publicacion_ID", keep=False).sum()) if "Publicacion_ID" in publicaciones else len(publicaciones),
        "con_coincidencias sin Oposiciones": sin_filas,
        "sin_coincidencias con Oposiciones": sin_con_filas,
        "Coincidencias no numérico": int((~_mascara_ausente(publicaciones, "Coincidencias") & coincidencias.isna()).sum()),
        "Coincidencias negativo": int((coincidencias < 0).sum()),
        "Versiones realmente inválidas": _diagnosticar_versiones(publicaciones)["Valores realmente inválidos"],
        "Versiones legacy": _diagnosticar_versiones(publicaciones)["Legacy pendientes de reprocesamiento"],
        "Estados desconocidos": int((~_serie(publicaciones, "Estado_analisis").isin(["con_coincidencias", "sin_coincidencias"])).sum()),
        "Comparación Coincidencias/filas": dict(clasificacion),
        "Criterio": "consistente: igualdad; diferencia explicable: ambos positivos (posible deduplicación); revisar: valores inválidos o contradicción de estado.",
    }


def _auditar_cobertura(cobertura, publicaciones):
    if cobertura.empty:
        return {"Filas": 0, "Hoja ausente o vacía": True}
    numeros = pd.to_numeric(_serie(cobertura, "Numero_publicaciones"), errors="coerce")
    fechas = _serie(cobertura, "Fecha").map(_fecha_segura)
    publicaciones_por_fecha = {}
    for _, publicacion in publicaciones.iterrows():
        fecha = _fecha_segura(publicacion.get("Fecha_BOE"))
        publicacion_id = publicacion.get("Publicacion_ID")
        if fecha is not None and isinstance(publicacion_id, str) and PATRON_PUBLICACION_ID.fullmatch(publicacion_id):
            publicaciones_por_fecha.setdefault(fecha, set()).add(publicacion_id)
    discrepancias = 0
    for indice, fila in cobertura.iterrows():
        fecha, numero = fechas.loc[indice], numeros.loc[indice]
        if fecha is not None and pd.notna(numero) and len(publicaciones_por_fecha.get(fecha, set())) != int(numero):
            discrepancias += 1
    estados = _serie(cobertura, "Estado")
    return {
        "Filas": len(cobertura),
        "Fechas duplicadas": int(cobertura.duplicated("Fecha", keep=False).sum()) if "Fecha" in cobertura else len(cobertura),
        "Estados desconocidos": int((~estados.isin(["consultado", "sin_edicion", "error"])).sum()),
        "Versiones inválidas": int(_serie(cobertura, "Version_extractor").map(lambda x: _comparar_version_auditoria(x) is None).sum()),
        "Numero_publicaciones inválido": int((~_mascara_ausente(cobertura, "Numero_publicaciones") & (numeros.isna() | (numeros % 1 != 0) | (numeros < 0))).sum()),
        "sin_edicion distinto de cero": int(((estados == "sin_edicion") & numeros.ne(0)).sum()),
        "Fechas inválidas": int(fechas.isna().sum()),
        "Cobertura/Publicaciones no coinciden": discrepancias,
    }


def _auditar_busquedas(busquedas):
    codigos = _serie(busquedas, "Código").dropna().astype(str)
    ids, textos, no_asociables = [], [], 0
    for codigo in codigos:
        encontrado = PATRON_PUBLICACION_ID.search(codigo)
        if encontrado is None:
            no_asociables += 1
            continue
        ids.append(encontrado.group())
        sufijo = codigo.rsplit("_", 1)[-1] if "_" in codigo[encontrado.end():] else ""
        textos.append(sufijo.replace("+", " "))
    return {
        "Total": len(codigos), "Códigos únicos": int(codigos.nunique()),
        "Publicaciones únicas implícitas": len(set(ids)),
        "Textos de búsqueda distintos": len(set(textos)),
        "Distribución por texto": dict(Counter(textos).most_common()),
        "Códigos no asociables": no_asociables,
    }


def _auditar_errores(errores, publicaciones):
    tipos = _serie(errores, "Tipo de error").dropna().astype(str)
    enlaces = _serie(errores, "Enlace Web").dropna().astype(str)
    ids_procesados = set(_serie(publicaciones, "Publicacion_ID").dropna().astype(str))
    resueltos = sum(bool((pid := PATRON_PUBLICACION_ID.search(url)) and pid.group() in ids_procesados) for url in enlaces)
    repetidos = enlaces.value_counts()
    return {
        "Total": len(errores), "Tipos": dict(tipos.value_counts()),
        "Enlaces únicos": int(enlaces.nunique()),
        "Errores repetidos por enlace": dict(repetidos[repetidos > 1]),
        "Potencialmente resueltos": resueltos,
        "Sin evidencia de resolución": len(errores) - resueltos,
    }


def _auditar_duplicados(df):
    clave = [c for c in CLAVE_DEDUPLICACION if c in df]
    exactos = int(df.duplicated(keep=False).sum()) if len(df.columns) else 0
    por_clave = int(df.duplicated(clave, keep=False).sum()) if clave else 0
    pid_puesto = _contradicciones(df, ["Publicacion_ID", "Puesto"], [c for c in df if c not in {"Publicacion_ID", "Puesto"}])
    enlace = _contradicciones(df, ["Enlace"], ["Administración", "Sistema", "Turno", "Num_plazas"])
    return {
        "Filas duplicadas exactas": exactos,
        "Duplicados según clave actual": por_clave,
        "Publicacion_ID + Puesto con datos diferentes": pid_puesto,
        "Enlaces con valores contradictorios": enlace,
    }


def _diagnosticar_versiones(publicaciones):
    serie = _serie(publicaciones, "Version_extractor")
    total = len(serie)
    categorias = Counter()
    valores = Counter()
    invalidos = []
    version_actual = int(VERSION_EXTRACTOR)
    for valor in serie.tolist():
        if valor is None or pd.isna(valor):
            etiqueta, categoria = "<NULO>", "nulo"
        else:
            texto = str(valor).strip()
            etiqueta = texto if texto else "<VACÍO>"
            if not texto:
                categoria = "vacío"
            elif texto.casefold() == "legacy":
                categoria = "legacy"
            elif _comparar_version_auditoria(valor) is None:
                categoria = "realmente inválido"
                invalidos.append(texto)
            elif _version_entera(valor) > version_actual:
                categoria = "versión numérica futura"
            else:
                categoria = "versión numérica válida"
        categorias[categoria] += 1
        valores[(etiqueta, categoria)] += 1
    detalle = [
        {
            "Valor": valor,
            "Categoría": categoria,
            "Publicaciones": cantidad,
            "Porcentaje": round(100 * cantidad / total, 2) if total else 0.0,
        }
        for (valor, categoria), cantidad in valores.most_common()
    ]
    return {
        "Total publicaciones": total,
        "Legacy pendientes de reprocesamiento": categorias["legacy"],
        "Vacías": categorias["vacío"],
        "Nulas": categorias["nulo"],
        "Versiones numéricas válidas": categorias["versión numérica válida"],
        "Versiones numéricas futuras": categorias["versión numérica futura"],
        "Valores realmente inválidos": categorias["realmente inválido"],
        "detalle": detalle,
        "ejemplos_invalidos": sorted(set(invalidos))[:20],
    }


def _diagnosticar_publicacion_puesto(oposiciones):
    campos = [
        "Num_plazas", "Turno", "Sistema", "Escala", "Subescala", "Clase",
        "Administración", "Municipio", "Provincia",
    ]
    disponibles = [c for c in campos if c in oposiciones]
    if not {"Publicacion_ID", "Puesto"}.issubset(oposiciones.columns):
        return _diagnostico_grupos_vacio()
    columnas_diferentes = Counter()
    detalles, total, legitimos, revisar = [], 0, 0, 0
    for (pid, puesto), grupo in oposiciones.groupby(
        ["Publicacion_ID", "Puesto"], dropna=False, sort=False
    ):
        if len(grupo) < 2:
            continue
        diferencias = [
            columna for columna in disponibles
            if grupo[columna].map(_valor_comparable).nunique(dropna=False) > 1
        ]
        if not diferencias:
            continue
        total += 1
        columnas_diferentes.update(diferencias)
        sospechosas = set(diferencias) & {"Administración", "Municipio", "Provincia"}
        clasificacion = "REVISAR" if sospechosas else "LEGÍTIMO"
        legitimos += clasificacion == "LEGÍTIMO"
        revisar += clasificacion == "REVISAR"
        if clasificacion == "REVISAR":
            detalles.append({
                "Publicacion_ID": pid,
                "Puesto": puesto,
                "Columnas diferentes": ", ".join(diferencias),
                "Filas": _registros(grupo, ["Publicacion_ID", "Puesto"] + disponibles),
            })
    return {
        "Grupos totales": total,
        "LEGÍTIMO": legitimos,
        "REVISAR": revisar,
        "Columnas que provocan diferencias": dict(columnas_diferentes.most_common()),
        "detalle_revisar": detalles,
    }


def _diagnostico_grupos_vacio():
    return {
        "Grupos totales": 0, "LEGÍTIMO": 0, "REVISAR": 0,
        "Columnas que provocan diferencias": {}, "detalle_revisar": [],
    }


def _diagnosticar_multiconvocatorias(oposiciones):
    if "Enlace" not in oposiciones:
        return {
            "Enlaces analizados": 0, "NORMAL_MULTICONVOCATORIA": 0,
            "POSIBLE_INCONSISTENCIA": 0, "Falsos positivos de primera auditoría": 0,
            "detalle_posibles_inconsistencias": [],
        }
    normales, revisar, detalles, total = 0, 0, [], 0
    campos_primera_auditoria = ["Administración", "Sistema", "Turno", "Num_plazas"]
    for enlace, grupo in oposiciones.groupby("Enlace", dropna=False, sort=False):
        if len(grupo) < 2 or not any(
            c in grupo and grupo[c].map(_valor_comparable).nunique(dropna=False) > 1
            for c in campos_primera_auditoria
        ):
            continue
        total += 1
        metricas = {
            "Enlace": enlace,
            "Publicacion_ID": _primer_valor(grupo, "Publicacion_ID"),
            "Convocatorias": len(grupo.drop_duplicates(
                [c for c in CLAVE_DEDUPLICACION if c in grupo]
            )),
            "Puestos": _nunique_serie(grupo, "Puesto"),
            "Administraciones": _nunique_serie(grupo, "Administración"),
            "Turnos": _nunique_serie(grupo, "Turno"),
            "Sistemas": _nunique_serie(grupo, "Sistema"),
            "Números de plazas": _nunique_serie(grupo, "Num_plazas"),
            "Municipios": _nunique_serie(grupo, "Municipio"),
            "Provincias": _nunique_serie(grupo, "Provincia"),
        }
        posible = any(
            metricas[campo] > 1
            for campo in ("Administraciones", "Municipios", "Provincias")
        )
        if posible:
            revisar += 1
            detalles.append(metricas)
        else:
            normales += 1
    return {
        "Enlaces analizados": total,
        "NORMAL_MULTICONVOCATORIA": normales,
        "POSIBLE_INCONSISTENCIA": revisar,
        "Falsos positivos de primera auditoría": normales,
        "detalle_posibles_inconsistencias": detalles,
    }


def _diagnosticar_log_errores(errores, publicaciones, oposiciones, cobertura):
    detalles = []
    for _, error in errores.iterrows():
        url = str(error.get("Enlace Web", ""))
        publicacion = PATRON_PUBLICACION_ID.search(url)
        fecha_indice = _fecha_indice(url)
        estado = "NO_DETERMINABLE"
        evidencia = "No se reconoce una publicación ni un índice diario."
        if publicacion:
            pid = publicacion.group()
            filas = publicaciones[
                _serie(publicaciones, "Publicacion_ID") == pid
            ]
            if not filas.empty:
                ultima = filas.iloc[-1]
                version = _comparar_version_auditoria(ultima.get("Version_extractor"))
                estado_analisis = ultima.get("Estado_analisis")
                filas_opo = int((_serie(oposiciones, "Publicacion_ID") == pid).sum())
                correcto = version is not None and version >= 0 and (
                    estado_analisis == "sin_coincidencias"
                    or (estado_analisis == "con_coincidencias" and filas_opo > 0)
                )
                if correcto and _evidencia_posterior(
                    error.get("Fecha"), ultima.get("Fecha_ultimo_analisis")
                ):
                    estado = "RESUELTO"
                    evidencia = f"Publicaciones={estado_analisis}, versión={ultima.get('Version_extractor')}, filas Oposiciones={filas_opo}."
                else:
                    estado = "PENDIENTE"
                    evidencia = "La publicación no tiene evidencia posterior completa de análisis correcto."
            else:
                estado = "PENDIENTE"
                evidencia = "No existe en Publicaciones."
        elif fecha_indice is not None:
            filas = cobertura[
                _serie(cobertura, "Fecha").map(_fecha_segura) == fecha_indice
            ]
            if not filas.empty:
                ultima = filas.iloc[-1]
                estado_cobertura = ultima.get("Estado")
                compatible = _comparar_version_auditoria(ultima.get("Version_extractor"))
                if (
                    estado_cobertura in {"consultado", "sin_edicion"}
                    and compatible is not None and compatible >= 0
                    and _evidencia_posterior(
                        error.get("Fecha"), ultima.get("Fecha_ultima_consulta")
                    )
                ):
                    estado = "RESUELTO"
                    evidencia = f"Cobertura posterior: {estado_cobertura}."
                elif estado_cobertura == "error":
                    estado = "ERROR_DE_INDICE"
                    evidencia = "La cobertura continúa en estado error."
                else:
                    estado = "PENDIENTE"
                    evidencia = "La cobertura no demuestra una consulta correcta posterior."
            else:
                evidencia = "No existe cobertura para la fecha del índice."
        detalles.append({
            "Fecha error": error.get("Fecha", ""),
            "Tipo": error.get("Tipo de error", ""),
            "Enlace": url,
            "Clasificación": estado,
            "Evidencia": evidencia,
        })
    conteos = Counter(fila["Clasificación"] for fila in detalles)
    return {
        "Errores totales": len(detalles),
        "Enlaces únicos": int(_serie(errores, "Enlace Web").dropna().nunique()),
        "RESUELTO": conteos["RESUELTO"],
        "PENDIENTE": conteos["PENDIENTE"],
        "ERROR_DE_INDICE": conteos["ERROR_DE_INDICE"],
        "NO_DETERMINABLE": conteos["NO_DETERMINABLE"],
        "casos_pendientes": [
            fila for fila in detalles if fila["Clasificación"] != "RESUELTO"
        ],
        "detalle_completo": detalles,
    }


def _diagnosticar_geolocalizacion(oposiciones):
    sin_geo = (
        _mascara_ausente(oposiciones, "Municipio")
        | _mascara_ausente(oposiciones, "Provincia")
        | _mascara_ausente(oposiciones, "Latitud")
        | _mascara_ausente(oposiciones, "Longitud")
    )
    filas = oposiciones.loc[sin_geo].copy()
    if filas.empty:
        return {"Filas totales": 0, "resumen_por_tipo": [], "ayuntamientos": []}
    filas["Tipo_administración"] = _serie(filas, "Administración").map(
        _tipo_administracion
    )
    resumen = []
    for tipo, grupo in filas.groupby("Tipo_administración", sort=False):
        resumen.append({
            "Tipo": tipo,
            "Filas": len(grupo),
            "Publicaciones": _nunique_serie(grupo, "Publicacion_ID"),
            "Administraciones": _nunique_serie(grupo, "Administración"),
        })
    ayuntamientos = filas[filas["Tipo_administración"] == "Ayuntamiento"]
    return {
        "Filas totales": len(filas),
        "resumen_por_tipo": resumen,
        "ayuntamientos": _registros(
            ayuntamientos,
            ["Publicacion_ID", "Administración", "Puesto", "Municipio", "Provincia"],
        ),
    }


def _tipo_administracion(valor):
    texto = _clave_simple(valor)
    reglas = [
        ("Diputación Provincial", r"diputacion provincial"),
        ("Diputación Foral", r"diputacion foral"),
        ("Cabildo Insular", r"cabildo insular"),
        ("Consejo/Consell Insular", r"(?:consejo|consell) insular"),
        ("Mancomunidad/Mancomunitat", r"mancomuni(?:dad|tat)"),
        ("Consejo Comarcal", r"(?:consejo|consell) comarcal"),
        ("Ayuntamiento", r"ayuntamiento|ajuntament"),
        ("Administración estatal", r"ministerio|administracion general del estado|estado"),
    ]
    for tipo, patron in reglas:
        if re.search(patron, texto):
            return tipo
    return "Otros"


def _fecha_indice(url):
    coincidencia = re.search(r"/boe/dias/(\d{4})/(\d{2})/(\d{2})/index\.php", url)
    if not coincidencia:
        return None
    try:
        return date(*map(int, coincidencia.groups()))
    except ValueError:
        return None


def _evidencia_posterior(fecha_error, fecha_correcta):
    error = pd.to_datetime(pd.Series([fecha_error]), errors="coerce").iloc[0]
    correcta = pd.to_datetime(pd.Series([fecha_correcta]), errors="coerce").iloc[0]
    if pd.isna(correcta):
        return False
    return pd.isna(error) or correcta >= error


def _valor_comparable(valor):
    return "<NULO>" if valor is None or pd.isna(valor) else str(valor).strip()


def _version_entera(valor):
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        if pd.notna(valor) and float(valor).is_integer() and valor > 0:
            return int(valor)
        return None
    texto = str(valor).strip() if valor is not None else ""
    return int(texto) if re.fullmatch(r"[1-9]\d*", texto) else None


def _comparar_version_auditoria(valor):
    version = _version_entera(valor)
    return comparar_versiones(str(version)) if version is not None else None


def _primer_valor(df, columna):
    if columna not in df:
        return ""
    valores = df[columna].dropna()
    return valores.iloc[0] if not valores.empty else ""


def _nunique_serie(df, columna):
    return len(set(_valores_validos(_serie(df, columna))))


def _contradicciones(df, claves, valores):
    claves, valores = [c for c in claves if c in df], [c for c in valores if c in df]
    if not claves or not valores or df.empty:
        return 0
    return sum(any(grupo[c].nunique(dropna=False) > 1 for c in valores) for _, grupo in df.groupby(claves, dropna=False))


def _grupos_multiples(df, clave, valores):
    if clave not in df or df.empty:
        return 0
    validos = df[~_mascara_ausente(df, clave)]
    return sum(any(grupo[c].dropna().astype(str).nunique() > 1 for c in valores if c in grupo) for _, grupo in validos.groupby(clave))


def _variantes(valores, normalizador=None):
    normalizador = normalizador or _clave_simple
    grupos = {}
    for valor in set(valores):
        grupos.setdefault(normalizador(valor), []).append(valor)
    return [{"Clave": clave, "Variantes": " | ".join(sorted(grupo))} for clave, grupo in grupos.items() if len(grupo) > 1]


def _clave_simple(valor):
    texto = unicodedata.normalize("NFKD", str(valor)).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[\s\-]+", " ", texto).strip()


def _clave_puesto(valor):
    texto = re.sub(r"/a\b", "", str(valor), flags=re.IGNORECASE)
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def _fecha_segura(valor):
    if valor is None or pd.isna(valor):
        return None
    if isinstance(valor, (datetime, pd.Timestamp)):
        return valor.date()
    texto = str(valor).strip()
    for formato in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            pass
    try:
        return convertir_fecha(texto).date()
    except (TypeError, ValueError, AttributeError):
        return None


def _ids_validos(df):
    return _serie(df, "Publicacion_ID").map(lambda x: isinstance(x, str) and bool(PATRON_PUBLICACION_ID.fullmatch(x)))


def _mascara_ausente(df, columna):
    serie = _serie(df, columna)
    texto = serie.astype("string").str.strip().str.casefold()
    return serie.isna() | texto.isin(MARCADORES_AUSENTES)


def _serie(df, columna):
    return df[columna] if columna in df else pd.Series(pd.NA, index=df.index, dtype="object")


def _valores_validos(serie):
    texto = serie.dropna().astype(str).str.strip()
    return texto[~texto.str.casefold().isin(MARCADORES_AUSENTES)].tolist()


def _frecuencias(valores, limite=None):
    datos = Counter(valores).most_common(limite)
    return [{"Valor": valor, "Frecuencia": frecuencia} for valor, frecuencia in datos]


def _nunique_validos(df, columna):
    return len(set(_valores_validos(_serie(df, columna))))


def _contar_igual(df, columna, valor):
    return int(_serie(df, columna).astype("string").str.strip().eq(valor).sum())


def _registros(df, columnas):
    disponibles = [c for c in columnas if c in df]
    return df[disponibles].fillna("").to_dict(orient="records")


def _numero_json(valor):
    return None if pd.isna(valor) else float(valor)


def _incidencias(a):
    return {
        "Geolocalización": len(a["geolocalizacion"]["casos_problematicos"]),
        "Fechas": sum(v for v in a["fechas"].values() if isinstance(v, int)),
        "Publicaciones a revisar": a["publicaciones"].get("Comparación Coincidencias/filas", {}).get("revisar", 0),
        "Cobertura inconsistente": a["cobertura"].get("Cobertura/Publicaciones no coinciden", 0),
        "Duplicados por clave": a["duplicados"]["Duplicados según clave actual"],
    }


def _tabla(filas):
    if not filas:
        return "Sin casos."
    if isinstance(filas, dict):
        filas = [{"Elemento": k, "Valor": v} for k, v in filas.items()]
    columnas = list(filas[0])
    salida = ["| " + " | ".join(columnas) + " |", "|" + "|".join("---" for _ in columnas) + "|"]
    for fila in filas:
        salida.append("| " + " | ".join(_md(fila.get(c, "")) for c in columnas) + " |")
    return "\n".join(salida)


def _tabla_dict(datos):
    return _tabla([{"Métrica": k, "Valor": v} for k, v in datos.items()])


def _render_bloque(datos):
    escalares, complejos = {}, {}
    for clave, valor in datos.items():
        (complejos if isinstance(valor, (dict, list)) else escalares)[clave] = valor
    partes = [_tabla_dict(escalares)] if escalares else []
    for clave, valor in complejos.items():
        partes += [f"### {clave}", "", _tabla(valor)]
    return "\n\n".join(partes) if partes else "Sin datos."


def _seccion_entidad(titulo, datos):
    return [f"## {titulo}", "", "### Top 30 por registros", "", _tabla(datos["top_registros"]),
            "", "### Top 30 por plazas", "", _tabla(datos["top_plazas"]),
            "", "### Posibles variantes", "", _tabla(datos["variantes"]), ""] + (
            ["### Inconsistencias geográficas", "", _tabla_dict({k: v for k, v in datos.items() if k not in {"top_registros", "top_plazas", "variantes"}}), ""] if titulo == "Administraciones" else []
        )


def _seccion_diagnostico_segundo_nivel(diagnostico):
    versiones = diagnostico["versiones"]
    duplicadas = diagnostico["convocatorias_duplicadas"]
    multi = diagnostico["multiconvocatorias"]
    errores = diagnostico["estado_errores"]
    geo = diagnostico["geolocalizacion_por_tipo"]
    return [
        "## Diagnóstico de segundo nivel", "",
        "### Versiones de Publicaciones", "",
        _tabla_dict({k: v for k, v in versiones.items() if k not in {"detalle", "ejemplos_invalidos"}}),
        "", "#### Distribución exacta", "", _tabla(versiones["detalle"]),
        "", "#### Ejemplos realmente inválidos", "", _tabla(
            [{"Valor": valor} for valor in versiones["ejemplos_invalidos"]]
        ), "",
        "### Convocatorias aparentemente duplicadas", "",
        _tabla_dict({k: v for k, v in duplicadas.items() if k != "detalle_revisar"}),
        "", "#### Casos REVISAR", "", _tabla(duplicadas["detalle_revisar"]), "",
        "### Publicaciones multiconvocatoria", "",
        _tabla_dict({k: v for k, v in multi.items() if k != "detalle_posibles_inconsistencias"}),
        "", "#### Posibles inconsistencias", "",
        _tabla(multi["detalle_posibles_inconsistencias"]), "",
        "### Estado real del Log de errores", "",
        _tabla_dict({k: v for k, v in errores.items() if k not in {"casos_pendientes", "detalle_completo"}}),
        "", "#### Casos pendientes", "", _tabla(errores["casos_pendientes"]), "",
        "### Geolocalización pendiente por tipo de administración", "",
        _tabla_dict({"Filas totales": geo["Filas totales"]}), "",
        _tabla(geo["resumen_por_tipo"]), "", "#### Ayuntamientos", "",
        _tabla(geo["ayuntamientos"]), "",
    ]


def _recomendaciones(auditoria):
    diagnostico = auditoria["diagnostico_segundo_nivel"]
    versiones = diagnostico["versiones"]
    duplicadas = diagnostico["convocatorias_duplicadas"]
    multi = diagnostico["multiconvocatorias"]
    errores = diagnostico["estado_errores"]
    geo = diagnostico["geolocalizacion_por_tipo"]
    recomendaciones = []
    if versiones["Legacy pendientes de reprocesamiento"]:
        recomendaciones.append({
            "Clasificación": "HISTÓRICO",
            "Hallazgo": f'{versiones["Legacy pendientes de reprocesamiento"]} publicaciones legacy',
            "Recomendación": "Mantenerlas diferenciadas y planificar su reprocesamiento controlado; no tratarlas como datos corruptos.",
        })
    if versiones["Valores realmente inválidos"]:
        recomendaciones.append({
            "Clasificación": "ERROR REAL",
            "Hallazgo": f'{versiones["Valores realmente inválidos"]} versiones realmente inválidas',
            "Recomendación": "Investigar su origen antes de corregir los registros afectados.",
        })
    if duplicadas["LEGÍTIMO"]:
        recomendaciones.append({
            "Clasificación": "FALSO POSITIVO DE AUDITORÍA",
            "Hallazgo": f'{duplicadas["LEGÍTIMO"]} grupos Publicacion_ID + Puesto legítimos',
            "Recomendación": "No considerar diferencias de turno, sistema, escala, clase o plazas como duplicados por sí solas.",
        })
    if duplicadas["REVISAR"]:
        recomendaciones.append({
            "Clasificación": "GEOGRAFÍA",
            "Hallazgo": f'{duplicadas["REVISAR"]} grupos con administración o geografía variable',
            "Recomendación": "Revisar manualmente únicamente los casos detallados.",
        })
    if multi["NORMAL_MULTICONVOCATORIA"]:
        recomendaciones.append({
            "Clasificación": "FALSO POSITIVO DE AUDITORÍA",
            "Hallazgo": f'{multi["NORMAL_MULTICONVOCATORIA"]} publicaciones multiconvocatoria normales',
            "Recomendación": "Excluirlas de futuras reglas genéricas de contradicción por enlace.",
        })
    if geo["Filas totales"]:
        recomendaciones.append({
            "Clasificación": "GEOGRAFÍA",
            "Hallazgo": f'{geo["Filas totales"]} filas sin geolocalización completa',
            "Recomendación": "Priorizar los ayuntamientos; mantener separadas las administraciones supramunicipales.",
        })
    pendientes = errores["PENDIENTE"] + errores["ERROR_DE_INDICE"]
    if pendientes:
        recomendaciones.append({
            "Clasificación": "HISTÓRICO",
            "Hallazgo": f"{pendientes} errores todavía pendientes",
            "Recomendación": "Conservar el log y revisar los casos sin evidencia posterior de resolución.",
        })
    if not recomendaciones:
        recomendaciones.append({
            "Clasificación": "NORMALIZACIÓN",
            "Hallazgo": "No se detectaron incidencias de segundo nivel",
            "Recomendación": "No realizar cambios automáticos.",
        })
    return recomendaciones


def _md(valor):
    if isinstance(valor, (dict, list)):
        valor = str(valor)
    return str(valor).replace("|", "\\|").replace("\n", " ")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audita BOE-oposiciones.xlsx sin modificarlo")
    parser.add_argument("--excel", default="BOE-oposiciones.xlsx")
    argumentos = parser.parse_args(argv)
    resultado = ejecutar_auditoria(argumentos.excel)
    print("Auditoría completada. Informe: informe_auditoria_datos.md")
    print(_tabla_dict(resultado["resumen"]))
    print("\nIncidencias principales:")
    print(_tabla_dict(_incidencias(resultado)))


if __name__ == "__main__":
    main()
