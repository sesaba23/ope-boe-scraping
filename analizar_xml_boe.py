"""Investigación de solo lectura sobre el XML documental oficial del BOE."""

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
from statistics import mean
import tempfile
import time
import unicodedata
from xml.etree import ElementTree

from bs4 import BeautifulSoup, ParserRejectedMarkup
import requests

from boe_api import ErrorAPIBOE, extraer_publicaciones_2b_api, obtener_sumario_api


CAMPOS = [
    "Puesto", "Num_plazas", "Turno", "Sistema", "Escala", "Subescala",
    "Clase", "Administración", "Fecha_boe", "Publicacion_ID",
]
MUESTRA_2004 = {
    "BOE-A-2004-1870": "2004-01-31",
    "BOE-A-2004-4176": "2004-03-08",
    "BOE-A-2004-6389": "2004-04-10",
    "BOE-A-2004-6488": "2004-04-13",
    "BOE-A-2004-10041": "2004-05-29",
    "BOE-A-2004-11945": "2004-06-25",
    "BOE-A-2004-12152": "2004-06-29",
    "BOE-A-2004-12500": "2004-07-03",
    "BOE-A-2004-19327": "2004-11-13",
    "BOE-A-2004-21018": "2004-12-14",
}
OBLIGATORIAS = {
    "BOE-A-2004-6488", "BOE-A-2004-10041", "BOE-A-2004-1870",
    "BOE-A-2004-6389", "BOE-A-2004-12152",
}
ETIQUETAS_ESTRUCTURADAS = {
    "Puesto": {"puesto", "denominacion_puesto", "categoria", "cuerpo"},
    "Num_plazas": {"numero_plazas", "num_plazas", "plazas"},
    "Turno": {"turno", "tipo_turno"},
    "Sistema": {"sistema_selectivo", "sistema", "procedimiento"},
    "Escala": {"escala"},
    "Subescala": {"subescala"},
    "Clase": {"clase"},
    "Administración": {"departamento", "organismo", "administracion"},
    "Fecha_boe": {"fecha_publicacion"},
    "Publicacion_ID": {"identificador"},
}
PALABRAS_CAMPO = {
    "Puesto": ("puesto", "categoria", "cuerpo"),
    "Num_plazas": ("plaza", "vacante"),
    "Turno": ("turno libre", "promocion interna"),
    "Sistema": ("oposicion", "concurso-oposicion", "concurso de acceso"),
    "Escala": ("escala",), "Subescala": ("subescala",),
    "Clase": ("clase",),
    "Administración": ("ayuntamiento", "ministerio", "universidad", "administracion"),
    "Fecha_boe": ("fecha",), "Publicacion_ID": ("boe-a-",),
}
ETIQUETAS_SEMIESTRUCTURADAS = {"table", "tabla", "tbody", "tr", "fila", "anexo", "cuadro"}


def obtener_muestra_api(anio=2004, limite=10, publicacion_id=None, consultar_api=None):
    """Recupera de la API los documentos fijados para la muestra experimental."""
    consultar_api = consultar_api or obtener_sumario_api
    if publicacion_id:
        fechas = [MUESTRA_2004[publicacion_id]] if publicacion_id in MUESTRA_2004 else None
        ids = [publicacion_id]
    else:
        ids = list(MUESTRA_2004)[:limite]
        fechas = sorted({MUESTRA_2004[x] for x in ids})
    encontradas = {}
    if fechas is not None:
        for fecha in fechas:
            resultado = extraer_publicaciones_2b_api(consultar_api(fecha))
            for documento in resultado["publicaciones"]:
                encontradas[documento.get("Publicacion_ID")] = {**documento, "Fecha": fecha}
    else:
        actual = date(anio, 1, 1)
        while actual <= date(anio, 12, 31) and publicacion_id not in encontradas:
            resultado = extraer_publicaciones_2b_api(consultar_api(actual))
            for documento in resultado["publicaciones"]:
                encontradas[documento.get("Publicacion_ID")] = {**documento, "Fecha": actual.isoformat()}
            actual += timedelta(days=1)
    faltantes = [identificador for identificador in ids if identificador not in encontradas]
    if faltantes:
        raise ValueError(f"La API no devolvió: {', '.join(faltantes)}")
    muestra = [encontradas[x] for x in ids]
    for documento in muestra:
        if not documento.get("url_html") or not documento.get("url_xml"):
            raise ValueError(f"Faltan URLs oficiales para {documento['Publicacion_ID']}")
    return muestra


