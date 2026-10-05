"""Consultas de lectura para los consumidores SQLite de BOE."""
from pathlib import Path
import sqlite3
import calendar
import re
from math import ceil
from datetime import date, datetime, timedelta

import pandas as pd

_OPCIONES_FILTROS_CACHE = {}
_OPCIONES_BUSQUEDA_CACHE = {}
_OPCIONES_INHABILES_CACHE = {}
_COBERTURA_DATOS_CACHE = {}
_VALIDACION_BASE_CACHE = {}

import base_datos
from tipo_personal import TIPOS_PERSONAL
from cobertura import (
    ESTADO_INCOHERENCIA_HISTORICA_VERIFICADA,
    ESTADOS_VALIDOS,
    crear_verificador_cobertura_indice,
)


class ErrorConsultaSQLite(RuntimeError):
    """La base productiva no está disponible para consultas."""


COLUMNAS_ESTADISTICAS = ["Num_plazas", "Puesto", "Puesto_normalizado", "Administración", "Comunidad_autonoma", "Provincia", "Municipio", "Ambito", "Sistema", "Turno", "Tipo_personal", "Fecha_boe"]
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
_PATRON_ENLACE_XML_BOE = re.compile(r"/diario_boe/xml\.php(?=\?)", re.IGNORECASE)
_PATRON_PUBLICACION_ID = re.compile(r"BOE-[A-Z]-\d{4}-\d+")
_PATRON_FECHA_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def _enlace_boe_html(enlace, publicacion_id=None):
    """Devuelve el enlace HTML de una publicación aunque el histórico guardase XML."""
    texto = str(enlace or "").strip()
    if texto:
        return _PATRON_ENLACE_XML_BOE.sub("/diario_boe/txt.php", texto)
    if publicacion_id and re.fullmatch(r"BOE-[A-Z]-\d{4}-\d+", str(publicacion_id)):
        return f"https://www.boe.es/diario_boe/txt.php?id={publicacion_id}"
    return texto

_FIESTAS_FIJAS = {
    (1, 1): "Año Nuevo", (1, 6): "Epifanía del Señor", (5, 1): "Fiesta del Trabajo",
    (8, 15): "Asunción de la Virgen", (10, 12): "Fiesta Nacional de España",
    (11, 1): "Todos los Santos", (12, 6): "Día de la Constitución Española",
    (12, 8): "Inmaculada Concepción", (12, 25): "Navidad", (12, 26): "San Esteban",
}


def festividad_dia_inhabil(fecha, nombre=""):
    """Obtiene una denominación de fiesta útil incluso en calendarios históricos."""
    fecha = _fecha_iso(fecha)
    texto = " ".join(str(nombre or "").replace("\xa0", " ").split())
    meses = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre")
    patron_fecha = rf"\b{fecha.day}\s+de\s+{meses[fecha.month - 1]}\b.{{0,140}}?(?:festividad|fiesta) de\s+([^.;:»]+)"
    coincidencia = re.search(patron_fecha, texto, re.IGNORECASE)
    if coincidencia:
        return coincidencia.group(1).strip(" ,")
    # El extractor histórico puede conservar párrafos completos del BOE. Sólo
    # usamos una mención textual cuando parece pertenecer a una denominación
    # concreta y no a una nota normativa extensa.
    if len(texto) <= 240:
        coincidencia = re.search(r"(?:festividad|fiesta) de\s+([^.;:»]+)", texto, re.IGNORECASE)
        if coincidencia:
            return coincidencia.group(1).strip(" ,")
    fija = _FIESTAS_FIJAS.get((fecha.month, fecha.day))
    if fija:
        return fija
    # Cálculo gregoriano de Pascua para denominar las fiestas móviles más
    # habituales en las resoluciones laborales de cualquier año histórico.
    a = fecha.year % 19; b = fecha.year // 100; c = fecha.year % 100
    d = b // 4; e = b % 4; f = (b + 8) // 25; g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30; i = c // 4; k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7; m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31; dia = ((h + l - 7 * m + 114) % 31) + 1
    pascua = date(fecha.year, mes, dia)
    moviles = {pascua - timedelta(days=3): "Jueves Santo", pascua - timedelta(days=2): "Viernes Santo",
               pascua + timedelta(days=1): "Lunes de Pascua"}
    if fecha in moviles:
        return moviles[fecha]
    if texto and len(texto) <= 120 and not re.fullmatch(r"\d{1,2}\s+de\s+\w+\.?", texto, re.IGNORECASE):
        fecha_prefijo = re.match(r"^\d{1,2}\s+(.+?)\.?$", texto)
        if fecha_prefijo:
            return fecha_prefijo.group(1).strip()
        return texto
    return None


def _comunidades_dias_inhabiles(comunidades):
    """Normaliza la selección de comunidades para las consultas del calendario."""
    if comunidades is None:
        return None
    if isinstance(comunidades, str):
        comunidades = [comunidades]
    return list(dict.fromkeys(str(valor).strip() for valor in comunidades if str(valor).strip()))


