"""Extractor histórico híbrido experimental y estrictamente de solo lectura."""

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import re
import unicodedata
from xml.etree import ElementTree

import requests

from analizar_xml_boe import MUESTRA_2004, analizar_xml, integridad_excel, obtener_muestra_api
from extraer_tablas_xml_boe import extraer_bloques_tabla_estructurados, extraer_resultados_tabla, identificar_columnas, parsear_tablas_xml


CAMPOS = [
    "Puesto", "Num_plazas", "Turno", "Sistema", "Escala", "Subescala",
    "Clase", "Administración", "Fecha_boe", "Publicacion_ID", "Enlace",
]
FUENTES = {"XML_METADATA", "XML_TABLE", "HISTORICAL_TEXT", "CONTEXT_INHERITANCE", "TABLE_STRUCTURE_INHERITANCE"}
CONFIANZAS_ADMITIDAS = {"ALTA", "MEDIA"}
PATRONES_NEGATIVOS = (
    r"\blista(?:s)? (?:provisional(?:es)?|definitiva(?:s)?) de (?:personas )?admitid[oa]s",
    r"\brelaci[oó]n (?:definitiva )?de (?:aspirantes )?admitid[oa]s",
    r"\btribunal(?:es)? calificador", r"\bcomisi[oó]n de selecci[oó]n",
    r"\bnombramiento(?:s)?\b", r"\brelaci[oó]n de aprobad[oa]s",
    r"\bresultado(?:s)? final(?:es)?\b", r"\bcorrecci[oó]n de errores\b",
    r"\bdeclara concluido el procedimiento\b", r"\bse ampl[ií]a el plazo\b",
)
PATRONES_POSITIVOS = (
    r"\bse convocan\b", r"\bconvocatoria para cubrir\b",
    r"\bpruebas? selectivas? para cubrir\b", r"\bconvoca(?:r|n)? .*?plazas?\b",
    r"\bn[uú]mero de (?:plazas|vacantes)\b", r"\bconcurso de acceso\b",
    r"\bconvocatoria para proveer\b",
)
PATRONES_NUMERO = (
    r"n[uú]mero de vacantes\s*[:.-]?\s*(\d+|[a-záéíóúñ]+)",
    r"n[uú]mero de plazas\s*[:.-]?\s*(\d+|[a-záéíóúñ]+)",
    r"se convocan\D{0,80}?(\d+|[a-záéíóúñ]+)\s+plazas?",
    r"pruebas? selectivas? para cubrir\D{0,50}?(\d+|[a-záéíóúñ]+)\s+plazas?",
    r"convocatoria para cubrir\D{0,50}?(\d+|[a-záéíóúñ]+)\s+plazas?",
    r"convoca(?:r|n)?\D{0,80}?(\d+|[a-záéíóúñ]+)\s+plazas?",
    r"(?:cubrir|provisi[oó]n\D{0,30}?de)\D{0,50}?(\d+|[a-záéíóúñ]+)\s+plazas?",
    r"^(\d+|una?|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|cincuenta|ochenta)\s+plazas?\s+de\b",
)
NUMEROS = {"un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
           "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
           "diez": 10, "cincuenta": 50, "ochenta": 80}
UNIDADES = {**NUMEROS, "once": 11, "doce": 12, "trece": 13, "catorce": 14,
            "quince": 15, "dieciseis": 16, "diecisiete": 17, "dieciocho": 18,
            "diecinueve": 19, "veinte": 20, "veintiuno": 21, "veintidos": 22,
            "veintitres": 23, "veinticuatro": 24, "veinticinco": 25,
            "veintiseis": 26, "veintisiete": 27, "veintiocho": 28,
            "veintinueve": 29}
DECENAS = {"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
           "setenta": 70, "ochenta": 80, "noventa": 90}
CANTIDAD_NUMERICA = r"(?:\d{1,3}(?:[. ]\d{3})+|\d+)"
CANTIDAD_TEXTO = r"(?:[a-záéíóúñ]+(?:\s+y)?(?:\s+[a-záéíóúñ]+){0,3})"
CANTIDAD = rf"(?:{CANTIDAD_NUMERICA}|{CANTIDAD_TEXTO})"
PATRON_CANTIDAD_PLAZAS = re.compile(rf"(?P<valor>{CANTIDAD})\s+plazas?\b", re.I)
PATRON_CANTIDAD_COMPONENTE = re.compile(
    r"(\d+|una?|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|cincuenta|ochenta)\s+plazas?"
    r"(?:\s+(?:para cubrir )?(?:de|por|en el|por el sistema(?: general)? de))?\s+"
    r"(turno libre|acceso libre|promoci[oó]n interna|movilidad)\b", re.I)
PATRON_CANTIDAD_TOTAL = re.compile(
    r"(?:total(?:\s+de)?|se convocan(?:\s+pruebas? selectivas? para cubrir)?)\D{0,50}?"
    r"(\d+|una?|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|cincuenta|ochenta)\s+plazas?", re.I)
PATRON_DISTRIBUCION = re.compile(r"\b(?:distribu(?:idas|yen|ci[oó]n)|de las cuales|siguiente distribuci[oó]n)\b", re.I)
PATRON_SUBCUPO = re.compile(
    r"(?:de las cuales|de ellas|reserv[aá]ndose|con reserva de|incluidas?)\s+"
    r"(\d+|una?|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|cincuenta|ochenta)\s+plazas?", re.I)


def _normalizar(valor):
    return " ".join(str(valor or "").split())


def _sin_tildes(valor):
    return "".join(c for c in unicodedata.normalize("NFKD", valor.casefold()) if not unicodedata.combining(c))


def _evidencia(campo, valor, fuente, confianza, fragmento):
    return {"campo": campo, "valor": valor, "fuente": fuente,
            "confianza": confianza, "fragmento_evidencia": _normalizar(fragmento)}