def analizar_xml(contenido):
    """Analiza XML con ElementTree sin resolver entidades externas."""
    if not contenido:
        raise ValueError("XML vacío")
    if b"<!DOCTYPE" in contenido.upper() or b"<!ENTITY" in contenido.upper():
        raise ValueError("El XML contiene una declaración no admitida")
    namespaces = {}
    try:
        for evento, dato in ElementTree.iterparse(BytesIO(contenido), events=("start-ns",)):
            namespaces[dato[0] or "(predeterminado)"] = dato[1]
        raiz = ElementTree.fromstring(contenido)
    except ElementTree.ParseError as error:
        raise ValueError(f"XML inválido: {error}") from error

    etiquetas = Counter(_local(elemento.tag) for elemento in raiz.iter())
    atributos = defaultdict(set)
    for elemento in raiz.iter():
        atributos[_local(elemento.tag)].update(elemento.attrib)
    metadatos = {}
    nodo_metadatos = _buscar(raiz, "metadatos")
    if nodo_metadatos is not None:
        for hijo in nodo_metadatos:
            metadatos[_local(hijo.tag)] = " ".join(hijo.itertext()).strip() or None
    nodo_texto = _buscar(raiz, "texto")
    if nodo_texto is None:
        raise LookupError("No existe el bloque texto")
    bloques_texto = [
        {"etiqueta": _local(elemento.tag), "atributos": dict(elemento.attrib), "texto": " ".join(elemento.itertext()).strip()}
        for elemento in list(nodo_texto)
        if " ".join(elemento.itertext()).strip()
    ]
    texto = "\n".join(bloque["texto"] for bloque in bloques_texto)
    soporte = clasificar_soporte_campos(raiz, texto)
    return {
        "elemento_raiz": _local(raiz.tag),
        "namespaces": namespaces,
        "jerarquia_principal": _jerarquia(raiz),
        "etiquetas": dict(sorted(etiquetas.items())),
        "atributos": {k: sorted(v) for k, v in sorted(atributos.items()) if v},
        "bloques_repetidos": {k: v for k, v in etiquetas.items() if v > 1},
        "metadatos": metadatos,
        "numero_bloques_texto": len(bloques_texto),
        "tipos_bloques_texto": dict(Counter(b["etiqueta"] for b in bloques_texto)),
        "texto_relevante": texto,
        "soporte_campos": soporte,
    }


def clasificar_soporte_campos(raiz, texto):
    etiquetas = defaultdict(list)
    semiestructurados = []
    for elemento in raiz.iter():
        nombre = _local(elemento.tag)
        valor = " ".join(elemento.itertext()).strip()
        if valor:
            etiquetas[nombre].append(valor)
        clase = str(elemento.attrib.get("class", "")).casefold()
        if nombre in ETIQUETAS_SEMIESTRUCTURADAS or "tabla" in clase:
            semiestructurados.append(_normalizar(valor))
    texto_normalizado = _normalizar(texto)
    resultado = {}
    for campo in CAMPOS:
        nombres = ETIQUETAS_ESTRUCTURADAS[campo]
        if any(etiquetas[nombre] for nombre in nombres):
            resultado[campo] = "ESTRUCTURADO"
            continue
        palabras = PALABRAS_CAMPO[campo]
        if any(any(palabra in bloque for palabra in palabras) for bloque in semiestructurados):
            resultado[campo] = "SEMIESTRUCTURADO"
        elif any(palabra in texto_normalizado for palabra in palabras):
            resultado[campo] = "TEXTO_LIBRE"
        else:
            resultado[campo] = "NO_PRESENTE"
    return resultado