def opciones_dias_inhabiles(ruta_bd="datos/boe.db"):
    """Devuelve años y comunidades con calendarios oficiales persistidos."""
    conexion = _conexion(ruta_bd)
    try:
        metadata = dict(conexion.execute("SELECT clave, valor FROM metadata"))
        clave_cache = (str(Path(ruta_bd).resolve()), metadata.get("data_version"))
        cached = _OPCIONES_INHABILES_CACHE.get(clave_cache)
        if cached is not None:
            return {clave: list(valores) for clave, valores in cached.items()}
        anios = [fila[0] for fila in conexion.execute(
            """SELECT DISTINCT c.anio
               FROM calendarios_festivos c JOIN dias_inhabiles d ON d.calendario_id = c.calendario_id
               WHERE c.estado = 'PARSEADO' ORDER BY c.anio DESC"""
        )]
        comunidades = [fila[0] for fila in conexion.execute(
            """SELECT DISTINCT d.comunidad_autonoma
               FROM dias_inhabiles d JOIN calendarios_festivos c ON c.calendario_id = d.calendario_id
               WHERE c.estado = 'PARSEADO' AND d.ambito = 'AUTONOMICO'
                 AND d.comunidad_autonoma IS NOT NULL AND trim(d.comunidad_autonoma) <> ''
               ORDER BY d.comunidad_autonoma COLLATE NOCASE"""
        )]
        resultado = {"anios": anios, "comunidades": comunidades}
        _OPCIONES_INHABILES_CACHE[clave_cache] = resultado
        if len(_OPCIONES_INHABILES_CACHE) > 4:
            _OPCIONES_INHABILES_CACHE.pop(next(iter(_OPCIONES_INHABILES_CACHE)))
        return {clave: list(valores) for clave, valores in resultado.items()}
    except sqlite3.Error as error:
        raise ErrorConsultaSQLite("Las tablas de calendarios no están disponibles.") from error
    finally:
        conexion.close()


def _filas_dias_inhabiles(conexion, *, anio, fecha=None, comunidades=None):
    """Consulta los días nacionales y los autonómicos seleccionados."""
    comunidades = _comunidades_dias_inhabiles(comunidades)
    clausulas = ["c.anio = ?", "c.estado = 'PARSEADO'"]
    parametros = [int(anio)]
    if fecha is not None:
        clausulas.append("d.fecha = ?")
        parametros.append(_fecha_iso(fecha).isoformat())
    if comunidades is not None and comunidades:
        placeholders = ",".join("?" for _ in comunidades)
        clausulas.append(f"(d.ambito = 'NACIONAL' OR (d.ambito = 'AUTONOMICO' AND d.comunidad_autonoma IN ({placeholders})))")
        parametros.extend(comunidades)
    elif comunidades is not None:
        clausulas.append("d.ambito = 'NACIONAL'")
    consulta = """SELECT d.fecha, MIN(d.nombre) AS nombre, d.ambito, d.comunidad_autonoma,
                              CASE WHEN MIN(c.publicacion_id) IS NOT NULL
                                   THEN 'https://www.boe.es/diario_boe/txt.php?id=' || MIN(c.publicacion_id)
                                   ELSE MIN(COALESCE(d.fuente_url, c.fuente_url)) END AS fuente_url,
                              MIN(c.tipo) AS calendario_tipo,
                              GROUP_CONCAT(DISTINCT c.tipo) AS tipos_calendario,
                              GROUP_CONCAT(DISTINCT CASE WHEN c.publicacion_id IS NOT NULL
                                   THEN 'https://www.boe.es/diario_boe/txt.php?id=' || c.publicacion_id
                                   ELSE COALESCE(d.fuente_url, c.fuente_url) END) AS fuentes,
                              MIN(c.publicacion_id) AS publicacion_id,
                              CASE WHEN c.tipo = 'FIESTAS_LABORALES' THEN 'LABORAL' ELSE 'ADMINISTRATIVO' END AS categoria_tipo
                       FROM dias_inhabiles d
                       JOIN calendarios_festivos c ON c.calendario_id = d.calendario_id
                       WHERE """ + " AND ".join(clausulas) + " GROUP BY d.fecha, d.ambito, d.comunidad_autonoma, categoria_tipo"
    consulta += " ORDER BY d.fecha, d.ambito, d.comunidad_autonoma, d.nombre"
    cursor = conexion.execute(consulta, parametros)
    columnas = [columna[0] for columna in cursor.description]
    filas = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
    for fila in filas:
        fila["festividad"] = festividad_dia_inhabil(fila["fecha"], fila.get("nombre"))
        fila["categoria"] = (
            "Festivo laboral" if fila.get("categoria_tipo") == "LABORAL"
            else "Día inhábil administrativo"
        )
        fila["fuentes"] = list(dict.fromkeys(
            fuente for fuente in (fila.get("fuentes") or "").split(",") if fuente
        ))
    return filas


def calendario_dias_inhabiles(ruta_bd="datos/boe.db", *, anio, comunidades=None):
    """Devuelve el conjunto de días inhábiles visible para un año y selección."""
    conexion = _conexion(ruta_bd)
    try:
        return _filas_dias_inhabiles(conexion, anio=anio, comunidades=comunidades)
    except sqlite3.Error as error:
        raise ErrorConsultaSQLite("Las tablas de calendarios no están disponibles.") from error
    finally:
        conexion.close()