def clasificar_documento(titulo, texto):
    """Clasifica antes de extraer, usando señales positivas y negativas generales."""
    contenido = _normalizar(f"{titulo or ''} {texto or ''}")
    titulo_normalizado = _normalizar(titulo)
    negativas_titulo = [p for p in PATRONES_NEGATIVOS if re.search(p, titulo_normalizado, re.I)]
    positivas = [p for p in PATRONES_POSITIVOS if re.search(p, contenido, re.I)]
    if negativas_titulo:
        return "NO_CONVOCATORIA", negativas_titulo
    if positivas:
        return "CONVOCATORIA", positivas
    if any(re.search(p, contenido, re.I) for p in PATRONES_NEGATIVOS):
        return "INDETERMINADO", ["señal negativa solo en el cuerpo"]
    return "INDETERMINADO", []


def detectar_bloques_convocatoria(texto):
    """Localiza ventanas de párrafos alrededor de señales de plazas."""
    parrafos = [_normalizar(p) for p in str(texto or "").splitlines() if _normalizar(p)]
    if not parrafos and _normalizar(texto):
        parrafos = [_normalizar(texto)]
    indices = [i for i, p in enumerate(parrafos) if any(re.search(patron, p, re.I) for patron in PATRONES_NUMERO)]
    ventanas = []
    for posicion, indice in enumerate(indices):
        anterior = indices[posicion - 1] if posicion else -1
        siguiente = indices[posicion + 1] if posicion + 1 < len(indices) else len(parrafos)
        inicio = max(anterior + 1, indice - 2, 0)
        fin = min(siguiente, indice + 4, len(parrafos))
        ventanas.append((inicio, fin))
    bloques = ["\n".join(parrafos[inicio:fin]) for inicio, fin in ventanas]
    if not bloques:
        continuo = _normalizar(texto)
        hallazgos = [m for patron in PATRONES_NUMERO for m in re.finditer(patron, continuo, re.I)]
        if hallazgos:
            primero = min(hallazgos, key=lambda m: m.start())
            bloques = [continuo[max(0, primero.start() - 250):primero.end() + 350]]
    return bloques


def _etiqueta_local(etiqueta):
    return etiqueta.rsplit("}", 1)[-1].casefold()


PATRON_PUESTO_CANTIDAD = re.compile(
    rf"(?P<valor>{CANTIDAD})\s+plazas?(?:\s+vacantes)?\s+(?:de|del cuerpo de)\s+"
    r"(?P<puesto>[A-ZÁÉÍÓÚÑ][^.;:\n]{2,140})(?=[.;]|$)", re.I)
PATRON_NUMERO_ETIQUETADO = re.compile(
    rf"(?:n[uú]mero|n[.ºo])\s+de\s+(?:plazas|vacantes)\s*[:.-]?\s*(?P<valor>{CANTIDAD})(?=\s*(?:plazas?|[.;]|$))", re.I)
PATRON_ENCABEZADO_CANTIDAD = re.compile(
    rf"(?:^|\s)(?:\d+\.|[A-ZÁÉÍÓÚÑ]\))?\s*(?P<puesto>[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ /-]{{2,100}})\s*:\s*(?P<valor>{CANTIDAD})\s+plazas?\b")
ENCABEZADOS_NO_PUESTO = {"sector publico", "sector privado", "total", "turno libre", "promocion interna", "movilidad"}
PREFIJOS_NO_PUESTO = ("la seccion", "formacion", "cubrir", "primera", "total")