def comparar_html_xml(html, analisis_xml):
    """Compara el texto principal HTML con el bloque textual XML."""
    try:
        soup = BeautifulSoup(html, "html.parser")
    except ParserRejectedMarkup as error:
        raise ValueError(f"HTML inválido: {error}") from error
    bloques = soup.find_all("div", id="textoxslt")
    if not bloques:
        raise LookupError("HTML sin div#textoxslt")
    texto_html = "\n".join(b.get_text(" ", strip=True) for b in bloques)
    texto_xml = analisis_xml["texto_relevante"]
    normal_html, normal_xml = _normalizar(texto_html), _normalizar(texto_xml)
    similitud = SequenceMatcher(None, normal_html, normal_xml, autojunk=False).ratio()
    meta_html = {
        "titulo": _texto_nodo(soup.find(class_="documento-tit")),
        "fecha": _texto_nodo(soup.find("div", class_="metadatos")),
    }
    meta_xml = analisis_xml["metadatos"]
    return {
        "similitud_textual": similitud,
        "contenido_esencialmente_igual": similitud >= 0.95,
        "metadatos_html": meta_html,
        "metadatos_xml": {
            k: meta_xml.get(k) for k in ("identificador", "departamento", "titulo", "fecha_publicacion")
        },
        "informacion_solo_xml": [k for k, v in meta_xml.items() if v and k not in {"titulo", "fecha_publicacion"}],
        "informacion_solo_html": [k for k, v in meta_html.items() if v and not meta_xml.get("titulo" if k == "titulo" else "fecha_publicacion")],
    }


def analizar_publicacion(documento, obtener=None):
    obtener = obtener or requests.get
    base = {k: documento.get(k) for k in ("Publicacion_ID", "Fecha", "titulo", "departamento", "url_html", "url_xml")}
    inicio = time.perf_counter()
    try:
        respuesta_xml = obtener(documento["url_xml"], timeout=10)
        if respuesta_xml.status_code == 404:
            return _resultado_error(base, "XML_NO_DISPONIBLE", "XML no disponible", inicio)
        respuesta_xml.raise_for_status()
    except requests.exceptions.RequestException as error:
        return _resultado_error(base, "ERROR_HTTP", str(error), inicio)
    try:
        estructura = analizar_xml(respuesta_xml.content)
    except ValueError as error:
        return _resultado_error(base, "XML_INVALIDO", str(error), inicio)
    except LookupError as error:
        return _resultado_error(base, "ERROR_ESTRUCTURA", str(error), inicio)
    try:
        respuesta_html = obtener(documento["url_html"], timeout=10)
        respuesta_html.raise_for_status()
        comparacion = comparar_html_xml(respuesta_html.content, estructura)
    except (requests.exceptions.RequestException, ValueError, LookupError) as error:
        return _resultado_error(base, "ERROR_ESTRUCTURA", str(error), inicio, estructura)
    evitar, justificacion, beneficio = evaluar_utilidad(estructura["soporte_campos"])
    estructura_sin_texto = dict(estructura)
    estructura_sin_texto.pop("texto_relevante", None)
    return {
        **base, "estado": "XML_VALIDO", "estructura_xml": estructura_sin_texto,
        "comparacion_html_xml": comparacion, "xml_evitaria_regex_historico": evitar,
        "justificacion": justificacion, "beneficio": beneficio,
        "tiempo": time.perf_counter() - inicio, "error": None,
    }


def evaluar_utilidad(soporte):
    campos_funcionales = [c for c in CAMPOS if c not in {"Publicacion_ID", "Fecha_boe", "Administración"}]
    estructurados = [c for c in campos_funcionales if soporte[c] == "ESTRUCTURADO"]
    semi = [c for c in campos_funcionales if soporte[c] == "SEMIESTRUCTURADO"]
    metadatos_utiles = sum(soporte[c] == "ESTRUCTURADO" for c in ("Publicacion_ID", "Fecha_boe", "Administración"))
    if "Puesto" in estructurados and "Num_plazas" in estructurados:
        return "SI", "Puesto y número de plazas tienen elementos específicos.", "EXTRACTOR_XML_COMPLETO"
    if semi or metadatos_utiles:
        return "PARCIALMENTE", "El XML estructura metadatos o bloques, pero los campos funcionales requieren analizar texto.", "HIBRIDO_XML_TEXTO"
    return "NO", "Los datos funcionales solo aparecen como texto libre o no aparecen.", "SIN_BENEFICIO"


def resumir(detalles):
    estados = Counter(d["estado"] for d in detalles)
    soportes = Counter()
    beneficios = Counter(d.get("beneficio") for d in detalles if d.get("beneficio"))
    for detalle in detalles:
        if detalle.get("estructura_xml"):
            soportes.update(detalle["estructura_xml"]["soporte_campos"].values())
    return {
        "publicaciones_analizadas": len(detalles), "XML_VALIDO": estados["XML_VALIDO"],
        "XML_NO_DISPONIBLE": estados["XML_NO_DISPONIBLE"],
        "errores": len(detalles) - estados["XML_VALIDO"] - estados["XML_NO_DISPONIBLE"],
        "soporte_campos": dict(soportes), "beneficios": dict(beneficios),
        "tiempo_total": sum(d["tiempo"] for d in detalles),
        "tiempo_medio": mean([d["tiempo"] for d in detalles]) if detalles else 0,
    }


