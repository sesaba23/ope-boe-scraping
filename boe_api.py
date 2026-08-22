"""Cliente experimental, de solo lectura, para el sumario oficial del BOE."""

from datetime import date, datetime
import re
from xml.etree import ElementTree

import requests


URL_SUMARIO = "https://www.boe.es/datosabiertos/api/boe/sumario/{fecha}"
TIMEOUT = 10
ESTADOS = {"SIN_EDICION", "SIN_SECCION_2B", "CON_PUBLICACIONES", "ERROR"}
PATRON_ID = re.compile(r"^BOE-[A-Z]-\d{4}-\d+$")


class ErrorAPIBOE(RuntimeError):
    """Error clasificado al consultar o validar la API oficial."""

    def __init__(self, tipo, mensaje, status_http=None):
        super().__init__(mensaje)
        self.tipo = tipo
        self.status_http = status_http


def obtener_sumario_api(fecha, obtener=requests.get, timeout=TIMEOUT):
    """Obtiene y valida el sumario oficial para una fecha."""
    fecha_api = _normalizar_fecha(fecha)
    url = URL_SUMARIO.format(fecha=fecha_api)
    try:
        respuesta = obtener(
            url, headers={"Accept": "application/json"}, timeout=timeout
        )
    except requests.exceptions.Timeout as error:
        raise ErrorAPIBOE("TIMEOUT", str(error)) from error
    except requests.exceptions.ConnectionError as error:
        raise ErrorAPIBOE("CONEXION", str(error)) from error
    except requests.exceptions.RequestException as error:
        raise ErrorAPIBOE("RED", str(error)) from error

    if respuesta.status_code == 404:
        datos = _json_opcional(respuesta)
        if _respuesta_indica_sin_edicion(datos) or _xml_indica_sin_edicion(
            respuesta.content
        ):
            return {"estado": "SIN_EDICION", "fecha": fecha_api, "sumario": None}
        raise ErrorAPIBOE("HTTP_404", "404 sin confirmación de ausencia de edición", 404)
    try:
        respuesta.raise_for_status()
    except requests.exceptions.HTTPError as error:
        codigo = respuesta.status_code
        tipo = (
            "HTTP_400" if codigo == 400 else
            "HTTP_429" if codigo == 429 else
            "HTTP_5XX" if 500 <= codigo < 600 else
            "HTTP"
        )
        raise ErrorAPIBOE(tipo, str(error), codigo) from error
    try:
        datos = respuesta.json()
    except (ValueError, TypeError) as error:
        raise ErrorAPIBOE("JSON_INVALIDO", "La respuesta no contiene JSON válido") from error
    if not isinstance(datos, dict):
        raise ErrorAPIBOE("ESTRUCTURA", "La raíz JSON no es un objeto")

    status = datos.get("status")
    if not isinstance(status, dict) or "code" not in status:
        raise ErrorAPIBOE("ESTRUCTURA", "Falta status.code en la respuesta")
    codigo_interno = str(status["code"])
    if codigo_interno != "200":
        if codigo_interno == "404" and _respuesta_indica_sin_edicion(datos):
            return {"estado": "SIN_EDICION", "fecha": fecha_api, "sumario": None}
        raise ErrorAPIBOE(
            f"STATUS_{codigo_interno}",
            f"La API devolvió status.code={codigo_interno}: {status.get('text', '')}",
        )
    try:
        sumario = datos["data"]["sumario"]
    except (KeyError, TypeError) as error:
        raise ErrorAPIBOE("ESTRUCTURA", "Falta data.sumario") from error
    if not isinstance(sumario, dict) or not isinstance(sumario.get("diario"), list):
        raise ErrorAPIBOE("ESTRUCTURA", "data.sumario.diario no es una lista")
    return {"estado": "OK", "fecha": fecha_api, "sumario": sumario}