def detalle_dia_inhabil(ruta_bd="datos/boe.db", *, fecha, comunidades=None):
    """Devuelve el detalle de un día, incluyendo denominaciones festivas disponibles."""
    fecha_valor = _fecha_iso(fecha)
    conexion = _conexion(ruta_bd)
    try:
        filas = _filas_dias_inhabiles(
            conexion, anio=fecha_valor.year, fecha=fecha_valor, comunidades=comunidades,
        )
    except sqlite3.Error as error:
        raise ErrorConsultaSQLite("Las tablas de calendarios no están disponibles.") from error
    finally:
        conexion.close()
    return {
        "fecha": fecha_valor.isoformat(),
        "inhabiles": filas,
        "festividades": list(dict.fromkeys(
            fila["festividad"] for fila in filas if fila.get("festividad")
        )),
    }


def _condicion_geolocalizable(alias_municipio="m"):
    return f"{alias_municipio}.latitud IS NOT NULL AND {alias_municipio}.longitud IS NOT NULL"


def _condicion_sin_coordenadas(alias_municipio="m"):
    return f"{alias_municipio}.latitud IS NULL OR {alias_municipio}.longitud IS NULL"


def _fecha_iso(valor):
    if isinstance(valor, date):
        return valor
    return datetime.strptime(str(valor), "%Y-%m-%d").date()


def _cargar_datos_cobertura(ruta_bd):
    """Carga una única instantánea de las tablas usadas por cobertura.

    La página de cobertura necesita el resumen histórico y el mes visible. Antes
    cada cálculo abría SQLite y volvía a cargar las dos tablas completas, lo que
    hacía que la petición pareciese bloqueada. Este cargador permite compartir
    esa instantánea entre ambos cálculos sin cambiar la semántica del índice.
    """
    conexion = _conexion(ruta_bd)
    try:
        metadata = dict(conexion.execute("SELECT clave, valor FROM metadata"))
        clave_cache = (str(Path(ruta_bd).resolve()), metadata.get("data_version"))
        cached = _COBERTURA_DATOS_CACHE.get(clave_cache)
        if cached is not None:
            return cached
        cobertura = pd.read_sql_query(
            "SELECT fecha AS Fecha, estado AS Estado, version_extractor AS Version_extractor, "
            "fecha_ultima_consulta AS Fecha_ultima_consulta, numero_publicaciones AS Numero_publicaciones FROM cobertura",
            conexion,
        )
        publicaciones = pd.read_sql_query(
            "SELECT publicacion_id AS Publicacion_ID, fecha_boe AS Fecha_BOE FROM publicaciones",
            conexion,
        )
        ultima = conexion.execute("SELECT MAX(fecha_ultima_consulta) FROM cobertura").fetchone()[0]
    finally:
        conexion.close()
    datos = (cobertura, publicaciones, ultima, _clasificador_cobertura_datos(cobertura, publicaciones))
    _COBERTURA_DATOS_CACHE[clave_cache] = datos
    # La versión de datos invalida las instantáneas antiguas. Se conserva una
    # pequeña ventana para no crecer sin límite si se sirven varias bases.
    if len(_COBERTURA_DATOS_CACHE) > 4:
        _COBERTURA_DATOS_CACHE.pop(next(iter(_COBERTURA_DATOS_CACHE)))
    return datos


def _clasificador_cobertura_datos(cobertura, publicaciones):
    """Construye el clasificador a partir de una instantánea ya cargada."""
    # Capturamos la fecha una sola vez: ``date.today()`` implica una llamada al
    # reloj del sistema y el resumen consulta miles de días consecutivos.
    hoy_clasificacion = date.today()
    # En SQLite las fechas productivas son ISO y la cobertura tiene una fila
    # única por día. En ese caso podemos calcular los tres invariantes que usa
    # el verificador (número, unicidad y formato de los IDs) con operaciones
    # vectorizadas, evitando recorrer 135.000 publicaciones dentro del
    # constructor genérico. Se mantiene el camino anterior para snapshots
    # históricos o esquemas no normalizados.
    fechas_cobertura = cobertura.get("Fecha", pd.Series(dtype="object"))
    fechas_publicaciones = publicaciones.get("Fecha_BOE", pd.Series(dtype="object"))
    camino_rapido = (
        not cobertura.empty
        and fechas_cobertura.notna().all()
        and fechas_cobertura.astype(str).str.fullmatch(_PATRON_FECHA_ISO).all()
        and fechas_cobertura.nunique(dropna=False) == len(fechas_cobertura)
        and not publicaciones.empty
        and fechas_publicaciones.notna().all()
        and fechas_publicaciones.astype(str).str.fullmatch(_PATRON_FECHA_ISO).all()
    )
    if camino_rapido:
        agrupadas = publicaciones.groupby("Fecha_BOE", sort=False)["Publicacion_ID"]
        publicaciones_por_fecha = agrupadas.size().to_dict()
        ids_distintos_por_fecha = agrupadas.nunique(dropna=False).to_dict()
        ids_validos = publicaciones["Publicacion_ID"].map(
            lambda valor: isinstance(valor, str) and _PATRON_PUBLICACION_ID.fullmatch(valor) is not None
        )
        ids_validos_por_fecha = ids_validos.groupby(publicaciones["Fecha_BOE"], sort=False).all().to_dict()

        def reutilizable(fecha):
            fila = filas.get(fecha)
            if fila is None or fila["Estado"] not in ESTADOS_VALIDOS | {ESTADO_INCOHERENCIA_HISTORICA_VERIFICADA}:
                return False
            valor = fila["Numero_publicaciones"]
            if valor is None or (isinstance(valor, float) and pd.isna(valor)) or isinstance(valor, bool):
                return False
            try:
                numero = float(valor)
            except (TypeError, ValueError):
                return False
            if not numero.is_integer() or numero < 0:
                return False
            numero = int(numero)
            if fila["Estado"] == ESTADO_INCOHERENCIA_HISTORICA_VERIFICADA:
                return True
            encontrados = int(publicaciones_por_fecha.get(fecha, 0))
            if fila["Estado"] == "sin_edicion":
                return numero == 0 and encontrados == 0
            if numero == 0:
                return encontrados == 0
            return (
                encontrados == numero
                and int(ids_distintos_por_fecha.get(fecha, 0)) == numero
                and bool(ids_validos_por_fecha.get(fecha, False))
            )
    else:
        reutilizable = crear_verificador_cobertura_indice(cobertura, publicaciones)

    # El recuento que se muestra en cada día conserva la semántica histórica:
    # cuenta filas de publicaciones con la fecha textual almacenada en SQLite.
    publicaciones_por_fecha = publicaciones.groupby("Fecha_BOE")["Publicacion_ID"].size().to_dict()
    filas = {
        fila["Fecha"]: {**fila, "Publicaciones_SQLite": int(publicaciones_por_fecha.get(fila["Fecha"], 0))}
        for fila in cobertura.to_dict(orient="records")
    }

    def clasificar(fecha):
        if fecha > hoy_clasificacion:
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