def guardar_informes(detalles, resumen, integridad, directorio="informes/xml_2004", momento=None):
    instante = momento or datetime.now()
    carpeta = Path(directorio)
    carpeta.mkdir(parents=True, exist_ok=True)
    base = carpeta / f"analisis_xml_2004_{instante.strftime('%Y%m%d_%H%M%S')}"
    json_path = _ruta_unica(base.with_suffix(".json"))
    md_path = json_path.with_suffix(".md")
    datos = {"fecha_ejecucion": instante.strftime("%Y-%m-%d %H:%M:%S"), "seleccion": _descripcion_muestra(), **resumen, "integridad_excel": integridad, "publicaciones": detalles}
    _guardar_atomico(json_path, json.dumps(datos, ensure_ascii=False, indent=2))
    _guardar_atomico(md_path, _markdown(detalles, resumen, integridad))
    return json_path, md_path


def ejecutar(anio=2004, limite=10, publicacion_id=None, ruta_excel="BOE-oposiciones.xlsx"):
    antes = integridad_excel(ruta_excel)
    muestra = obtener_muestra_api(anio, limite, publicacion_id)
    detalles = [analizar_publicacion(documento) for documento in muestra]
    resumen = resumir(detalles)
    despues = integridad_excel(ruta_excel)
    integridad = {"antes": antes, "despues": despues, "sin_cambios": antes == despues}
    rutas = guardar_informes(detalles, resumen, integridad)
    return detalles, resumen, integridad, rutas


def integridad_excel(ruta="BOE-oposiciones.xlsx"):
    ruta = Path(ruta); contenido = ruta.read_bytes(); estado = ruta.stat()
    return {"sha256": hashlib.sha256(contenido).hexdigest(), "tamano": estado.st_size, "mtime_ns": estado.st_mtime_ns}


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Análisis experimental del XML BOE")
    parser.add_argument("--anio", type=int, default=2004)
    parser.add_argument("--limite", type=int, default=10)
    parser.add_argument("--publicacion")
    opciones = parser.parse_args(argumentos)
    detalles, resumen, integridad, rutas = ejecutar(opciones.anio, opciones.limite, opciones.publicacion)
    print(f"Publicaciones analizadas: {resumen['publicaciones_analizadas']}")
    print(f"XML válidos: {resumen['XML_VALIDO']}")
    print(f"XML no disponibles: {resumen['XML_NO_DISPONIBLE']}")
    print(f"Errores: {resumen['errores']}")
    print(f"JSON: {rutas[0]}\nMarkdown: {rutas[1]}")
    if not integridad["sin_cambios"]:
        raise SystemExit("El Excel cambió durante el análisis")


def _resultado_error(base, estado, mensaje, inicio, estructura=None):
    resultado = {**base, "estado": estado, "estructura_xml": estructura, "comparacion_html_xml": None, "xml_evitaria_regex_historico": "NO", "justificacion": mensaje, "beneficio": None, "tiempo": time.perf_counter() - inicio, "error": mensaje}
    if estructura:
        resultado["estructura_xml"] = {k: v for k, v in estructura.items() if k != "texto_relevante"}
    return resultado


def _local(etiqueta):
    return etiqueta.rsplit("}", 1)[-1]


def _buscar(raiz, nombre):
    return next((e for e in raiz.iter() if _local(e.tag) == nombre), None)


def _jerarquia(raiz, profundidad=3):
    def recorrer(elemento, nivel):
        if nivel >= profundidad:
            return {_local(elemento.tag): []}
        return {_local(elemento.tag): [recorrer(hijo, nivel + 1) for hijo in list(elemento)]}
    return recorrer(raiz, 0)


def _normalizar(texto):
    texto = "".join(c for c in unicodedata.normalize("NFD", str(texto).casefold()) if unicodedata.category(c) != "Mn")
    return " ".join(texto.split())


def _texto_nodo(nodo):
    return nodo.get_text(" ", strip=True) if nodo else None


def _descripcion_muestra():
    return "Cinco falsos negativos obligatorios y cinco contrastes: Administración Local, multiconvocatoria, probable no convocatoria y REVISAR, distribuidos entre enero y diciembre de 2004. URLs HTML/XML obtenidas exclusivamente de la API."


