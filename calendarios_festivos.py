"""Fuentes oficiales y estado anual de calendarios de días inhábiles.

El módulo no incorpora fiestas locales. Conserva la resolución oficial que
originó cada calendario y permite reutilizarlo durante todo el año objetivo.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import re
import sqlite3
import time
import unicodedata
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

import base_datos


VERSION = "calendarios-festivos-v2"
ESTADOS = {"PENDIENTE", "ENCONTRADO", "PARSEADO", "ERROR"}
TIPOS = {"FIESTAS_LABORALES", "DIAS_INHABILES_AGE", "DIAS_INHABILES_CCAA"}
MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
    "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
    "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
COMUNIDADES = (
    "Andalucía", "Aragón", "Asturias", "Illes Balears", "Canarias",
    "Cantabria", "Castilla-La Mancha", "Castilla y León", "Cataluña",
    "Ceuta", "Melilla", "Comunitat Valenciana", "Extremadura", "Galicia",
    "Comunidad de Madrid", "Región de Murcia", "Navarra", "País Vasco",
    "La Rioja",
)
_NORM_COMUNIDADES = {
    "".join(c for c in unicodedata.normalize("NFKD", nombre).casefold()
            if not unicodedata.combining(c)): nombre
    for nombre in COMUNIDADES
}
_PATRON_ANIO = re.compile(r"\b(20\d{2})\b")
_PATRON_FECHA = re.compile(
    r"(?P<dia>\d{1,2})\s*(?:de\s*)?(?P<mes>enero|febrero|marzo|abril|mayo|junio|"
    r"julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)", re.I
)
_PATRON_DIA = re.compile(r"D[ií]a\s+(?P<dia>\d{1,2})\s*:\s*(?P<texto>[^.\n]+)", re.I)


def asegurar_esquema(conexion):
    """Crea las tablas nuevas en bases v8 sin cambiar filas existentes."""
    conexion.executescript(base_datos.ESQUEMA_CALENDARIOS)


def _texto_normalizado(valor):
    return "".join(
        c for c in unicodedata.normalize("NFKD", str(valor or "")).casefold()
        if not unicodedata.combining(c)
    )


def _anio_de_titulo(titulo):
    coincidencias = _PATRON_ANIO.findall(str(titulo or ""))
    return int(coincidencias[-1]) if coincidencias else None


def _tipo_de_titulo(titulo):
    texto = _texto_normalizado(titulo)
    if "dias inhabiles" in texto:
        if "administracion general del estado" in texto or "age" in texto:
            return "DIAS_INHABILES_AGE"
        return "DIAS_INHABILES_CCAA"
    if "fiestas laborales" in texto or "calendario laboral" in texto:
        return "FIESTAS_LABORALES"
    return None


def _iter_items_sumario(resultado):
    sumario = resultado.get("sumario") if isinstance(resultado, dict) else None
    for diario in (sumario or {}).get("diario", []) if isinstance(sumario, dict) else []:
        secciones = diario.get("seccion", []) if isinstance(diario, dict) else []
        if isinstance(secciones, dict):
            secciones = [secciones]
        for seccion in secciones:
            if not isinstance(seccion, dict):
                continue
            departamentos = seccion.get("departamento", [])
            if isinstance(departamentos, dict):
                departamentos = [departamentos]
            for departamento in departamentos:
                if not isinstance(departamento, dict):
                    continue
                grupos = departamento.get("item", [])
                if isinstance(grupos, dict):
                    grupos = [grupos]
                elif not isinstance(grupos, list):
                    grupos = []
                epigrafes = departamento.get("epigrafe", [])
                if isinstance(epigrafes, dict):
                    epigrafes = [epigrafes]
                for epigrafe in epigrafes:
                    if isinstance(epigrafe, dict):
                        items = epigrafe.get("item", [])
                        if isinstance(items, dict):
                            items = [items]
                        if isinstance(items, list):
                            grupos.extend(items)
                for item in grupos:
                    if isinstance(item, dict):
                        yield item, departamento.get("nombre", "")


def extraer_candidatos_sumario(resultado, anio_objetivo=None):
    """Detecta resoluciones de calendario en cualquier sección del sumario."""
    if resultado.get("estado") == "SIN_EDICION":
        return []
    candidatos, vistos = [], set()
    for item, departamento in _iter_items_sumario(resultado):
        titulo = str(item.get("titulo") or "").strip()
        tipo = _tipo_de_titulo(titulo)
        anio = _anio_de_titulo(titulo)
        identificador = item.get("identificador")
        if not tipo or not anio or (anio_objetivo and anio != int(anio_objetivo)) or not identificador:
            continue
        if identificador in vistos:
            continue
        vistos.add(identificador)
        candidatos.append({
            "publicacion_id": str(identificador), "titulo": titulo,
            "departamento": departamento, "anio": anio, "tipo": tipo,
            "url_xml": item.get("url_xml") or "",
            "url_html": item.get("url_html") or "",
        })
    return candidatos


def _fecha(dia, mes, anio):
    try:
        return date(int(anio), int(mes), int(dia)).isoformat()
    except (TypeError, ValueError):
        return None


def _comunidades_en_texto(texto):
    normalizado = _texto_normalizado(texto)
    return [nombre for clave, nombre in _NORM_COMUNIDADES.items() if clave in normalizado]


def normalizar_comunidad_autonoma(valor):
    """Mapea variantes habituales de la comunidad a la denominación oficial."""
    texto = _texto_normalizado(valor)
    alias = {
        "cataluna": "Cataluña", "catalunya": "Cataluña", "madrid": "Comunidad de Madrid",
        "valencia": "Comunitat Valenciana", "comunidad valenciana": "Comunitat Valenciana",
        "baleares": "Illes Balears", "islas baleares": "Illes Balears",
        "castilla leon": "Castilla y León", "castilla la mancha": "Castilla-La Mancha",
        "murcia": "Región de Murcia", "pais vasco": "País Vasco",
    }
    for clave, nombre in alias.items():
        if clave in texto:
            return nombre
    for clave, nombre in _NORM_COMUNIDADES.items():
        if clave in texto:
            return nombre
    return valor


def _fiestas_laborales_tabulares(sopa, anio):
    """Lee la tabla BOE que marca las fiestas por columnas autonómicas."""
    for tabla in sopa.find_all("table"):
        filas = []
        for fila in tabla.find_all("tr"):
            celdas = [celda.get_text(" ", strip=True) for celda in fila.find_all(["th", "td"])]
            if celdas:
                filas.append(celdas)
        encabezado = None
        comunidades = []
        for celdas in filas:
            candidatas = []
            for celda in celdas:
                normalizada = normalizar_comunidad_autonoma(celda)
                if normalizada in COMUNIDADES:
                    candidatas.append(normalizada)
                else:
                    candidatas.extend(_comunidades_en_texto(celda))
            candidatas = list(dict.fromkeys(candidatas))
            if len(candidatas) >= 3:
                encabezado, comunidades = celdas, candidatas
                break
        if not encabezado or len(comunidades) < 3:
            continue
        resultado = []
        mes_actual = None
        for celdas in filas:
            fecha_match = _PATRON_FECHA.search(celdas[0]) if celdas else None
            if fecha_match:
                mes_actual = MESES[fecha_match.group("mes").casefold()]
                fecha = _fecha(fecha_match.group("dia"), mes_actual, anio)
            else:
                mes_match = re.fullmatch(r"\s*(" + "|".join(MESES) + r")\s*", celdas[0], re.IGNORECASE) if celdas else None
                if mes_match:
                    mes_actual = MESES[mes_match.group(1).casefold()]
                    continue
                if mes_actual is None:
                    continue
                dia_match = re.match(r"\s*(\d{1,2})\b", celdas[0])
                if not dia_match:
                    continue
                fecha = _fecha(dia_match.group(1), mes_actual, anio)
            if not fecha:
                continue
            # En la tabla oficial hay una columna de fecha y una celda por
            # comunidad. Si existen celdas de apoyo, se alinea por la derecha.
            marcas = celdas[1:]
            if len(marcas) < len(comunidades):
                continue
            marcas = marcas[-len(comunidades):]
            nacional = False
            autonomicas = []
            nacionales_sustituibles = 0
            for comunidad, marca in zip(comunidades, marcas):
                texto_marca = _texto_normalizado(marca)
                if "***" in texto_marca or "**" in texto_marca:
                    autonomicas.append(comunidad)
                    if "***" not in texto_marca and "**" in texto_marca:
                        nacionales_sustituibles += 1
                elif "*" in texto_marca:
                    nacional = True
            if not nacional and nacionales_sustituibles == len(comunidades):
                nacional, autonomicas = True, []
            if nacional:
                resultado.append({"fecha": fecha, "nombre": celdas[0], "ambito": "NACIONAL", "comunidad_autonoma": None})
            resultado.extend(
                {"fecha": fecha, "nombre": celdas[0], "ambito": "AUTONOMICO", "comunidad_autonoma": comunidad}
                for comunidad in autonomicas
            )
        if resultado:
            return resultado
    return []


def parsear_documento(contenido, *, anio, tipo, fuente_url=""):
    """Extrae fechas explícitas de HTML/XML oficial de forma conservadora."""
    sopa = BeautifulSoup(contenido, "html.parser")
    resultado = []
    vistos = set()
    texto = sopa.get_text(" ", strip=True)

    def agregar(fecha, nombre, ambito, comunidad=None):
        if not fecha:
            return
        clave = (fecha, ambito, comunidad or "")
        if clave in vistos:
            return
        vistos.add(clave)
        resultado.append({"fecha": fecha, "nombre": nombre or "Día inhábil",
                          "ambito": ambito, "comunidad_autonoma": comunidad,
                          "fuente_url": fuente_url})

    if tipo == "FIESTAS_LABORALES":
        for dia in _fiestas_laborales_tabulares(sopa, anio):
            agregar(dia["fecha"], dia["nombre"], dia["ambito"], dia["comunidad_autonoma"])
        if resultado:
            return resultado

    # Resoluciones de días inhábiles: «Día 2: ...» precedido por el mes.
    for coincidencia in _PATRON_DIA.finditer(texto):
        previo = texto[max(0, coincidencia.start() - 100):coincidencia.start()]
        meses = list(re.finditer(r"\b(" + "|".join(MESES) + r")\b", previo, re.I))
        if not meses:
            continue
        mes = MESES[meses[-1].group(1).casefold()]
        cuerpo = coincidencia.group("texto")
        comunidades = _comunidades_en_texto(cuerpo)
        if comunidades:
            for comunidad in comunidades:
                agregar(_fecha(coincidencia.group("dia"), mes, anio), cuerpo, "AUTONOMICO", comunidad)
        elif "todo el territorio nacional" in _texto_normalizado(cuerpo):
            agregar(_fecha(coincidencia.group("dia"), mes, anio), cuerpo, "NACIONAL")

    # Tablas laborales: cada fila suele empezar por «1 de enero» y las
    # celdas siguientes contienen marcas para las comunidades aplicables.
    for fila in sopa.find_all("tr"):
        celdas = [celda.get_text(" ", strip=True) for celda in fila.find_all(["th", "td"])]
        if not celdas:
            continue
        fecha_match = _PATRON_FECHA.search(celdas[0])
        if not fecha_match:
            continue
        fecha = _fecha(fecha_match.group("dia"), MESES[fecha_match.group("mes").casefold()], anio)
        resto = " ".join(celdas[1:])
        comunidades = _comunidades_en_texto(resto)
        texto_resto = _texto_normalizado(resto)
        nacional = any(marca in texto_resto for marca in (
            "todo el territorio nacional", "todo el territorio", "nacional",
            "toda espana", "toda españa",
        ))
        if nacional:
            agregar(fecha, celdas[0], "NACIONAL")
        if comunidades:
            for comunidad in comunidades:
                agregar(fecha, celdas[0], "AUTONOMICO", comunidad)
        elif not nacional and (resto or tipo == "DIAS_INHABILES_AGE"):
            agregar(fecha, celdas[0], "NACIONAL")

    # Fallback para resoluciones sencillas con fechas en texto corrido.
    if not resultado:
        for coincidencia in _PATRON_FECHA.finditer(texto):
            fecha = _fecha(coincidencia.group("dia"), MESES[coincidencia.group("mes").casefold()], anio)
            contexto = texto[max(0, coincidencia.start() - 80):coincidencia.end() + 140]
            comunidades = _comunidades_en_texto(contexto)
            if comunidades:
                for comunidad in comunidades:
                    agregar(fecha, contexto, "AUTONOMICO", comunidad)
            else:
                agregar(fecha, contexto, "NACIONAL")
    return resultado


def _conectar(ruta_bd, readonly=False):
    conexion = base_datos.conectar(ruta_bd, readonly=readonly)
    if not readonly:
        asegurar_esquema(conexion)
    return conexion


def guardar_calendario(ruta_bd, candidato, contenido, *, momento=None):
    """Parsea y persiste un calendario; devuelve un resumen auditable."""
    anio, tipo = int(candidato["anio"]), candidato["tipo"]
    fuente = candidato.get("url_xml") or candidato.get("url_html") or ""
    dias = parsear_documento(contenido, anio=anio, tipo=tipo, fuente_url=fuente)
    ahora = (momento or datetime.now()).isoformat(timespec="seconds")
    conexion = _conectar(ruta_bd)
    try:
        with base_datos.transaccion(conexion):
            fila = conexion.execute(
                "SELECT calendario_id, estado FROM calendarios_festivos WHERE anio=? AND tipo=? AND ambito=? AND comunidad_autonoma IS NULL",
                (anio, tipo, "BOE"),
            ).fetchone()
            if fila is None:
                conexion.execute(
                    "INSERT INTO calendarios_festivos(anio,tipo,ambito,estado,publicacion_id,fuente_url,fecha_publicacion,version_parser,fecha_busqueda,error) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (anio, tipo, "BOE", "ENCONTRADO", candidato.get("publicacion_id"), fuente, candidato.get("fecha_publicacion"), VERSION, ahora, None),
                )
                calendario_id = conexion.execute("SELECT last_insert_rowid()").fetchone()[0]
            else:
                calendario_id = fila[0]
                conexion.execute(
                    "UPDATE calendarios_festivos SET estado='ENCONTRADO',publicacion_id=?,fuente_url=?,version_parser=?,fecha_busqueda=?,error=NULL WHERE calendario_id=?",
                    (candidato.get("publicacion_id"), fuente, VERSION, ahora, calendario_id),
                )
            conexion.execute("DELETE FROM dias_inhabiles WHERE calendario_id=?", (calendario_id,))
            conexion.executemany(
                "INSERT INTO dias_inhabiles(calendario_id,fecha,nombre,ambito,comunidad_autonoma,fuente_url) VALUES (?,?,?,?,?,?)",
                [(calendario_id, d["fecha"], d["nombre"], d["ambito"], d["comunidad_autonoma"], d["fuente_url"]) for d in dias],
            )
            conexion.execute("UPDATE calendarios_festivos SET estado=?,fecha_busqueda=? WHERE calendario_id=?", ("PARSEADO" if dias else "ERROR", ahora, calendario_id))
    finally:
        conexion.close()
    return {"anio": anio, "tipo": tipo, "estado": "PARSEADO" if dias else "ERROR", "dias": len(dias), "fuente": fuente}


def descargar_y_guardar_calendario(ruta_bd, candidato, *, obtener=requests.get, timeout=20):
    conexion = _conectar(ruta_bd, readonly=True)
    try:
        fila = conexion.execute(
            "SELECT estado FROM calendarios_festivos WHERE anio=? AND tipo=? AND ambito=? AND comunidad_autonoma IS NULL",
            (int(candidato["anio"]), candidato["tipo"], "BOE"),
        ).fetchone()
        if fila and fila[0] == "PARSEADO":
            return {"anio": int(candidato["anio"]), "tipo": candidato["tipo"], "estado": "PARSEADO", "dias": None, "fuente": "persistido", "omitido": True}
    except sqlite3.OperationalError:
        pass
    finally:
        conexion.close()
    url = candidato.get("url_xml") or candidato.get("url_html")
    if not url or urlparse(url).scheme not in {"http", "https"}:
        raise ValueError("El candidato de calendario no tiene una URL oficial válida")
    respuesta = obtener(url, headers={"Accept": "application/xml,text/html"}, timeout=timeout)
    respuesta.raise_for_status()
    return guardar_calendario(ruta_bd, candidato, respuesta.content)


def _ventana_busqueda(anio):
    """Ventana habitual de publicación del calendario del año objetivo."""
    inicio = date(int(anio) - 1, 10, 1)
    fin = date(int(anio), 2, 28)
    while inicio <= fin and inicio.weekday() >= 5:
        inicio += timedelta(days=1)
    return inicio, fin


def _estado_busqueda(conexion, anio):
    return conexion.execute(
        "SELECT estado,ventana_desde,ventana_hasta FROM busquedas_calendarios WHERE anio=?",
        (int(anio),),
    ).fetchone()


def _guardar_estado_busqueda(conexion, anio, inicio, fin, estado, consultas, error=None):
    conexion.execute(
        """INSERT INTO busquedas_calendarios(anio,ventana_desde,ventana_hasta,estado,fecha_ultima_busqueda,consultas,error)
           VALUES (?,?,?,?,datetime('now'),?,?)
           ON CONFLICT(anio) DO UPDATE SET ventana_desde=excluded.ventana_desde,
             ventana_hasta=excluded.ventana_hasta,estado=excluded.estado,
             fecha_ultima_busqueda=excluded.fecha_ultima_busqueda,consultas=excluded.consultas,error=excluded.error""",
        (int(anio), inicio.isoformat(), fin.isoformat(), estado, int(consultas), error),
    )


def descubrir_calendarios(ruta_bd, anios, *, obtener_sumario=None, obtener_documento=requests.get,
                          timeout=20, pausa=0.2, forzar=False, informar=None):
    """Busca y persiste calendarios oficiales en las ventanas anuales del BOE.

    La búsqueda queda registrada por año. Una ventana completada no vuelve a
    consultarse salvo que ``forzar`` sea verdadero; los calendarios ya
    parseados tampoco vuelven a descargarse.
    """
    from boe_api import obtener_sumario_api

    if pausa < 0:
        raise ValueError("pausa no puede ser negativa")
    obtener_sumario = obtener_sumario or obtener_sumario_api
    anios = sorted({int(anio) for anio in anios})
    conexion = _conectar(ruta_bd)
    conexion.commit()
    conexion.close()
    resumen = {"anios": anios, "consultas": 0, "calendarios": [], "errores": []}
    marca = None
    for anio in anios:
        inicio, fin = _ventana_busqueda(anio)
        if fin > date.today():
            fin = date.today()
        conexion = _conectar(ruta_bd, readonly=True)
        try:
            estado = _estado_busqueda(conexion, anio)
            parseados = {
                fila[0] for fila in conexion.execute(
                    "SELECT tipo FROM calendarios_festivos WHERE anio=? AND estado='PARSEADO'",
                    (anio,),
                )
            }
        finally:
            conexion.close()
        if not forzar and estado and estado[0] == "COMPLETADO" and estado[1] == inicio.isoformat() and estado[2] == fin.isoformat():
            continue
        faltan = TIPOS - parseados
        consultas_anio = 0
        errores_anio = []
        actual = inicio
        while actual <= fin and faltan:
            if actual.weekday() >= 5:
                actual += timedelta(days=1)
                continue
            if marca is not None and pausa:
                espera = pausa - (time.monotonic() - marca)
                if espera > 0:
                    time.sleep(espera)
            marca = time.monotonic()
            consultas_anio += 1
            resumen["consultas"] += 1
            try:
                candidatos = extraer_candidatos_sumario(
                    obtener_sumario(actual, timeout=timeout), anio_objetivo=anio
                )
                for candidato in candidatos:
                    if candidato["tipo"] not in faltan:
                        continue
                    try:
                        resultado = descargar_y_guardar_calendario(
                            ruta_bd, candidato, obtener=obtener_documento, timeout=timeout
                        )
                        resumen["calendarios"].append(resultado)
                        if resultado.get("estado") == "PARSEADO":
                            faltan.discard(candidato["tipo"])
                    except Exception as error:  # el calendario no bloquea los plazos
                        errores_anio.append(f"{candidato.get('publicacion_id')}: {error}")
            except Exception as error:
                errores_anio.append(f"{actual.isoformat()}: {error}")
            conexion = _conectar(ruta_bd)
            try:
                with base_datos.transaccion(conexion):
                    _guardar_estado_busqueda(
                        conexion, anio, inicio, fin, "EN_CURSO", consultas_anio,
                        "; ".join(errores_anio[-3:]) or None,
                    )
            finally:
                conexion.close()
            if informar:
                informar(anio, actual, faltan, resumen["consultas"])
            actual += timedelta(days=1)
        estado_final = "COMPLETADO" if not faltan and not errores_anio else ("INCOMPLETO" if faltan else "COMPLETADO")
        conexion = _conectar(ruta_bd)
        try:
            with base_datos.transaccion(conexion):
                _guardar_estado_busqueda(
                    conexion, anio, inicio, fin, estado_final, consultas_anio,
                    "; ".join(errores_anio[-3:]) or None,
                )
        finally:
            conexion.close()
        resumen["errores"].extend({"anio": anio, "error": error} for error in errores_anio)
    return resumen


def festivos_para_anio(ruta_bd, anio, *, comunidad_autonoma=None):
    """Devuelve festivos confirmados o ``None`` si aún no hay calendario."""
    comunidad_autonoma = normalizar_comunidad_autonoma(comunidad_autonoma)
    try:
        conexion = _conectar(ruta_bd, readonly=True)
    except (sqlite3.OperationalError, OSError):
        return None
    try:
        existe = conexion.execute(
            "SELECT 1 FROM calendarios_festivos WHERE anio=? AND estado='PARSEADO' LIMIT 1",
            (int(anio),),
        ).fetchone()
        if existe is None:
            return None
        sql = """SELECT d.fecha FROM dias_inhabiles d JOIN calendarios_festivos c ON c.calendario_id=d.calendario_id
                 WHERE c.anio=? AND c.estado='PARSEADO' AND (d.ambito='NACIONAL' OR (d.ambito='AUTONOMICO' AND d.comunidad_autonoma=?))"""
        return {fila[0] for fila in conexion.execute(sql, (int(anio), comunidad_autonoma or ""))}
    except sqlite3.OperationalError:
        return None
    finally:
        conexion.close()


def advertencia_plazo(plazo_calculo):
    """Indica cuándo el resultado puede variar por fiestas locales."""
    return str(plazo_calculo or "").startswith("CALCULADO_DIAS_HABILES") and "EXPLICITO" not in str(plazo_calculo)