def _clasificador_cobertura(ruta_bd):
    """Construye el clasificador de cobertura efectiva del índice BOE."""
    return _cargar_datos_cobertura(ruta_bd)[3]


def _resumen_cobertura_desde_clasificador(clasificar, ultima, *, hoy):
    hoy = hoy or date.today()
    contador = {clave: 0 for clave in ("CONSULTADO", "SIN_EDICION", "INCOHERENCIA_VERIFICADA", "PENDIENTE", "NO_REUTILIZABLE", "FUTURO")}
    actual = FECHA_INICIO_COBERTURA
    while actual <= hoy:
        contador[clasificar(actual)["estado_visual"]] += 1
        actual += timedelta(days=1)
    total = sum(contador.values()) - contador["FUTURO"]
    cubiertos = contador["CONSULTADO"] + contador["SIN_EDICION"] + contador["INCOHERENCIA_VERIFICADA"]
    return {**contador, "fecha_inicio": FECHA_INICIO_COBERTURA.isoformat(), "fecha_fin": hoy.isoformat(),
            "dias_totales": total, "dias_cubiertos": cubiertos,
            "dias_pendientes": total - cubiertos, "porcentaje": round(100 * cubiertos / total, 2) if total else 100,
            "ultima_consulta": ultima}


def _cobertura_mes_desde_clasificador(clasificar, *, anio, mes):
    inicio = date(int(anio), int(mes), 1)
    siguiente = date(inicio.year + (inicio.month == 12), 1 if inicio.month == 12 else inicio.month + 1, 1)
    dias = [{"vacio": True} for _ in range(calendar.monthrange(inicio.year, inicio.month)[0])]
    actual = inicio
    while actual < siguiente:
        resultado = clasificar(actual)
        fila = resultado.pop("fila")
        dias.append({"fecha": actual.isoformat(), "vacio": False, **resultado,
                     "estado": fila["Estado"] if fila else None,
                     "version_extractor": fila["Version_extractor"] if fila else None,
                     "fecha_ultima_consulta": fila["Fecha_ultima_consulta"] if fila else None,
                     "numero_publicaciones": fila["Numero_publicaciones"] if fila else None,
                     "publicaciones_sqlite": fila.get("Publicaciones_SQLite") if fila else None})
        actual += timedelta(days=1)
    return {"anio": inicio.year, "mes": inicio.month, "dias": dias}


def resumen_cobertura(ruta_bd, *, hoy=None):
    """Calcula el resumen histórico de cobertura."""
    _, _, ultima, clasificar = _cargar_datos_cobertura(ruta_bd)
    return _resumen_cobertura_desde_clasificador(clasificar, ultima, hoy=hoy)


def cobertura_mes(ruta_bd, *, anio, mes):
    """Calcula el calendario de cobertura de un mes."""
    _, _, _, clasificar = _cargar_datos_cobertura(ruta_bd)
    return _cobertura_mes_desde_clasificador(clasificar, anio=anio, mes=mes)


def resumen_cobertura_y_mes(ruta_bd, *, anio, mes, hoy=None):
    """Calcula resumen y mes visible compartiendo una sola lectura de SQLite."""
    _, _, ultima, clasificar = _cargar_datos_cobertura(ruta_bd)
    resumen = _resumen_cobertura_desde_clasificador(clasificar, ultima, hoy=hoy)
    calendario = _cobertura_mes_desde_clasificador(clasificar, anio=anio, mes=mes)
    return resumen, calendario


def detalle_cobertura_dia(ruta_bd, *, fecha):
    fecha = _fecha_iso(fecha)
    for dia in cobertura_mes(ruta_bd, anio=fecha.year, mes=fecha.month)["dias"]:
        if not dia.get("vacio") and dia["fecha"] == fecha.isoformat():
            return dia
    raise ValueError("Fecha no válida")


