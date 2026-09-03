"""Consultas de lectura para los consumidores SQLite de BOE."""
from pathlib import Path
import sqlite3
from math import ceil
from datetime import date, datetime, timedelta

import pandas as pd

import base_datos
from cobertura import (
    ESTADO_INCOHERENCIA_HISTORICA_VERIFICADA,
    ESTADOS_VALIDOS,
    crear_verificador_cobertura_indice,
)


class ErrorConsultaSQLite(RuntimeError):
    """La base productiva no está disponible para consultas."""


COLUMNAS_ESTADISTICAS = ["Num_plazas", "Puesto", "Puesto_normalizado", "Administración", "Provincia", "Municipio", "Ambito", "Sistema", "Turno", "Fecha_boe"]
COLUMNAS_MAPA = ["Num_plazas", "Puesto", "Administración", "Sistema", "Fecha_boe_original", "Enlace", "Latitud", "Longitud", "Habitantes", "Municipio", "Provincia"]

_ORDEN_BUSQUEDA = {
    "fecha_desc": "fecha_boe DESC, oposicion_id DESC",
    "fecha_asc": "fecha_boe ASC, oposicion_id ASC",
    "puesto_asc": "puesto COLLATE NOCASE ASC, oposicion_id ASC",
    "administracion_asc": "administracion COLLATE NOCASE ASC, oposicion_id ASC",
    "plazas_desc": "num_plazas DESC, oposicion_id DESC",
}
_TAMANO_PAGINA_MAXIMO = 100
FECHA_INICIO_COBERTURA = date(2004, 1, 1)


def _fecha_iso(valor):
    if isinstance(valor, date):
        return valor
    return datetime.strptime(str(valor), "%Y-%m-%d").date()


def _clasificador_cobertura(ruta_bd):
    """Construye el clasificador de cobertura efectiva del índice BOE."""
    conexion = _conexion(ruta_bd)
    try:
        cobertura = pd.read_sql_query(
            "SELECT fecha AS Fecha, estado AS Estado, version_extractor AS Version_extractor, "
            "fecha_ultima_consulta AS Fecha_ultima_consulta, numero_publicaciones AS Numero_publicaciones FROM cobertura",
            conexion,
        )
        publicaciones = pd.read_sql_query(
            "SELECT publicacion_id AS Publicacion_ID, fecha_boe AS Fecha_BOE FROM publicaciones",
            conexion,
        )
    finally:
        conexion.close()

    reutilizable = crear_verificador_cobertura_indice(cobertura, publicaciones)
    publicaciones_por_fecha = publicaciones.groupby("Fecha_BOE")["Publicacion_ID"].size().to_dict()
    filas = {
        fila["Fecha"]: {**fila, "Publicaciones_SQLite": int(publicaciones_por_fecha.get(fila["Fecha"], 0))}
        for fila in cobertura.to_dict(orient="records")
    }

    def clasificar(fecha):
        hoy = date.today()
        if fecha > hoy:
            return {"estado_visual": "FUTURO", "cubierto": False, "motivo": "Fecha futura", "fila": None}
        fila = filas.get(fecha.isoformat())
        if fila is None:
            return {"estado_visual": "PENDIENTE", "cubierto": False, "motivo": "Cobertura inexistente", "fila": None}
        estado = fila["Estado"]
        if estado == ESTADO_INCOHERENCIA_HISTORICA_VERIFICADA:
            return {
                "estado_visual": "INCOHERENCIA_VERIFICADA", "cubierto": True,
                "motivo": "Incoherencia histórica verificada. El índice BOE actual no contiene las publicaciones históricas conservadas en SQLite. No requiere nueva consulta automática.",
                "fila": fila,
            }
        if estado not in ESTADOS_VALIDOS:
            return {"estado_visual": "NO_REUTILIZABLE", "cubierto": False, "motivo": "Estado no reutilizable", "fila": fila}
        if not reutilizable(fecha.isoformat()):
            return {"estado_visual": "NO_REUTILIZABLE", "cubierto": False, "motivo": "Cobertura incompleta o no verificable", "fila": fila}
        return {"estado_visual": "CONSULTADO" if estado == "consultado" else "SIN_EDICION", "cubierto": True, "motivo": None, "fila": fila}
    return clasificar