def _es_titulo_bloque(texto):
    """Acepta encabezados breves explícitos, no descripciones funcionales."""
    texto = _normalizar(texto)
    return bool(texto and len(texto) <= 120 and not re.search(r"[.;:]|\b(plazas?|vacantes|art[ií]culo|resoluci[oó]n|anexo)\b", texto, re.I)
                and re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", texto))


def _es_encabezado_puesto(texto):
    """Distingue un encabezado de puesto de contexto opcional estructural."""
    texto = _normalizar(texto)
    if not _es_titulo_bloque(texto) or len(texto) > 70:
        return False
    if re.match(r"^(?:subescala|clase|turno|sistema|bases?|normas?|anexo|disposiciones?|organizaci[oó]n|funcionamiento|programa|temario)\b|^escala\s+de\b", texto, re.I):
        return False
    # Un encabezado de puesto no es una proposición narrativa ni una referencia.
    if re.search(r"\b(?:se|por|para|con|de fecha|real decreto|ley|art[ií]culo|formaci[oó]n)\b", texto, re.I):
        return False
    palabras = [p for p in re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]+", texto) if p.casefold() not in {"de", "del", "la", "el", "y"}]
    return bool(palabras) and len(palabras) <= 4 and all(p[0].isupper() for p in palabras)


def _bloque_desde_texto(texto, origen, posicion, contexto=None):
    """Construye un bloque solo con evidencia local y explícita."""
    texto = _normalizar(texto)
    extraido = extraer_campos_bloque(texto)
    campos, evidencias = extraido["campos"], list(extraido["evidencias"])
    # El extractor anterior aporta contexto opcional, pero el segmentador solo
    # acepta Puesto si su bloque contiene una asociación explícita y local.
    campos["Puesto"] = None
    evidencias = [e for e in evidencias if e["campo"] != "Puesto"]
    encabezado = PATRON_ENCABEZADO_CANTIDAD.search(texto)
    if encabezado:
        puesto = _normalizar(encabezado.group("puesto"))
        cantidad = _convertir_cantidad(encabezado.group("valor"))
        if cantidad is not None:
            campos["Num_plazas"] = cantidad
            evidencias.append(_evidencia("Num_plazas", cantidad, "HISTORICAL_TEXT", "ALTA", encabezado.group(0)))
        if _sin_tildes(puesto) not in ENCABEZADOS_NO_PUESTO and cantidad is not None:
            campos["Puesto"], campos["Num_plazas"] = puesto, cantidad
            evidencias += [
                _evidencia("Puesto", puesto, "HISTORICAL_TEXT", "ALTA", encabezado.group(0)),
            ]
    for hallazgo in PATRON_PUESTO_CANTIDAD.finditer(texto):
        cantidad = _convertir_cantidad(hallazgo.group("valor"))
        if cantidad is not None:
            puesto = _normalizar(hallazgo.group("puesto"))
            if not _sin_tildes(puesto).startswith(PREFIJOS_NO_PUESTO):
                campos["Puesto"] = puesto
                campos["Num_plazas"] = cantidad
                evidencias += [
                    _evidencia("Puesto", puesto, "HISTORICAL_TEXT", "ALTA", hallazgo.group(0)),
                    _evidencia("Num_plazas", cantidad, "HISTORICAL_TEXT", "ALTA", hallazgo.group(0)),
                ]
            break
    if campos["Num_plazas"] is None:
        numero = PATRON_NUMERO_ETIQUETADO.search(texto)
        if numero:
            cantidad = _convertir_cantidad(numero.group("valor"))
            if cantidad is not None:
                campos["Num_plazas"] = cantidad
                evidencias.append(_evidencia("Num_plazas", cantidad, "HISTORICAL_TEXT", "ALTA", numero.group(0)))
    if contexto and campos["Puesto"] is None:
        campos["Puesto"] = contexto
        evidencias.append(_evidencia("Puesto", contexto, "HISTORICAL_TEXT", "ALTA", contexto))
    return {"origen": origen, "posicion": posicion, "texto": texto,
            "campos": campos, "evidencias": evidencias}


def segmentar_estructura_historica(contenido_xml):
    """Segmenta XML conservando el orden de párrafos y filas de tabla.

    El resultado no infiere convocatorias: cada bloque conserva su procedencia,
    posición y las evidencias locales que permiten asociar puesto y cantidad.
    """
    try:
        raiz = ElementTree.fromstring(contenido_xml)
    except ElementTree.ParseError as error:
        raise ValueError(f"XML inválido: {error}") from error
    nodo_texto = next((n for n in raiz.iter() if _etiqueta_local(n.tag) == "texto"), None)
    if nodo_texto is None:
        raise LookupError("No existe el bloque texto")
    bloques, previo, encabezado_activo, grupo, seccion = [], None, None, 0, 0
    tablas = iter(parsear_tablas_xml(contenido_xml))
    indice_tabla = 0
    for posicion, nodo in enumerate(nodo_texto.iter()):
        etiqueta = _etiqueta_local(nodo.tag)
        if etiqueta == "p":
            texto = _normalizar(" ".join(nodo.itertext()))
            if not texto:
                continue
            if re.match(r"^(?:anexo|t[ií]tulo|cap[ií]tulo)\b", texto, re.I):
                seccion += 1
                previo, encabezado_activo = texto, None
                continue
            if _es_titulo_bloque(texto):
                if _es_encabezado_puesto(texto):
                    grupo += 1
                    encabezado_activo = texto
                    bloques.append({"tipo": "CONTEXTO", "origen": "PARRAFO", "posicion": posicion,
                                   "texto": texto, "campos": {campo: None for campo in CAMPOS},
                                   "evidencias": [], "contexto_anterior": previo,
                                   "encabezado_local": texto, "bloque_padre": grupo,
                                   "section_id": seccion, "parent_section": None})
                previo = texto
                continue
            contexto = previo if PATRON_NUMERO_ETIQUETADO.search(texto) and _es_titulo_bloque(previo) else None
            bloque = _bloque_desde_texto(texto, "PARRAFO", posicion, contexto)
            if bloque["campos"]["Puesto"] is not None or bloque["campos"]["Num_plazas"] is not None:
                bloque.update({"tipo": "DATOS", "contexto_anterior": previo,
                               "encabezado_local": encabezado_activo, "bloque_padre": grupo})
                bloque.update({"section_id": seccion, "parent_section": None})
                bloques.append(bloque)
            previo = texto
        elif etiqueta == "table":
            tabla = next(tablas, None)
            if tabla is None:
                continue
            grupo += 1
            for bloque_tabla in extraer_bloques_tabla_estructurados(tabla):
                fila_indice, fila, estructura_fila = (bloque_tabla["fila_indice"], bloque_tabla["campos"],
                                                       bloque_tabla["estructura"])
                evidencias = [_evidencia(campo, valor, "XML_TABLE", "ALTA", f"{campo}: {valor}")
                              for campo, valor in fila.items() if valor is not None]
                campos = {campo: None for campo in CAMPOS}
                campos.update(fila)
                bloques.append({"origen": "TABLA", "posicion": posicion,
                               "tipo": "DATOS", "contexto_anterior": None,
                               "encabezado_local": None, "bloque_padre": grupo,
                               "section_id": seccion, "parent_section": None,
                               "tabla_indice": indice_tabla, "fila_indice": fila_indice,
                               "estructura_tabla": estructura_fila,
                               "grupo_padre_tabla": estructura_fila["grupo_padre"],
                               "nivel_jerarquico_tabla": estructura_fila["nivel_jerarquico"],
                               "heredable_contexto_tabla": bool(
                                   estructura_fila["grupo_padre"] and not estructura_fila["es_grupo"]
                                   and any(c["heredada"] and c["rowspan"] > 1 for c in estructura_fila["celdas"])
                               ),
                               "texto": " | ".join(tabla["filas"][fila_indice]) if fila_indice < len(tabla["filas"]) else "",
                               "campos": campos, "evidencias": evidencias})
            indice_tabla += 1
    return bloques


def clasificar_bloque_historico(bloque):
    campos = bloque["campos"]
    if campos.get("Puesto") and campos.get("Num_plazas") is not None:
        return "VALIDA"
    if campos.get("Puesto") or campos.get("Num_plazas") is not None:
        return "VALIDA_PARCIAL"
    return "NO_UTILIZABLE"


def componer_contexto_bloques(bloques):
    """Hereda exclusivamente un puesto único dentro de su grupo estructural.

    Nunca usa distancia textual: el grupo se delimita por encabezados claros o
    por tabla. Al existir más de un candidato, el bloque queda sin modificar y
    se marca ``CONTEXTO_AMBIGUO`` para revisión.
    """
    compuestos = deepcopy(bloques)
    candidatos, candidatos_tabla = {}, {}
    aceptadas, ambiguas = [], []
    for bloque in compuestos:
        if bloque.get("tipo") == "CONTEXTO":
            candidatos[bloque["bloque_padre"]] = [bloque["encabezado_local"]]
            continue
        if bloque.get("tipo") != "DATOS":
            continue
        campos = bloque["campos"]
        grupo = bloque.get("bloque_padre")
        clave_tabla = (bloque.get("tabla_indice"), grupo) if bloque["origen"] == "TABLA" else None
        almacen = candidatos_tabla if clave_tabla is not None else candidatos
        clave = clave_tabla if clave_tabla is not None else grupo
        actuales = almacen.setdefault(clave, [])
        if campos.get("Puesto"):
            if campos["Puesto"] not in actuales:
                actuales.append(campos["Puesto"])
            continue
        if campos.get("Num_plazas") is None:
            continue
        grupo_tabla = bloque.get("grupo_padre_tabla") if clave_tabla is not None else None
        if clave_tabla is not None and grupo_tabla and not bloque.get("heredable_contexto_tabla", False):
            # Una fila agrupadora explícita (colspan/sin cantidad) es un padre
            # demostrable, incluso si no se apoya en una celda rowspan.
            campos["Puesto"] = grupo_tabla
            bloque["evidencias"].append(_evidencia(
                "Puesto", grupo_tabla, "TABLE_STRUCTURE_INHERITANCE", "ALTA", grupo_tabla))
            bloque["herencia_contextual"] = {"puesto": grupo_tabla, "contexto": grupo_tabla,
                                             "grupo": grupo, "confianza": "ALTA"}
            aceptadas.append(bloque)
        elif clave_tabla is not None and not bloque.get("heredable_contexto_tabla", False):
            bloque["diagnostico_contexto"] = "CONTEXTO_AMBIGUO"
            ambiguas.append(bloque)
        elif len(actuales) == 1:
            puesto = actuales[0]
            evidencia_contexto = bloque.get("encabezado_local") or puesto
            campos["Puesto"] = puesto
            bloque["evidencias"].append(_evidencia(
                "Puesto", puesto, "CONTEXT_INHERITANCE", "ALTA", evidencia_contexto))
            bloque["herencia_contextual"] = {"puesto": puesto, "contexto": evidencia_contexto,
                                             "grupo": grupo, "confianza": "ALTA"}
            aceptadas.append(bloque)
        else:
            bloque["diagnostico_contexto"] = "CONTEXTO_AMBIGUO" if len(actuales) > 1 else "SIN_CONTEXTO_HEREDABLE"
            if len(actuales) > 1:
                ambiguas.append(bloque)
    return {"bloques": compuestos, "herencias_aceptadas": aceptadas,
            "contextos_ambiguos": ambiguas}


def extraer_segmentado_desde_contenido(publicacion_id, contenido_xml, url_xml, url_html=None):
    """Prototipo de segmentación; no altera el extractor histórico existente."""
    estructura = analizar_xml(contenido_xml)
    metadatos = estructura["metadatos"]
    metadatos.setdefault("identificador", publicacion_id)
    enlace = url_html or url_xml
    bloques = segmentar_estructura_historica(contenido_xml)
    filas, evidencias = [], []
    vistos = set()
    for bloque in bloques:
        calidad = clasificar_bloque_historico(bloque)
        bloque["calidad"] = calidad
        if calidad == "NO_UTILIZABLE":
            continue
        fila = _convocatoria_desde_evidencias(list(bloque["evidencias"]), metadatos, enlace)
        firma = (fila.get("Puesto"), fila.get("Num_plazas"), bloque["origen"], bloque.get("posicion"))
        if firma in vistos:
            continue
        vistos.add(firma); filas.append(fila); evidencias.append(bloque["evidencias"])
    reconciliacion = reconciliar_cantidades(detectar_cantidades(estructura["texto_relevante"]))
    return {"publicacion_id": publicacion_id, "bloques": bloques, "convocatorias": filas,
            "evidencias": evidencias, "reconciliacion": reconciliacion,
            "metadatos": metadatos}


def extraer_compuesto_desde_contenido(publicacion_id, contenido_xml, url_xml, url_html=None):
    """Segmentación más composición contextual experimental, sin efectos externos."""
    segmentado = extraer_segmentado_desde_contenido(publicacion_id, contenido_xml, url_xml, url_html)
    composicion = componer_contexto_bloques(segmentado["bloques"])
    metadatos, enlace = segmentado["metadatos"], url_html or url_xml
    filas, evidencias, vistos = [], [], set()
    for bloque in composicion["bloques"]:
        if bloque.get("tipo") != "DATOS":
            continue
        bloque["calidad"] = clasificar_bloque_historico(bloque)
        if bloque["calidad"] == "NO_UTILIZABLE":
            continue
        fila = _convocatoria_desde_evidencias(list(bloque["evidencias"]), metadatos, enlace)
        firma = (fila.get("Puesto"), fila.get("Num_plazas"), bloque["origen"], bloque.get("posicion"))
        if firma not in vistos:
            vistos.add(firma); filas.append(fila); evidencias.append(bloque["evidencias"])
    return {**segmentado, "bloques": composicion["bloques"], "convocatorias": filas,
            "evidencias": evidencias, "herencias_aceptadas": composicion["herencias_aceptadas"],
            "contextos_ambiguos": composicion["contextos_ambiguos"]}


def _buscar_primero(patrones, texto, campo, transformacion=lambda x: x, confianza="ALTA"):
    for patron in patrones:
        coincidencia = re.search(patron, texto, re.I | re.S)
        if coincidencia:
            valor = transformacion(coincidencia.group(1))
            return _evidencia(campo, valor, "HISTORICAL_TEXT", confianza, coincidencia.group(0))
    return None


def _convertir_cantidad(valor):
    texto = _sin_tildes(_normalizar(valor))
    if re.fullmatch(r"\d{1,3}(?:[. ]\d{3})+|\d+", texto):
        return int(texto.replace(".", "").replace(" ", ""))
    if texto in NUMEROS:
        return NUMEROS[texto]
    palabras = [p for p in texto.split() if p != "y"]
    if not palabras:
        return None
    if "mil" in palabras:
        indice = palabras.index("mil")
        previo = _convertir_cantidad(" ".join(palabras[:indice])) if indice else 1
        posterior = _convertir_cantidad(" ".join(palabras[indice + 1:])) if palabras[indice + 1:] else 0
        return previo * 1000 + posterior if previo is not None and posterior is not None else None
    if len(palabras) == 2 and palabras[0] in DECENAS and palabras[1] in UNIDADES:
        return DECENAS[palabras[0]] + UNIDADES[palabras[1]]
    return UNIDADES.get(texto) or DECENAS.get(texto)


def detectar_cantidades(texto):
    """Representa cantidades textuales sin reconciliarlas ni mutar el texto."""
    continuo = _normalizar(texto)
    hallazgos, vistos = [], set()
    for coincidencia in PATRON_CANTIDAD_PLAZAS.finditer(continuo):
        valor = _convertir_cantidad(coincidencia.group("valor"))
        if valor is None or coincidencia.span() in vistos:
            continue
        vistos.add(coincidencia.span())
        inicio_alrededor = max(0, coincidencia.start() - 180)
        alrededor = continuo[inicio_alrededor:coincidencia.end() + 240]
        posicion_local = coincidencia.start() - inicio_alrededor
        componentes_contexto = [
            m for m in PATRON_CANTIDAD_COMPONENTE.finditer(alrededor)
            if _convertir_cantidad(m.group(1)) == valor and m.start(1) <= posicion_local <= m.end(1)
        ]
        componente = componentes_contexto[0] if componentes_contexto else None
        total = PATRON_CANTIDAD_TOTAL.search(alrededor)
        tipo = "COMPONENTE" if componente and _convertir_cantidad(componente.group(1)) == valor else "DESCONOCIDO"
        if total and _convertir_cantidad(total.group(1)) == valor:
            tipo = "TOTAL"
        contexto = extraer_campos_bloque(alrededor)["campos"]
        turno = None
        if componente and _convertir_cantidad(componente.group(1)) == valor:
            turno = "Turno libre" if _sin_tildes(componente.group(2)) == "acceso libre" else _normalizar(componente.group(2)).capitalize()
            contexto["Turno"] = turno
        hallazgos.append({
            "valor": valor, "fragmento": coincidencia.group(0), "posicion": coincidencia.start(),
            "fuente": "HISTORICAL_TEXT", "Puesto": contexto.get("Puesto"),
            "Turno": turno or contexto.get("Turno"), "Sistema": contexto.get("Sistema"),
            "Escala": contexto.get("Escala"), "Subescala": contexto.get("Subescala"),
            "Clase": contexto.get("Clase"), "tipo_inicial": tipo,
            "confianza": "ALTA" if tipo in {"TOTAL", "COMPONENTE"} else "BAJA",
            "evidencia": alrededor,
            "relacion_distribucion": bool(PATRON_DISTRIBUCION.search(continuo[coincidencia.start():coincidencia.start() + 2500])),
        })
    for coincidencia in PATRON_SUBCUPO.finditer(continuo):
        valor = _convertir_cantidad(coincidencia.group(1))
        if valor is None:
            continue
        candidatos = [(i, cantidad) for i, cantidad in enumerate(hallazgos)
                       if cantidad["posicion"] < coincidencia.start()
                       and cantidad["tipo_inicial"] == "COMPONENTE"]
        previo = max(candidatos, key=lambda item: item[1]["posicion"])[0] if candidatos else None
        if previo is None:
            continue
        hallazgos.append({
            "valor": valor, "fragmento": coincidencia.group(0), "posicion": coincidencia.start(),
            "fuente": "HISTORICAL_TEXT", "Puesto": None, "Turno": None, "Sistema": None,
            "Escala": None, "Subescala": None, "Clase": None, "tipo_inicial": "SUBCUPO",
            "confianza": "ALTA", "evidencia": coincidencia.group(0), "incluido_en": previo,
            "relacion_distribucion": True,
        })
    hallazgos.sort(key=lambda cantidad: cantidad["posicion"])
    return hallazgos


def reconciliar_cantidades(cantidades):
    """Reconciliación conservadora de totales explícitos y sus componentes.

    Solo descarta un total si éste declara una distribución y sus componentes
    posteriores, claramente marcados por turno, suman exactamente ese total.
    """
    cantidades_copia = deepcopy(cantidades)
    grupos, descartadas = [], set()
    for indice, total in enumerate(cantidades_copia):
        if total.get("tipo_inicial") != "TOTAL" or not total.get("relacion_distribucion"):
            continue
        componentes = [
            (i, c) for i, c in enumerate(cantidades_copia)
            if c.get("tipo_inicial") == "COMPONENTE" and c.get("posicion", -1) > total.get("posicion", -1)
            and c.get("posicion", 0) - total.get("posicion", 0) <= 2500
        ]
        if not componentes:
            continue
        suma = sum(c["valor"] for _, c in componentes)
        decision = "TOTAL_DESGLOSADO" if suma == total["valor"] else "AMBIGUO"
        grupos.append({"total_indice": indice, "total": total, "componentes_indices": [i for i, _ in componentes],
                       "componentes": [c for _, c in componentes], "suma_componentes": suma,
                       "subcupos_indices": [i for i, c in enumerate(cantidades_copia) if c.get("tipo_inicial") == "SUBCUPO"
                                            and c.get("incluido_en") in [x for x, _ in componentes]],
                       "subcupos": [c for c in cantidades_copia if c.get("tipo_inicial") == "SUBCUPO"
                                    and c.get("incluido_en") in [x for x, _ in componentes]],
                       "decision": decision, "evidencia": total.get("evidencia")})
        if decision == "TOTAL_DESGLOSADO":
            descartadas.add(indice)
    funcionales = [c for i, c in enumerate(cantidades_copia) if i not in descartadas]
    subcupos = [c for c in cantidades_copia if c.get("tipo_inicial") == "SUBCUPO"]
    return {"estado": "TOTAL_DESGLOSADO" if any(g["decision"] == "TOTAL_DESGLOSADO" for g in grupos)
                       else "AMBIGUO" if any(g["decision"] == "AMBIGUO" for g in grupos) else "SIN_RECONCILIACION",
            "cantidades": cantidades_copia, "grupos": grupos, "cantidades_funcionales": funcionales,
            "totales_descartados": [cantidades_copia[i] for i in sorted(descartadas)],
            "subcupos_incluidos": subcupos,
            "tipos_relacion": (["SUBCUPO_INCLUIDO"] if subcupos else []) + ([g["decision"] for g in grupos])}


def extraer_campos_bloque(bloque):
    """Extrae campos y evidencias de un bloque, sin completar valores dudosos."""
    texto = _normalizar(bloque)
    evidencias = []
    numero = _buscar_primero(PATRONES_NUMERO, texto, "Num_plazas", _convertir_cantidad)
    if numero:
        evidencias.append(numero)
    patrones_puesto = (
        # Denominaciones laborales explícitas. El descriptor "personal laboral"
        # no se usa como Puesto cuando la categoría concreta está presente.
        r"\bcategor[ií]a(?:\s+profesional)?\s+(?:de\s+)?([A-ZÁÉÍÓÚÑ][^.;,:\n]{2,100})",
        # Lista textual local: cada denominación queda ligada a su cantidad por
        # la misma coma, sin heredar contexto entre elementos.
        r"(?:^|[.:;]\s*)([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ /-]{2,100}?),\s*(?:\d+|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+plazas?\b",
        r"plazas?\s+de\s+la\s+Escala\s+de\s+([^.;,(\n]{3,100})",
        r"(?:plazas?|vacantes)\s+(?:de|del cuerpo de|de la categor[ií]a de)\s+(?!acceso\b|turno\b|promoci[oó]n\b|movilidad\b)([A-ZÁÉÍÓÚÑ][^.;,:\n]{2,100})",
        r"(?:pruebas? selectivas? para (?:el ingreso|acceso)|convocatoria para cubrir plazas?)\s+en (?:el|la)\s+([^.;:\n]{3,100})",
        r"^\s*([A-ZÁÉÍÓÚÑ][^.;:\n]{2,80})\.\s*Personal\s+(?:funcionario|laboral)",
    )
    puesto = _buscar_primero(patrones_puesto, texto, "Puesto", lambda x: _normalizar(x), "MEDIA")
    if puesto:
        evidencias.append(puesto)
    for campo, patron in (
        ("Escala", r"\bEscala\s+(?:de\s+)?(.{3,100}?)(?=\s+con sujeci[oó]n|\s+por el sistema|[.;,:\n])"),
        ("Subescala", r"\bSubescala\s+(?:de\s+)?([^.;,:\n]{3,100})"),
        ("Clase", r"\bClase\s+(?:de\s+)?([^.;,:\n]{2,100})"),
    ):
        hallazgo = _buscar_primero((patron,), texto, campo, lambda x: _normalizar(x), "MEDIA")
        if hallazgo:
            evidencias.append(hallazgo)
    turno = _buscar_primero((r"\b(turno libre)\b", r"\b(promoci[oó]n interna)\b", r"\b(movilidad)\b"), texto, "Turno", lambda x: _normalizar(x).capitalize(), "ALTA")
    if turno:
        evidencias.append(turno)
    sistema = _buscar_primero((r"\b(concurso[- ]oposici[oó]n)\b", r"\b(concurso de m[eé]ritos)\b", r"\b(oposici[oó]n)\b", r"\b(concurso)\b"), texto, "Sistema", lambda x: _normalizar(x).capitalize(), "ALTA")
    if sistema:
        evidencias.append(sistema)
    valores = {campo: None for campo in CAMPOS}
    diagnostico = []
    for prueba in evidencias:
        if prueba["confianza"] in CONFIANZAS_ADMITIDAS:
            valores[prueba["campo"]] = prueba["valor"]
        else:
            diagnostico.append(prueba)
    return {"campos": valores, "evidencias": evidencias, "diagnostico_baja_confianza": diagnostico}


PATRON_LISTA_DENOMINACION_CANTIDAD = re.compile(
    rf"(?:^|[.:;]\s*)(?P<puesto>[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ /-]{{2,100}}?),\s*"
    rf"(?P<cantidad>{CANTIDAD})\s+plazas?\b")


def extraer_pares_denominacion_cantidad(bloque):
    """Extrae pares explícitos del mismo bloque, sin herencia entre filas."""
    pares = []
    for hallazgo in PATRON_LISTA_DENOMINACION_CANTIDAD.finditer(_normalizar(bloque)):
        cantidad = _convertir_cantidad(hallazgo.group("cantidad"))
        if cantidad is None:
            continue
        puesto = _normalizar(hallazgo.group("puesto"))
        pares.append((puesto, cantidad, hallazgo.group(0)))
    return pares


def _divisiones_turno(bloque):
    patrones = (("Libre", r"(\d+)\s+plazas?\s+(?:de|en el|por el)?\s*turno libre"),
                ("Promoción interna", r"(\d+)\s+plazas?\s+(?:de|en|por)?\s*promoci[oó]n interna"),
                ("Movilidad", r"(\d+)\s+plazas?\s+(?:de|en|por)?\s*movilidad"))
    return [(turno, int(m.group(1)), m.group(0)) for turno, patron in patrones for m in re.finditer(patron, bloque, re.I)]


def _convocatoria_desde_evidencias(evidencias, metadatos, enlace):
    for campo, clave, valor in (("Administración", "departamento", metadatos.get("departamento")),
                                ("Fecha_boe", "fecha_publicacion", metadatos.get("fecha_publicacion")),
                                ("Publicacion_ID", "identificador", metadatos.get("identificador"))):
        if valor is not None and not any(e["campo"] == campo for e in evidencias):
            evidencias.append(_evidencia(campo, valor, "XML_METADATA", "ALTA", f"{clave}: {valor}"))
    campos = {campo: None for campo in CAMPOS}
    for prueba in evidencias:
        if prueba["confianza"] in CONFIANZAS_ADMITIDAS and campos.get(prueba["campo"]) is None:
            campos[prueba["campo"]] = prueba["valor"]
    campos.update({
        "Administración": metadatos.get("departamento"),
        "Fecha_boe": metadatos.get("fecha_publicacion"),
        "Publicacion_ID": metadatos.get("identificador"), "Enlace": enlace,
    })
    return campos


def _convocatoria_desde_cantidad(cantidad, metadatos, enlace):
    evidencias = [_evidencia("Num_plazas", cantidad["valor"], cantidad["fuente"], cantidad["confianza"], cantidad["fragmento"])]
    for campo in ("Puesto", "Turno", "Sistema", "Escala", "Subescala", "Clase"):
        if cantidad.get(campo) is not None:
            evidencias.append(_evidencia(campo, cantidad[campo], cantidad["fuente"], cantidad["confianza"], cantidad["evidencia"]))
    return _convocatoria_desde_evidencias(evidencias, metadatos, enlace), evidencias


def extraer_desde_contenido(publicacion_id, contenido_xml, url_xml, url_html=None):
    """Núcleo comprobable sin red del extractor híbrido."""
    estructura = analizar_xml(contenido_xml)
    metadatos, texto = estructura["metadatos"], estructura["texto_relevante"]
    metadatos.setdefault("identificador", publicacion_id)
    clasificacion, senales = clasificar_documento(metadatos.get("titulo"), texto)
    resultado = {"publicacion_id": publicacion_id, "clasificacion_documento": clasificacion,
                 "convocatorias": [], "evidencias": [], "advertencias": [],
                 "metadatos": {k: metadatos.get(k) for k in ("titulo", "departamento", "fecha_publicacion", "seccion", "subseccion")},
                 "extractor_actual_filas": 0, "filas_antes_reconciliacion": 0,
                 "reconciliacion": {"estado": "SIN_RECONCILIACION", "cantidades": [], "grupos": [], "totales_descartados": []}}
    if clasificacion != "CONVOCATORIA":
        resultado["advertencias"].append("Documento excluido o ambiguo antes de extraer")
        resultado["senales_clasificacion"] = senales
        return resultado
    tablas = parsear_tablas_xml(contenido_xml)
    tabulares = [fila for tabla in tablas for fila in extraer_resultados_tabla(tabla)]
    textos_tabla = {_normalizar(" ".join(tabla["encabezados"] + [celda for fila in tabla["filas"] for celda in fila])) for tabla in tablas}
    texto_sin_tablas = "\n".join(linea for linea in texto.splitlines() if _normalizar(linea) not in textos_tabla)
    reconciliacion = reconciliar_cantidades(detectar_cantidades(texto_sin_tablas))
    resultado["reconciliacion"] = reconciliacion
    bloques = detectar_bloques_convocatoria(texto_sin_tablas)
    if not bloques and any(re.search(p, metadatos.get("titulo", ""), re.I) for p in PATRONES_POSITIVOS):
        bloques = [metadatos.get("titulo", "")]
    textuales = [extraer_campos_bloque(b) for b in bloques]
    categoria_titulo = _buscar_primero(
        (r"\bcategor[ií]a(?:\s+profesional)?\s+(?:de\s+)?([A-ZÁÉÍÓÚÑ][^.;,:\n]{2,100})",),
        metadatos.get("titulo", ""), "Puesto", _normalizar, "ALTA")
    if categoria_titulo:
        for extraido in textuales:
            if _sin_tildes(extraido["campos"].get("Puesto") or "") in {"personal laboral", "personal funcionario", "funcionario", "puesto de trabajo"}:
                extraido["campos"]["Puesto"] = categoria_titulo["valor"]
                extraido["evidencias"] = [e for e in extraido["evidencias"] if e["campo"] != "Puesto"] + [categoria_titulo]
    enlace = url_html or url_xml
    pares_explicitos = extraer_pares_denominacion_cantidad(texto_sin_tablas)
    # Una lista explícita Puesto, cantidad es más específica que sus tablas de
    # especialidades: conserva cada asociación local y evita herencias.
    if len(pares_explicitos) >= 2:
        for puesto, cantidad, fragmento in pares_explicitos:
            ev = [_evidencia("Puesto", puesto, "HISTORICAL_TEXT", "ALTA", fragmento),
                  _evidencia("Num_plazas", cantidad, "HISTORICAL_TEXT", "ALTA", fragmento)]
            resultado["convocatorias"].append(_convocatoria_desde_evidencias(ev, metadatos, enlace))
            resultado["evidencias"].append(ev)
        resultado["filas_antes_reconciliacion"] = len(resultado["convocatorias"])
        return resultado
    if reconciliacion["estado"] == "TOTAL_DESGLOSADO" and not tabulares:
        for grupo in reconciliacion["grupos"]:
            if grupo["decision"] != "TOTAL_DESGLOSADO":
                continue
            for cantidad in grupo["componentes"]:
                convocatoria, evidencias = _convocatoria_desde_cantidad(cantidad, metadatos, enlace)
                resultado["convocatorias"].append(convocatoria)
                resultado["evidencias"].append(evidencias)
    # Una división explícita por turno tiene prioridad sobre el total agregado.
    for bloque, extraido in zip(bloques, textuales):
        if tabulares or reconciliacion["estado"] == "TOTAL_DESGLOSADO":
            continue
        es_total_descartado = (
            extraido["campos"]["Num_plazas"] is not None and extraido["campos"]["Turno"] is None
            and any(total["valor"] == extraido["campos"]["Num_plazas"] for total in reconciliacion["totales_descartados"])
        )
        if es_total_descartado:
            continue
        divisiones = _divisiones_turno(bloque)
        if len(divisiones) >= 2:
            base = [e for e in extraido["evidencias"] if e["campo"] not in {"Num_plazas", "Turno"}]
            for turno, plazas, fragmento in divisiones:
                ev = base + [_evidencia("Num_plazas", plazas, "HISTORICAL_TEXT", "ALTA", fragmento), _evidencia("Turno", turno, "HISTORICAL_TEXT", "ALTA", fragmento)]
                resultado["convocatorias"].append(_convocatoria_desde_evidencias(ev, metadatos, enlace)); resultado["evidencias"].append(ev)
        elif extraido["campos"]["Puesto"] is not None or extraido["campos"]["Num_plazas"] is not None:
            resultado["convocatorias"].append(_convocatoria_desde_evidencias(extraido["evidencias"], metadatos, enlace)); resultado["evidencias"].append(extraido["evidencias"])
    # Las filas tabulares son independientes; el texto solo completa si hay una correspondencia inequívoca.
    if tabulares:
        filas_tabla, evidencias_tabla = [], []
        complemento = textuales[0]["evidencias"] if len(textuales) == 1 and len(tabulares) == 1 else []
        for fila in tabulares:
            ev = [_evidencia(c, v, "XML_TABLE", "ALTA", f"{c}: {v}") for c, v in fila.items() if v is not None]
            existentes = {e["campo"] for e in ev}
            ev += [e for e in complemento if e["campo"] not in existentes]
            filas_tabla.append(_convocatoria_desde_evidencias(ev, metadatos, enlace)); evidencias_tabla.append(ev)
        # Evita duplicar una única fila textual usada solo como complemento.
        if complemento:
            resultado["convocatorias"], resultado["evidencias"] = filas_tabla, evidencias_tabla
        else:
            resultado["convocatorias"].extend(filas_tabla); resultado["evidencias"].extend(evidencias_tabla)
    if not resultado["convocatorias"]:
        resultado["advertencias"].append("Clasificado como convocatoria, pero sin bloques o tablas aprovechables")
    resultado["filas_antes_reconciliacion"] = len(resultado["convocatorias"]) + len(reconciliacion["totales_descartados"])
    return resultado


def extraer_convocatorias_historicas(publicacion_id, url_xml, url_html=None, obtener=requests.get):
    respuesta = obtener(url_xml, timeout=10); respuesta.raise_for_status()
    return extraer_desde_contenido(publicacion_id, respuesta.content, url_xml, url_html)


def resumir(resultados):
    clases = Counter(r["clasificacion_documento"] for r in resultados)
    convocatorias = [c for r in resultados for c in r["convocatorias"]]
    completos = sum(all(c.get(k) is not None for k in ("Puesto", "Num_plazas", "Administración", "Fecha_boe")) for c in convocatorias)
    return {"documentos_analizados": len(resultados), **{k: clases[k] for k in ("CONVOCATORIA", "NO_CONVOCATORIA", "INDETERMINADO")},
            "documentos_con_filas_extraidas": sum(bool(r["convocatorias"]) for r in resultados), "total_convocatorias": len(convocatorias),
            "campos_completos": completos, "campos_parciales": len(convocatorias) - completos,
            "documentos_mejorados": sum(bool(r["convocatorias"]) and r["extractor_actual_filas"] == 0 for r in resultados),
            "falsos_positivos_potenciales": sum(bool(r["convocatorias"]) and any(c.get("Puesto") is None or c.get("Num_plazas") is None for c in r["convocatorias"]) for r in resultados)}


def guardar_informes(resultados, directorio="informes/extractor_historico_2004", momento=None):
    directorio = Path(directorio); directorio.mkdir(parents=True, exist_ok=True)
    momento = momento or datetime.now(); sello = momento.strftime("%Y%m%d_%H%M%S_%f")
    resumen = resumir(resultados)
    datos = {"fecha_ejecucion": momento.isoformat(timespec="seconds"), "resumen": resumen, "documentos": resultados}
    json_path = directorio / f"extractor_historico_2004_{sello}.json"; md_path = directorio / f"extractor_historico_2004_{sello}.md"
    json_path.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    lineas = ["# Extractor histórico híbrido BOE 2004", "", "## Resumen", "", *[f"- {k}: {v}" for k, v in resumen.items()], "", "## Documentos analizados", ""]
    for r in resultados:
        rec = r.get("reconciliacion", {})
        lineas += [f"### {r['publicacion_id']} — {r['clasificacion_documento']}", "", f"Extractor actual: {r['extractor_actual_filas']}; antes de reconciliar: {r.get('filas_antes_reconciliacion', len(r['convocatorias']))}; híbrido: {len(r['convocatorias'])}; reconciliación: {rec.get('estado', 'SIN_RECONCILIACION')}.", ""]
        if rec.get("cantidades"):
            lineas += ["Cantidades detectadas:", "", *[f"- {c['valor']} [{c['tipo_inicial']}] {c['fragmento']}" for c in rec["cantidades"]], ""]
        for grupo in rec.get("grupos", []):
            lineas += [f"Grupo {grupo['decision']}: total {grupo['total']['valor']}; suma componentes {grupo['suma_componentes']}.", ""]
        for i, (c, ev) in enumerate(zip(r["convocatorias"], r["evidencias"]), 1):
            lineas += [f"#### Convocatoria {i}", "", *[f"- {k}: {c.get(k)}" for k in CAMPOS if k not in {"Enlace"}], "", "Evidencias:", "", *[f"- {e['campo']} = {e['valor']} [{e['fuente']}/{e['confianza']}]: {e['fragmento_evidencia']}" for e in ev], ""]
        if r["advertencias"]: lineas += ["Advertencias: " + "; ".join(r["advertencias"]), ""]
    lineas += ["## Falsos negativos corregidos", "", f"{resumen['documentos_mejorados']} documentos con filas frente a cero del extractor actual.", "", "## Falsos positivos potenciales", "", str(resumen["falsos_positivos_potenciales"]), "", "## Limitaciones", "", "Los patrones son conservadores; las tablas sin correspondencia inequívoca no se fusionan y los números escritos con palabras no se convierten.", "", "## Recomendación", "", "Revisar manualmente las evidencias antes de plantear cualquier integración productiva.", ""]
    md_path.write_text("\n".join(lineas), encoding="utf-8")
    return json_path, md_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--salida", default="informes/extractor_historico_2004")
    args = parser.parse_args(argv)
    antes = integridad_excel(); documentos = obtener_muestra_api(limite=10)
    resultados = [extraer_convocatorias_historicas(d["Publicacion_ID"], d["url_xml"], d.get("url_html")) for d in documentos]
    despues = integridad_excel()
    if antes != despues: raise RuntimeError("El Excel cambió durante el análisis experimental")
    rutas = guardar_informes(resultados, args.salida)
    for r in resultados: print(f"{r['publicacion_id']}: actual=0, híbrido={len(r['convocatorias'])}, {r['clasificacion_documento']}")
    print(f"Informes: {rutas[0]} / {rutas[1]}")


if __name__ == "__main__":
    main()