def _conexion(ruta_bd):
    try:
        ruta = Path(ruta_bd).expanduser().resolve()
        try:
            estado = ruta.stat()
            clave_validacion = (str(ruta), estado.st_mtime_ns, estado.st_ctime_ns, estado.st_size)
        except OSError:
            # La validación conserva el mensaje de dominio cuando la base no
            # existe o no puede inspeccionarse.
            clave_validacion = None
        if clave_validacion not in _VALIDACION_BASE_CACHE:
            _VALIDACION_BASE_CACHE[clave_validacion] = base_datos.validar_base_principal(ruta)
            if len(_VALIDACION_BASE_CACHE) > 8:
                _VALIDACION_BASE_CACHE.pop(next(iter(_VALIDACION_BASE_CACHE)))
        return base_datos.conectar(ruta, readonly=True)
    except (OSError, sqlite3.Error, base_datos.EspejoSQLiteError) as error:
        raise ErrorConsultaSQLite(f"SQLite no está disponible: {ruta_bd}") from error


def _tiene_tipo_personal(conexion):
    return any(fila[1] == "tipo_personal" for fila in conexion.execute("PRAGMA table_info(oposiciones)"))


def _seleccion_tipo_personal(conexion, prefijo=""):
    columna = f"{prefijo}tipo_personal" if _tiene_tipo_personal(conexion) else "NULL AS tipo_personal"
    return columna


def _tiene_plazos(conexion):
    columnas = {fila[1] for fila in conexion.execute("PRAGMA table_info(oposiciones)")}
    return {"plazo_solicitudes", "fecha_inicio_plazo", "fecha_fin_plazo"} <= columnas


def _seleccion_plazos(conexion, prefijo=""):
    if _tiene_plazos(conexion):
        return ",".join(
            f"{prefijo}{columna}" for columna in
            ("plazo_solicitudes", "fecha_inicio_plazo", "fecha_fin_plazo", "plazo_calculo")
        )
    return ",".join(
        f"NULL AS {columna}" for columna in
        ("plazo_solicitudes", "fecha_inicio_plazo", "fecha_fin_plazo", "plazo_calculo")
    )


def _validar_plazo(valor):
    if valor in (None, "", "todas"):
        return None
    if valor != "en_plazo":
        raise ValueError("plazo debe ser 'todas' o 'en_plazo'")
    return valor


def _validar_tipos_personal(valores):
    if valores is None or valores == "":
        return []
    if isinstance(valores, str):
        valores = [valores]
    valores = [str(valor).strip() for valor in valores if str(valor).strip()]
    invalidos = sorted(set(valores) - set(TIPOS_PERSONAL))
    if invalidos:
        raise ValueError("tipo_personal no válido: " + ", ".join(invalidos))
    return list(dict.fromkeys(valores))


def _filtros(desde=None, hasta=None, provincia=None, municipio=None, administracion=None,
             puesto=None, sistema=None, turno=None, ambito=None, tipo_personal=None,
             plazo=None, tiene_plazos=True):
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
    tipos = _validar_tipos_personal(tipo_personal)
    if tipos:
        clausulas.append(f"tipo_personal IN ({','.join('?' for _ in tipos)})")
        parametros.extend(tipos)
    if _validar_plazo(plazo) == "en_plazo":
        if tiene_plazos:
            clausulas.append("fecha_fin_plazo IS NOT NULL AND fecha_fin_plazo >= ?")
            parametros.append(date.today().isoformat())
        else:
            clausulas.append("0")
    return (" WHERE " + " AND ".join(clausulas) if clausulas else ""), parametros


def oposiciones(ruta_bd="datos/boe.db", *, columnas=COLUMNAS_ESTADISTICAS, **filtros):
    """Devuelve solo las columnas y filas solicitadas, en una conexión read-only."""
    mapa = {"Num_plazas": "num_plazas", "Puesto": "puesto",
            "Puesto_normalizado": "COALESCE(puesto_normalizado, puesto)", "Administración": "COALESCE(administracion_normalizada, administracion)",
            "Comunidad_autonoma": "comunidad_autonoma",
            "Provincia": "provincia", "Municipio": "municipio", "Sistema": "sistema", "Turno": "turno",
            "Fecha_boe": "fecha_boe", "Fecha_boe_original": "fecha_boe_original",
            "Enlace": "enlace", "Latitud": "latitud",
            "Longitud": "longitud", "Habitantes": "habitantes", "Ambito": "ambito",
            "Tipo_personal": "tipo_personal"}
    try:
        conexion = _conexion(ruta_bd)
        if "Tipo_personal" in columnas and not _tiene_tipo_personal(conexion):
            mapa["Tipo_personal"] = "NULL"
        seleccion = ",".join(f"{mapa[c]} AS '{c}'" for c in columnas)
    except KeyError as error:
        raise ValueError(f"Columna de consulta no admitida: {error.args[0]}") from error
    where, parametros = _filtros(**filtros, tiene_plazos=_tiene_plazos(conexion))
    if "conexion" not in locals():
        conexion = _conexion(ruta_bd)
    try:
        return pd.read_sql_query(f"SELECT {seleccion} FROM oposiciones{where} ORDER BY fecha_boe,oposicion_id", conexion, params=parametros)
    finally:
        conexion.close()