def resumen_cobertura(ruta_bd, *, hoy=None):
    hoy = hoy or date.today()
    clasificar = _clasificador_cobertura(ruta_bd)
    contador = {clave: 0 for clave in ("CONSULTADO", "SIN_EDICION", "INCOHERENCIA_VERIFICADA", "PENDIENTE", "NO_REUTILIZABLE", "FUTURO")}
    actual = FECHA_INICIO_COBERTURA
    while actual <= hoy:
        contador[clasificar(actual)["estado_visual"]] += 1
        actual += timedelta(days=1)
    total = sum(contador.values()) - contador["FUTURO"]
    cubiertos = contador["CONSULTADO"] + contador["SIN_EDICION"] + contador["INCOHERENCIA_VERIFICADA"]
    conexion = _conexion(ruta_bd)
    try:
        ultima = conexion.execute("SELECT MAX(fecha_ultima_consulta) FROM cobertura").fetchone()[0]
    finally:
        conexion.close()
    return {**contador, "fecha_inicio": FECHA_INICIO_COBERTURA.isoformat(), "fecha_fin": hoy.isoformat(),
            "dias_totales": total, "dias_cubiertos": cubiertos,
            "dias_pendientes": total - cubiertos, "porcentaje": round(100 * cubiertos / total, 2) if total else 100,
            "ultima_consulta": ultima}


def cobertura_mes(ruta_bd, *, anio, mes):
    inicio = date(int(anio), int(mes), 1)
    siguiente = date(inicio.year + (inicio.month == 12), 1 if inicio.month == 12 else inicio.month + 1, 1)
    clasificar = _clasificador_cobertura(ruta_bd)
    dias, actual = [], inicio
    while actual < siguiente:
        resultado = clasificar(actual)
        fila = resultado.pop("fila")
        dias.append({"fecha": actual.isoformat(), **resultado,
                     "estado": fila["Estado"] if fila else None,
                     "version_extractor": fila["Version_extractor"] if fila else None,
                     "fecha_ultima_consulta": fila["Fecha_ultima_consulta"] if fila else None,
                     "numero_publicaciones": fila["Numero_publicaciones"] if fila else None,
                     "publicaciones_sqlite": fila.get("Publicaciones_SQLite") if fila else None})
        actual += timedelta(days=1)
    return {"anio": inicio.year, "mes": inicio.month, "dias": dias}


def detalle_cobertura_dia(ruta_bd, *, fecha):
    fecha = _fecha_iso(fecha)
    for dia in cobertura_mes(ruta_bd, anio=fecha.year, mes=fecha.month)["dias"]:
        if dia["fecha"] == fecha.isoformat():
            return dia
    raise ValueError("Fecha no válida")


def _conexion(ruta_bd):
    try:
        base_datos.validar_base_principal(ruta_bd)
        return base_datos.conectar(ruta_bd, readonly=True)
    except (OSError, sqlite3.Error, base_datos.EspejoSQLiteError) as error:
        raise ErrorConsultaSQLite(f"SQLite no está disponible: {ruta_bd}") from error


def _filtros(desde=None, hasta=None, provincia=None, municipio=None, administracion=None,
             puesto=None, sistema=None, turno=None, ambito=None):
    clausulas, parametros = [], []
    for columna, valor, operador in (("fecha_boe", desde, ">="), ("fecha_boe", hasta, "<="),
                                     ("provincia", provincia, "="), ("municipio", municipio, "="),
                                     ("administracion", administracion, "="), ("ambito", ambito, "="), ("sistema", sistema, "="),
                                     ("turno", turno, "=")):
        if valor:
            clausulas.append(f"{columna} {operador} ?"); parametros.append(valor)
    if puesto:
        for palabra in str(puesto).split():
            clausulas.append("lower(puesto) LIKE lower(?)"); parametros.append(f"%{palabra}%")
    return (" WHERE " + " AND ".join(clausulas) if clausulas else ""), parametros