def _ruta_unica(ruta):
    candidata = ruta; numero = 1
    while candidata.exists():
        candidata = ruta.with_name(f"{ruta.stem}_{numero}{ruta.suffix}"); numero += 1
    return candidata


def _guardar_atomico(destino, contenido):
    temporal = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=destino.parent, delete=False) as archivo:
            temporal = Path(archivo.name); archivo.write(contenido); archivo.flush(); os.fsync(archivo.fileno())
        os.replace(temporal, destino)
    except BaseException:
        if temporal: temporal.unlink(missing_ok=True)
        raise


def _markdown(detalles, resumen, integridad):
    lineas = ["# Análisis experimental XML BOE 2004", "", "## Resumen ejecutivo", "", f"- Publicaciones analizadas: {resumen['publicaciones_analizadas']}", f"- XML válidos: {resumen['XML_VALIDO']}", f"- XML no disponibles: {resumen['XML_NO_DISPONIBLE']}", f"- Errores: {resumen['errores']}", "", "## Muestra analizada", "", _descripcion_muestra()]
    lineas.extend(["", "| Publicacion_ID | Fecha | Departamento | Estado |", "|---|---|---|---|"])
    lineas.extend(f"| {d['Publicacion_ID']} | {d['Fecha']} | {d.get('departamento') or ''} | {d['estado']} |" for d in detalles)
    lineas.extend(["", "## Estructura XML", "", "Se registran raíz, namespaces, jerarquía, etiquetas, atributos y bloques repetidos por publicación.", "", "## Elementos y metadatos", "", "Los metadatos y elementos observados se conservan completos en el JSON.", "", "## Comparación XML vs HTML", ""])
    for d in detalles:
        if d.get("comparacion_html_xml"):
            c = d["comparacion_html_xml"]
            lineas.append(f"- {d['Publicacion_ID']}: similitud {c['similitud_textual']:.3f}; contenido esencialmente igual: {c['contenido_esencialmente_igual']}")
    lineas.extend(["", "## Análisis por campo", "", "| Publicacion_ID | " + " | ".join(CAMPOS) + " |", "|---|" + "---|" * len(CAMPOS)])
    for d in detalles:
        soporte = (d.get("estructura_xml") or {}).get("soporte_campos", {})
        lineas.append("| " + d["Publicacion_ID"] + " | " + " | ".join(soporte.get(c, "-") for c in CAMPOS) + " |")
    lineas.extend(["", "## Casos de falsos negativos", "", "| Publicacion_ID | HTML extractor actual | XML tiene estructura útil | Campos estructurados | ¿XML evitaría regex histórico? | Justificación |", "|---|---|---|---|---|---|"])
    for d in detalles:
        if d["Publicacion_ID"] in OBLIGATORIAS:
            soporte = d.get("estructura_xml", {}).get("soporte_campos", {})
            estructurados = ", ".join(c for c, v in soporte.items() if v == "ESTRUCTURADO") or "ninguno"
            lineas.append(f"| {d['Publicacion_ID']} | SIN_RESULTADOS | {d.get('beneficio') or '-'} | {estructurados} | {d['xml_evitaria_regex_historico']} | {d['justificacion']} |")
    lineas.extend(["", "## Ventajas del XML", "", "Metadatos explícitos, jerarquía validable y bloques de texto delimitados.", "", "## Limitaciones del XML", "", "Los campos de convocatoria pueden seguir dentro de texto libre o tablas que requieren interpretación.", "", "## Recomendación arquitectónica", ""])
    completo = resumen["beneficios"].get("EXTRACTOR_XML_COMPLETO", 0); hibrido = resumen["beneficios"].get("HIBRIDO_XML_TEXTO", 0)
    if completo:
        lineas.append("Investigar un extractor XML completo para los casos con puesto y plazas estructurados.")
    elif hibrido:
        lineas.append("Priorizar un enfoque híbrido: XML para metadatos y delimitación; análisis textual para los campos funcionales.")
    else:
        lineas.append("Mantener HTML/texto: la muestra no muestra estructura XML funcional suficiente.")
    lineas.extend(["", "## Integridad del Excel", "", f"- Antes: `{integridad['antes']}`", f"- Después: `{integridad['despues']}`", f"- Sin cambios: **{integridad['sin_cambios']}**", ""])
    return "\n".join(lineas)


if __name__ == "__main__":
    main()