def opciones_filtros(ruta_bd="datos/boe.db"):
    conexion = _conexion(ruta_bd)
    try:
        meta = dict(conexion.execute("SELECT clave, valor FROM metadata"))
        clave_cache = (str(Path(ruta_bd).resolve()), meta.get("data_version"))
        if clave_cache in _OPCIONES_FILTROS_CACHE:
            return {clave: list(valores) for clave, valores in _OPCIONES_FILTROS_CACHE[clave_cache].items()}
        resultado = {}
        for clave, columna in (("provincias", "provincia"), ("ambitos", "ambito"), ("sistemas", "sistema"), ("turnos", "turno")):
            filas = conexion.execute(f"SELECT DISTINCT {columna} FROM oposiciones WHERE {columna} IS NOT NULL AND trim({columna}) NOT IN ('', '--', 'no disponible') ORDER BY {columna} COLLATE NOCASE").fetchall()
            resultado[clave] = [fila[0] for fila in filas]
        resultado["puestos"] = sorted((fila[0] for fila in conexion.execute("SELECT DISTINCT COALESCE(puesto_normalizado, puesto) FROM oposiciones WHERE COALESCE(puesto_normalizado, puesto) IS NOT NULL AND trim(COALESCE(puesto_normalizado, puesto)) NOT IN ('', '--', 'no disponible')")), key=str.casefold)
        if _tiene_tipo_personal(conexion):
            resultado["tipos_personal"] = list(TIPOS_PERSONAL)
        _OPCIONES_FILTROS_CACHE[clave_cache] = {clave: list(valores) for clave, valores in resultado.items()}
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
        metadata = dict(conexion.execute("SELECT clave, valor FROM metadata"))
        clave_cache = (
            str(Path(ruta_bd).resolve()), metadata.get("data_version"),
            comunidad_autonoma or "", provincia or "", municipio or "",
        )
        cached = _OPCIONES_BUSQUEDA_CACHE.get(clave_cache)
        if cached is not None:
            return {clave: list(valores) for clave, valores in cached.items()}
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
        resultado["tipos_personal"] = list(TIPOS_PERSONAL) if _tiene_tipo_personal(conexion) else []
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
        _OPCIONES_BUSQUEDA_CACHE[clave_cache] = resultado
        if len(_OPCIONES_BUSQUEDA_CACHE) > 32:
            _OPCIONES_BUSQUEDA_CACHE.pop(next(iter(_OPCIONES_BUSQUEDA_CACHE)))
        return {clave: list(valores) for clave, valores in resultado.items()}
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
        clausulas.append("lower(COALESCE(NULLIF(puesto_normalizado,''), puesto)) LIKE lower(?)")
        parametros.append(f"%{termino}%")
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
        tipo = _seleccion_tipo_personal(conexion)
        cursor = conexion.execute(
            """SELECT oposicion_id,num_plazas,puesto,puesto_normalizado,administracion,
                      administracion_normalizada,ambito,tipo_entidad,comunidad_autonoma,
                      provincia,municipio,sistema,turno,escala,subescala,clase,fecha_boe,
                      fecha_boe_original,enlace,publicacion,confianza_geografica,
                      evidencia_geografica,version_extractor,version_resolutor,latitud,
                      longitud,habitantes,municipio_codigo_ine,""" + tipo + "," + _seleccion_plazos(conexion) + """
               FROM oposiciones WHERE oposicion_id = ?""", (oposicion_id,)
        )
        fila = cursor.fetchone()
        if fila is None:
            return None
        columnas = [columna[0] for columna in cursor.description]
        resultado = dict(zip(columnas, fila))
        resultado["enlace"] = _enlace_boe_html(resultado.get("enlace"), resultado.get("publicacion_id"))
        return resultado
    finally:
        conexion.close()


def _condiciones_busqueda(
    *, texto=None, fecha_desde=None, fecha_hasta=None, administracion=None,
    ambito=None, comunidad_autonoma=None, provincia=None, municipio=None,
    municipio_exacto=None, municipio_provincia_exacto=None, tipo_entidad=None,
    sistema=None, turno=None, escala=None, subescala=None, clase=None, tipo_personal=None,
    plazo=None, tiene_plazos=True,
):
    """Construye el ``WHERE`` parametrizado común de las búsquedas web y CLI.

    No incluye ordenación ni paginación: otros consumidores de la misma
    búsqueda podrán reutilizarlo sin alterar la semántica del listado.
    """
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
            clausulas.append("lower(COALESCE(NULLIF(puesto_normalizado,''), puesto)) LIKE lower(?)")
            parametros.append(f"%{termino}%")
    tipos = _validar_tipos_personal(tipo_personal)
    if tipos:
        clausulas.append(f"tipo_personal IN ({','.join('?' for _ in tipos)})")
        parametros.extend(tipos)
    if _validar_plazo(plazo) == "en_plazo":
        if tiene_plazos:
            clausulas.append("fecha_fin_plazo IS NOT NULL AND fecha_fin_plazo >= ?")
            parametros.append(date.today().isoformat())
        else:
            clausulas.append("0")
    return (" WHERE " + " AND ".join(clausulas) if clausulas else ""), parametros