def oposiciones(ruta_bd="datos/boe.db", *, columnas=COLUMNAS_ESTADISTICAS, **filtros):
    """Devuelve solo las columnas y filas solicitadas, en una conexión read-only."""
    mapa = {"Num_plazas": "num_plazas", "Puesto": "puesto",
            "Puesto_normalizado": "COALESCE(puesto_normalizado, puesto)", "Administración": "COALESCE(administracion_normalizada, administracion)",
            "Provincia": "provincia", "Municipio": "municipio", "Sistema": "sistema", "Turno": "turno",
            "Fecha_boe": "fecha_boe", "Fecha_boe_original": "fecha_boe_original",
            "Enlace": "enlace", "Latitud": "latitud",
            "Longitud": "longitud", "Habitantes": "habitantes", "Ambito": "ambito"}
    try:
        seleccion = ",".join(f"{mapa[c]} AS '{c}'" for c in columnas)
    except KeyError as error:
        raise ValueError(f"Columna de consulta no admitida: {error.args[0]}") from error
    where, parametros = _filtros(**filtros)
    conexion = _conexion(ruta_bd)
    try:
        return pd.read_sql_query(f"SELECT {seleccion} FROM oposiciones{where} ORDER BY fecha_boe,oposicion_id", conexion, params=parametros)
    finally:
        conexion.close()


def opciones_filtros(ruta_bd="datos/boe.db"):
    conexion = _conexion(ruta_bd)
    try:
        resultado = {}
        for clave, columna in (("provincias", "provincia"), ("ambitos", "ambito"), ("sistemas", "sistema"), ("turnos", "turno")):
            filas = conexion.execute(f"SELECT DISTINCT {columna} FROM oposiciones WHERE {columna} IS NOT NULL AND trim({columna}) NOT IN ('', '--', 'no disponible') ORDER BY {columna} COLLATE NOCASE").fetchall()
            resultado[clave] = [fila[0] for fila in filas]
        return resultado
    finally:
        conexion.close()


def _valores_distintos(conexion, columna, *, where="", parametros=()):
    """Valores visibles de un campo de oposiciones, sin ausencias técnicas."""
    return [fila[0] for fila in conexion.execute(
        f"SELECT DISTINCT {columna} FROM oposiciones "
        f"WHERE {columna} IS NOT NULL AND trim({columna}) <> '' {where} "
        f"ORDER BY {columna} COLLATE NOCASE", parametros
    )]


def opciones_busqueda(ruta_bd="datos/boe.db", *, comunidad_autonoma=None, provincia=None, municipio=None):
    """Opciones de filtros del buscador, obtenidas siempre de SQLite.

    Las provincias y municipios se limitan al territorio recibido. Las ciudades
    autónomas quedan disponibles por comunidad aunque no tengan provincia.
    """
    conexion = _conexion(ruta_bd)
    try:
        resultado = {
            clave: _valores_distintos(conexion, columna)
            for clave, columna in (
                ("ambitos", "ambito"), ("tipos_entidad", "tipo_entidad"),
                ("comunidades", "comunidad_autonoma"), ("provincias", "provincia"),
                ("sistemas", "sistema"),
                ("turnos", "turno"), ("escalas", "escala"),
                ("subescalas", "subescala"), ("clases", "clase"),
            )
        }
        # Administración tiene miles de valores distintos: el formulario usa
        # texto libre y no los transporta todos al HTML.
        resultado["administraciones"] = []
        # También se evita enviar miles de municipios sin contexto territorial.
        resultado["municipios"] = []
        if comunidad_autonoma:
            resultado["provincias"] = _valores_distintos(
                conexion, "provincia", where="AND comunidad_autonoma = ?", parametros=(comunidad_autonoma,)
            )
        if provincia:
            resultado["municipios"] = _valores_distintos(
                conexion, "municipio", where="AND provincia = ?", parametros=(provincia,)
            )
        elif comunidad_autonoma:
            resultado["municipios"] = _valores_distintos(
                conexion, "municipio", where="AND comunidad_autonoma = ?", parametros=(comunidad_autonoma,)
            )
        elif municipio:
            resultado["municipios"] = _valores_distintos(
                conexion, "municipio", where="AND municipio = ?", parametros=(municipio,)
            )
        return resultado
    finally:
        conexion.close()