def extraer_publicaciones_2b_api(resultado_sumario):
    """Extrae y normaliza exclusivamente los documentos de la sección II.B."""
    if resultado_sumario.get("estado") == "SIN_EDICION":
        return {"estado": "SIN_EDICION", "publicaciones": []}
    sumario = resultado_sumario.get("sumario")
    if not isinstance(sumario, dict) or not isinstance(sumario.get("diario"), list):
        raise ErrorAPIBOE("ESTRUCTURA", "Sumario no validado")

    secciones = []
    for diario in sumario["diario"]:
        if not isinstance(diario, dict):
            raise ErrorAPIBOE("ESTRUCTURA", "Estructura de diario/sección inesperada")
        secciones_diario = diario.get("seccion", [])
        if isinstance(secciones_diario, dict):
            secciones_diario = [secciones_diario]
        if not isinstance(secciones_diario, list):
            raise ErrorAPIBOE("ESTRUCTURA", "Estructura de diario/sección inesperada")
        for seccion in secciones_diario:
            if _es_seccion_2b(seccion):
                secciones.append(seccion)
    if not secciones:
        return {"estado": "SIN_SECCION_2B", "publicaciones": []}

    publicaciones = []
    claves = set()
    for seccion in secciones:
        departamentos = seccion.get("departamento", [])
        if isinstance(departamentos, dict):
            departamentos = [departamentos]
        if not isinstance(departamentos, list):
            raise ErrorAPIBOE("ESTRUCTURA", "departamento no es objeto ni lista")
        for departamento in departamentos:
            for item in _items_departamento(departamento):
                publicacion = _normalizar_item(item, departamento)
                clave = publicacion.get("Publicacion_ID") or _primera_url(publicacion)
                if clave and clave not in claves:
                    claves.add(clave)
                    publicaciones.append(publicacion)
    return {"estado": "CON_PUBLICACIONES", "publicaciones": publicaciones}


def _normalizar_fecha(valor):
    if isinstance(valor, datetime):
        valor = valor.date()
    if isinstance(valor, date):
        return valor.strftime("%Y%m%d")
    if isinstance(valor, str):
        texto = valor.strip()
        for formato in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(texto, formato).strftime("%Y%m%d")
            except ValueError:
                pass
    raise ValueError("Fecha inválida; use date, datetime, AAAAMMDD o AAAA-MM-DD")


def _json_opcional(respuesta):
    try:
        datos = respuesta.json()
        return datos if isinstance(datos, dict) else None
    except (ValueError, TypeError):
        return None


def _respuesta_indica_sin_edicion(datos):
    if not isinstance(datos, dict):
        return False
    status = datos.get("status", {})
    texto = str(status.get("text", "")).casefold()
    return str(status.get("code", "")) == "404" and any(
        fragmento in texto for fragmento in ("no encontrado", "not found", "no existe")
    )


def _xml_indica_sin_edicion(contenido):
    try:
        raiz = ElementTree.fromstring(contenido)
    except (ElementTree.ParseError, TypeError):
        return False
    codigo = raiz.findtext("./status/code")
    texto = (raiz.findtext("./status/text") or "").casefold()
    return codigo == "404" and any(
        fragmento in texto
        for fragmento in ("no existe", "no encontrado", "not found")
    )


def _es_seccion_2b(seccion):
    if not isinstance(seccion, dict):
        raise ErrorAPIBOE("ESTRUCTURA", "Una sección no es un objeto")
    codigo = str(seccion.get("codigo", "")).upper().replace(".", "")
    if codigo == "2B":
        return True
    nombre = " ".join(str(seccion.get("nombre", "")).casefold().split())
    return "ii. autoridades y personal" in nombre and "b. oposiciones y concursos" in nombre


def _items_departamento(departamento):
    if not isinstance(departamento, dict):
        raise ErrorAPIBOE("ESTRUCTURA", "Un departamento no es un objeto")
    epigrafes = departamento.get("epigrafe", [])
    if isinstance(epigrafes, dict):
        epigrafes = [epigrafes]
    if not isinstance(epigrafes, list):
        raise ErrorAPIBOE("ESTRUCTURA", "epigrafe no es objeto ni lista")
    for epigrafe in epigrafes:
        if not isinstance(epigrafe, dict):
            raise ErrorAPIBOE("ESTRUCTURA", "Un epígrafe no es un objeto")
        items = epigrafe.get("item", [])
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            raise ErrorAPIBOE("ESTRUCTURA", "item no es objeto ni lista")
        yield from items


def _normalizar_item(item, departamento):
    if not isinstance(item, dict):
        raise ErrorAPIBOE("ESTRUCTURA", "Un item no es un objeto")
    resultado = {}
    identificador = item.get("identificador")
    if identificador and PATRON_ID.fullmatch(str(identificador)):
        resultado["Publicacion_ID"] = str(identificador)
    for origen, destino in (("titulo", "titulo"), ("url_html", "url_html"), ("url_xml", "url_xml")):
        if item.get(origen):
            resultado[destino] = item[origen]
    pdf = item.get("url_pdf")
    if isinstance(pdf, dict) and pdf.get("texto"):
        resultado["url_pdf"] = pdf["texto"]
    elif isinstance(pdf, str) and pdf:
        resultado["url_pdf"] = pdf
    if departamento.get("nombre"):
        resultado["departamento"] = departamento["nombre"]
    return resultado


def _primera_url(publicacion):
    return next((publicacion.get(k) for k in ("url_html", "url_xml", "url_pdf") if publicacion.get(k)), None)