def buscar_oposiciones(
    ruta_bd="datos/boe.db", *, texto=None, fecha_desde=None, fecha_hasta=None,
    administracion=None, ambito=None, comunidad_autonoma=None, provincia=None,
    municipio=None, municipio_exacto=None, municipio_provincia_exacto=None,
    tipo_entidad=None, sistema=None, turno=None, escala=None,
    subescala=None, clase=None, tipo_personal=None, plazo=None, pagina=1, tamano_pagina=25, orden="fecha_desc",
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

    seleccion = """oposicion_id,fecha_boe,puesto,puesto_normalizado,num_plazas,
        administracion,administracion_normalizada,ambito,tipo_entidad,
        comunidad_autonoma,provincia,municipio,sistema,turno,escala,subescala"""
    conexion = _conexion(ruta_bd)
    try:
        where, parametros = _condiciones_busqueda(
            texto=texto, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
            administracion=administracion, ambito=ambito,
            comunidad_autonoma=comunidad_autonoma, provincia=provincia,
            municipio=municipio, municipio_exacto=municipio_exacto,
            municipio_provincia_exacto=municipio_provincia_exacto,
            tipo_entidad=tipo_entidad, sistema=sistema, turno=turno,
            escala=escala, subescala=subescala, clase=clase,
            tipo_personal=tipo_personal, plazo=plazo,
            tiene_plazos=_tiene_plazos(conexion),
        )
        seleccion += "," + _seleccion_tipo_personal(conexion)
        seleccion += ",clase,enlace,publicacion,confianza_geografica,evidencia_geografica"
        if _tiene_plazos(conexion):
            seleccion += ",plazo_solicitudes,fecha_inicio_plazo,fecha_fin_plazo,plazo_calculo"
        else:
            seleccion += ",NULL AS plazo_solicitudes,NULL AS fecha_inicio_plazo,NULL AS fecha_fin_plazo,NULL AS plazo_calculo"
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
    columnas = [
        re.sub(r"^NULL AS ", "", columna, flags=re.IGNORECASE)
        if columna.upper().startswith("NULL AS ") else columna
        for columna in columnas
    ]
    return {
        "filas": [dict(zip(columnas, fila)) for fila in filas],
        "total": total, "pagina": pagina, "tamano_pagina": tamano_pagina,
        "total_paginas": total_paginas,
        "orden": orden,
    }


def resumen_mapa_oposiciones(
    ruta_bd="datos/boe.db", *, texto=None, fecha_desde=None, fecha_hasta=None,
    administracion=None, ambito=None, comunidad_autonoma=None, provincia=None,
    municipio=None, municipio_exacto=None, municipio_provincia_exacto=None,
    tipo_entidad=None, sistema=None, turno=None, escala=None,
    subescala=None, clase=None, tipo_personal=None, plazo=None,
):
    """Agrupa todos los resultados filtrados por municipio maestro e INE.

    La función no pagina: el listado y el mapa comparten el mismo ``WHERE``,
    pero el segundo necesita representar el conjunto completo de resultados.
    """
    conexion = _conexion(ruta_bd)
    tiene_plazos = _tiene_plazos(conexion)
    where, parametros = _condiciones_busqueda(
        texto=texto, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
        administracion=administracion, ambito=ambito,
        comunidad_autonoma=comunidad_autonoma, provincia=provincia,
        municipio=municipio, municipio_exacto=municipio_exacto,
        municipio_provincia_exacto=municipio_provincia_exacto,
        tipo_entidad=tipo_entidad, sistema=sistema, turno=turno,
        escala=escala, subescala=subescala, clase=clase,
        tipo_personal=tipo_personal, plazo=plazo, tiene_plazos=tiene_plazos,
    )
    condicion_geolocalizable = _condicion_geolocalizable()
    where_geolocalizable = (
        f"{where} AND {condicion_geolocalizable}"
        if where else f" WHERE {condicion_geolocalizable}"
    )
    try:
        total, plazas, geolocalizadas = conexion.execute(
            f"""SELECT COUNT(o.oposicion_id), COALESCE(SUM(o.num_plazas), 0),
                       COALESCE(SUM(CASE WHEN {condicion_geolocalizable} THEN 1 ELSE 0 END), 0)
                FROM oposiciones AS o
                LEFT JOIN municipios AS m ON m.codigo_ine = o.municipio_codigo_ine{where}""",
            parametros,
        ).fetchone()
        filas = conexion.execute(
            f"""SELECT o.municipio_codigo_ine, m.nombre, p.nombre, ca.nombre,
                       m.latitud, m.longitud, COUNT(o.oposicion_id), SUM(o.num_plazas)
                FROM oposiciones AS o
                JOIN municipios AS m ON m.codigo_ine = o.municipio_codigo_ine
                LEFT JOIN provincias AS p ON p.provincia_id = m.provincia_id
                JOIN comunidades_autonomas AS ca ON ca.comunidad_id = m.comunidad_id
                {where_geolocalizable}
                GROUP BY o.municipio_codigo_ine, m.nombre, p.nombre, ca.nombre, m.latitud, m.longitud
                ORDER BY COUNT(o.oposicion_id) DESC, m.nombre COLLATE NOCASE ASC, o.municipio_codigo_ine ASC""",
            parametros,
        ).fetchall()
    finally:
        conexion.close()
    municipios = [
        {
            "codigo_ine": fila[0], "municipio": fila[1], "provincia": fila[2],
            "comunidad_autonoma": fila[3], "latitud": fila[4], "longitud": fila[5],
            "convocatorias": fila[6], "plazas": fila[7],
        }
        for fila in filas
    ]
    return {
        "resumen": {
            "convocatorias": total, "plazas": plazas, "municipios": len(municipios),
            "geolocalizadas": geolocalizadas, "sin_coordenadas": total - geolocalizadas,
        },
        "municipios": municipios,
    }


def buscar_oposiciones_sin_coordenadas(
    ruta_bd="datos/boe.db", *, texto=None, fecha_desde=None, fecha_hasta=None,
    administracion=None, ambito=None, comunidad_autonoma=None, provincia=None,
    municipio=None, municipio_exacto=None, municipio_provincia_exacto=None,
    tipo_entidad=None, sistema=None, turno=None, escala=None,
    subescala=None, clase=None, tipo_personal=None, plazo=None, pagina=1, tamano=50,
):
    """Devuelve paginadas las convocatorias no geolocalizables del mapa."""
    try:
        pagina, tamano = int(pagina), int(tamano)
    except (TypeError, ValueError) as error:
        raise ValueError("pagina y tamano deben ser enteros positivos") from error
    if pagina < 1 or not 1 <= tamano <= _TAMANO_PAGINA_MAXIMO:
        raise ValueError(f"pagina debe ser positiva y tamano debe estar entre 1 y {_TAMANO_PAGINA_MAXIMO}")

    conexion = _conexion(ruta_bd)
    where, parametros = _condiciones_busqueda(
        texto=texto, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
        administracion=administracion, ambito=ambito,
        comunidad_autonoma=comunidad_autonoma, provincia=provincia,
        municipio=municipio, municipio_exacto=municipio_exacto,
        municipio_provincia_exacto=municipio_provincia_exacto,
        tipo_entidad=tipo_entidad, sistema=sistema, turno=turno,
        escala=escala, subescala=subescala, clase=clase,
        tipo_personal=tipo_personal, plazo=plazo, tiene_plazos=_tiene_plazos(conexion),
    )
    condicion_sin_coordenadas = _condicion_sin_coordenadas()
    where_sin_coordenadas = (
        f"{where} AND ({condicion_sin_coordenadas})"
        if where else f" WHERE ({condicion_sin_coordenadas})"
    )
    seleccion = """o.oposicion_id,COALESCE(NULLIF(o.puesto_normalizado,''), o.puesto) AS puesto,
        o.num_plazas,o.fecha_boe,o.administracion,o.comunidad_autonoma,o.provincia,
        o.municipio,o.municipio_codigo_ine,o.enlace,o.publicacion_id,
        CASE
            WHEN o.municipio_codigo_ine IS NULL OR o.municipio_codigo_ine = '' THEN 'sin_codigo_ine'
            WHEN m.codigo_ine IS NULL THEN 'codigo_ine_no_resuelto'
            ELSE 'municipio_sin_coordenadas'
        END AS motivo_sin_coordenadas"""
    try:
        total = conexion.execute(
            f"SELECT COUNT(o.oposicion_id) FROM oposiciones AS o LEFT JOIN municipios AS m ON m.codigo_ine = o.municipio_codigo_ine{where_sin_coordenadas}",
            parametros,
        ).fetchone()[0]
        paginas = ceil(total / tamano) if total else 0
        pagina = min(pagina, paginas) if paginas else 1
        offset = (pagina - 1) * tamano
        filas = conexion.execute(
            f"""SELECT {seleccion}
                FROM oposiciones AS o LEFT JOIN municipios AS m ON m.codigo_ine = o.municipio_codigo_ine
                {where_sin_coordenadas}
                ORDER BY o.fecha_boe DESC, o.oposicion_id DESC LIMIT ? OFFSET ?""",
            [*parametros, tamano, offset],
        ).fetchall()
    finally:
        conexion.close()
    columnas = [
        "oposicion_id", "puesto", "num_plazas", "fecha_boe", "administracion",
        "comunidad_autonoma", "provincia", "municipio", "municipio_codigo_ine",
        "enlace", "publicacion_id", "motivo_sin_coordenadas",
    ]
    return {
        "total": total, "pagina": pagina, "tamano": tamano, "paginas": paginas,
        "resultados": [dict(zip(columnas, fila)) for fila in filas],
    }


def metadata(ruta_bd="datos/boe.db"):
    conexion = _conexion(ruta_bd)
    try:
        return base_datos.leer_metadata(conexion)
    finally:
        conexion.close()


def obtener_data_version(ruta_bd="datos/boe.db"):
    """Lee sólo la versión de datos, sin consultar oposiciones ni validar toda la base."""
    try:
        conexion = base_datos.conectar(ruta_bd, readonly=True)
        try:
            fila = conexion.execute(
                "SELECT valor FROM metadata WHERE clave = 'data_version'"
            ).fetchone()
            if fila is None:
                raise ValueError("SQLite no contiene data_version")
            return int(fila[0])
        finally:
            conexion.close()
    except (OSError, sqlite3.Error, ValueError) as error:
        raise ErrorConsultaSQLite(f"SQLite no está disponible: {ruta_bd}") from error