def _terminos_parciales(texto):
    return [termino for termino in str(texto or "").strip().split() if termino]


def buscar_municipios(ruta_bd="datos/boe.db", texto=None, *, provincia=None,
                      comunidad_autonoma=None, limite=12):
    """Sugerencias municipales reales, acotadas y compatibles con los filtros."""
    terminos = _terminos_parciales(texto)
    if len(" ".join(terminos)) < 2:
        return []
    try:
        limite = min(15, max(1, int(limite)))
    except (TypeError, ValueError) as error:
        raise ValueError("limite debe ser un entero positivo") from error
    clausulas = ["municipio IS NOT NULL", "trim(municipio) <> ''"]
    parametros = []
    for termino in terminos:
        clausulas.append("lower(municipio) LIKE lower(?)")
        parametros.append(f"%{termino}%")
    for valor, columna in ((provincia, "provincia"), (comunidad_autonoma, "comunidad_autonoma")):
        if valor:
            clausulas.append(f"{columna} = ?")
            parametros.append(valor)
    conexion = _conexion(ruta_bd)
    try:
        filas = conexion.execute(
            """SELECT municipio, provincia, MAX(comunidad_autonoma) AS comunidad_autonoma
               FROM oposiciones WHERE """ + " AND ".join(clausulas) +
            " GROUP BY municipio, provincia "
            "ORDER BY CASE WHEN lower(municipio) LIKE lower(?) THEN 0 ELSE 1 END, "
            "municipio COLLATE NOCASE, provincia COLLATE NOCASE LIMIT ?",
            [*parametros, f"{terminos[0]}%", limite],
        ).fetchall()
        return [{"municipio": fila[0], "provincia": fila[1], "comunidad_autonoma": fila[2]} for fila in filas]
    finally:
        conexion.close()


def buscar_sugerencias_puesto(ruta_bd="datos/boe.db", texto=None, *, limite=12):
    """Sugerencias legibles de puesto basadas en los valores existentes."""
    terminos = _terminos_parciales(texto)
    if len(" ".join(terminos)) < 2:
        return []
    try:
        limite = min(15, max(1, int(limite)))
    except (TypeError, ValueError) as error:
        raise ValueError("limite debe ser un entero positivo") from error
    clausulas, parametros = [], []
    for termino in terminos:
        clausulas.append("(lower(puesto) LIKE lower(?) OR lower(COALESCE(puesto_normalizado,'')) LIKE lower(?))")
        parametros.extend((f"%{termino}%", f"%{termino}%"))
    conexion = _conexion(ruta_bd)
    try:
        filas = conexion.execute(
            """SELECT COALESCE(NULLIF(puesto_normalizado, ''), puesto) AS puesto_visible
               FROM oposiciones WHERE """ + " AND ".join(clausulas) +
            " GROUP BY puesto_visible ORDER BY CASE WHEN lower(puesto_visible) LIKE lower(?) THEN 0 ELSE 1 END, "
            "puesto_visible COLLATE NOCASE LIMIT ?",
            [*parametros, f"{terminos[0]}%", limite],
        ).fetchall()
        return [fila[0] for fila in filas]
    finally:
        conexion.close()


def obtener_oposicion(ruta_bd="datos/boe.db", oposicion_id=None):
    """Devuelve una oposición concreta para la ficha web o ``None`` si no existe."""
    try:
        oposicion_id = int(oposicion_id)
    except (TypeError, ValueError):
        return None
    conexion = _conexion(ruta_bd)
    try:
        cursor = conexion.execute(
            """SELECT oposicion_id,num_plazas,puesto,puesto_normalizado,administracion,
                      administracion_normalizada,ambito,tipo_entidad,comunidad_autonoma,
                      provincia,municipio,sistema,turno,escala,subescala,clase,fecha_boe,
                      fecha_boe_original,enlace,publicacion,confianza_geografica,
                      evidencia_geografica,version_extractor,version_resolutor,latitud,
                      longitud,habitantes,municipio_codigo_ine
               FROM oposiciones WHERE oposicion_id = ?""", (oposicion_id,)
        )
        fila = cursor.fetchone()
        if fila is None:
            return None
        columnas = [columna[0] for columna in cursor.description]
        return dict(zip(columnas, fila))
    finally:
        conexion.close()


def buscar_oposiciones(
    ruta_bd="datos/boe.db", *, texto=None, fecha_desde=None, fecha_hasta=None,
    administracion=None, ambito=None, comunidad_autonoma=None, provincia=None,
    municipio=None, municipio_exacto=None, municipio_provincia_exacto=None,
    tipo_entidad=None, sistema=None, turno=None, escala=None,
    subescala=None, clase=None, pagina=1, tamano_pagina=25, orden="fecha_desc",
):
    """Busca oposiciones desde SQLite con filtros exactos y paginación segura.

    La función devuelve datos neutros para que terminal y web compartan la
    misma consulta sin incorporar lógica de presentación.
    """
    if orden not in _ORDEN_BUSQUEDA:
        raise ValueError(f"Orden no permitido: {orden}")
    try:
        pagina = max(1, int(pagina))
        tamano_pagina = min(_TAMANO_PAGINA_MAXIMO, max(1, int(tamano_pagina)))
    except (TypeError, ValueError) as error:
        raise ValueError("pagina y tamano_pagina deben ser enteros positivos") from error

    clausulas, parametros = [], []
    for valor, columna, operador in (
        (fecha_desde, "fecha_boe", ">="), (fecha_hasta, "fecha_boe", "<="),
        (administracion, "administracion", "="), (ambito, "ambito", "="),
        (comunidad_autonoma, "comunidad_autonoma", "="), (provincia, "provincia", "="),
        (municipio_exacto, "municipio", "="), (municipio_provincia_exacto, "provincia", "="),
        (tipo_entidad, "tipo_entidad", "="),
        (sistema, "sistema", "="), (turno, "turno", "="), (escala, "escala", "="),
        (subescala, "subescala", "="), (clase, "clase", "="),
    ):
        if valor:
            clausulas.append(f"{columna} {operador} ?")
            parametros.append(valor)
    if municipio and not municipio_exacto:
        for termino in _terminos_parciales(municipio):
            clausulas.append("lower(municipio) LIKE lower(?)")
            parametros.append(f"%{termino}%")
    if texto:
        for termino in _terminos_parciales(texto):
            clausulas.append("(lower(puesto) LIKE lower(?) OR lower(COALESCE(puesto_normalizado,'')) LIKE lower(?))")
            parametros.extend((f"%{termino}%", f"%{termino}%"))

    where = " WHERE " + " AND ".join(clausulas) if clausulas else ""
    seleccion = """oposicion_id,fecha_boe,puesto,puesto_normalizado,num_plazas,
        administracion,administracion_normalizada,ambito,tipo_entidad,
        comunidad_autonoma,provincia,municipio,sistema,turno,escala,subescala,
        clase,enlace,publicacion,confianza_geografica,evidencia_geografica"""
    conexion = _conexion(ruta_bd)
    try:
        total = conexion.execute(f"SELECT count(*) FROM oposiciones{where}", parametros).fetchone()[0]
        total_paginas = ceil(total / tamano_pagina) if total else 0
        if total_paginas:
            pagina = min(pagina, total_paginas)
        offset = (pagina - 1) * tamano_pagina
        filas = conexion.execute(
            f"SELECT {seleccion} FROM oposiciones{where} ORDER BY {_ORDEN_BUSQUEDA[orden]} LIMIT ? OFFSET ?",
            [*parametros, tamano_pagina, offset],
        ).fetchall()
    finally:
        conexion.close()
    columnas = [x.strip() for x in seleccion.replace("\n", " ").split(",")]
    return {
        "filas": [dict(zip(columnas, fila)) for fila in filas],
        "total": total, "pagina": pagina, "tamano_pagina": tamano_pagina,
        "total_paginas": total_paginas,
        "orden": orden,
    }


def metadata(ruta_bd="datos/boe.db"):
    conexion = _conexion(ruta_bd)
    try:
        return dict(conexion.execute("SELECT clave,valor FROM metadata"))
    finally:
        conexion.close()
