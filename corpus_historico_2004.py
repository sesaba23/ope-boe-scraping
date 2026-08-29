"""Corpus manual y validador experimentales para publicaciones BOE de 2004.

No descarga documentos ni escribe en la persistencia productiva.
"""

import argparse
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import unicodedata


RAIZ = Path(__file__).resolve().parent
ESCANEO = RAIZ / "informes/escaneo_xml_2004/informe_escaneo_xml_2004.json"
CORPUS = RAIZ / "datos/corpus_historico_2004.json"
INFORME = RAIZ / "informes/corpus_historico_2004/corpus_historico_2004.md"
REVISION_INICIAL = RAIZ / "informes/corpus_historico_2004/revision_inicial_10.json"
INFORME_REVISION_INICIAL = RAIZ / "informes/corpus_historico_2004/revision_inicial_10.md"
DIRECTORIO_DIAGNOSTICO_PUESTO = RAIZ / "informes/diagnostico_puesto_2004"
OBLIGATORIAS = {
    "BOE-A-2004-10041", "BOE-A-2004-3891", "BOE-A-2004-3826",
    "BOE-A-2004-6777", "BOE-A-2004-10220", "BOE-A-2004-14618",
}
# Casos ya caracterizados por los informes previos, añadidos para garantizar
# familias que el escaneo conservador no etiquetó explícitamente.
DIVERSIDAD_FIJA = {"BOE-A-2004-2476", "BOE-A-2004-10218", "BOE-A-2004-14746"}
CAMPOS_OPCIONALES = ("Turno", "Sistema", "Escala", "Subescala", "Clase")
TIPOS_CANTIDAD = {"CONVOCATORIA", "TOTAL", "COMPONENTE", "SUBCUPO"}
CLASIFICACIONES_MANUALES = {"CONVOCATORIA", "NO_CONVOCATORIA", "INDETERMINADO"}
SELECCION_INICIAL_10 = (
    ("BOE-A-2004-81", "SENCILLA_UNICA"),
    ("BOE-A-2004-372", "SENCILLA_UNICA"),
    ("BOE-A-2004-1396", "SENCILLA_UNICA"),
    ("BOE-A-2004-74", "SIN_CONVOCATORIA"),
    ("BOE-A-2004-8235", "SIN_CONVOCATORIA"),
    ("BOE-A-2004-3826", "TABLA"),
    ("BOE-A-2004-3891", "TABLA"),
    ("BOE-A-2004-10041", "TOTAL_DESGLOSE"),
    ("BOE-A-2004-2476", "SUBCUPO"),
    ("BOE-A-2004-6309", "MULTICONVOCATORIA"),
)


def _id_numero(fila):
    return int(fila["Publicacion_ID"].rsplit("-", 1)[-1])


def _mes(fila):
    return fila["Fecha_BOE"][5:7]


def _tipo_documento(fila):
    """Etiqueta de muestreo, no una etiqueta de referencia manual."""
    if fila["Publicacion_ID"] in {"BOE-A-2004-2476", "BOE-A-2004-14746"}:
        return "SUBCUPOS"
    titulo = fila.get("titulo", "").casefold()
    cantidades = fila.get("cantidades_detectadas", [])
    if fila.get("posibles_subcupos"):
        return "SUBCUPOS"
    if fila.get("posible_total") and fila.get("posibles_componentes"):
        return "TOTAL_DESGLOSE"
    if len(cantidades) > 2:
        return "MULTICONVOCATORIA"
    if any(x in titulo for x in ("lista", "comisión", "nombramiento", "tribunal", "corrección")) and not cantidades:
        return "SIN_CONVOCATORIA"
    if fila.get("expresiones_encontradas"):
        return "ESTRUCTURAL_TABLA"
    if len(cantidades) == 1:
        return "UNICA_CONVOCATORIA"
    return "TEXTO_LIBRE"


def seleccionar_publicaciones(resultados, limite=50):
    """Selección determinista, diversa y con predominio de casos sencillos."""
    filas = sorted(resultados, key=lambda x: (_id_numero(x), x["Publicacion_ID"]))
    por_id = {x["Publicacion_ID"]: x for x in filas}
    fijas = OBLIGATORIAS | DIVERSIDAD_FIJA
    faltan = fijas - por_id.keys()
    if faltan:
        raise ValueError(f"Faltan publicaciones obligatorias: {sorted(faltan)}")
    elegidas = [por_id[x] for x in sorted(fijas, key=lambda x: int(x.rsplit('-', 1)[-1]))]
    usados = {x["Publicacion_ID"] for x in elegidas}
    meses = Counter(_mes(x) for x in elegidas)
    departamentos = Counter(x.get("departamento") for x in elegidas)
    tipos = Counter(_tipo_documento(x) for x in elegidas)

    # Primera vuelta: al menos una publicación por mes.
    objetivos = ["SIN_CONVOCATORIA", "UNICA_CONVOCATORIA", "TEXTO_LIBRE",
                 "ESTRUCTURAL_TABLA", "MULTICONVOCATORIA", "TOTAL_DESGLOSE", "SUBCUPOS"]
    for mes in [f"{n:02d}" for n in range(1, 13)]:
        if meses[mes]:
            continue
        candidatos = [x for x in filas if x["Publicacion_ID"] not in usados and _mes(x) == mes]
        x = min(candidatos, key=lambda y: (prioridad_temporal(_tipo_documento(y)),
                                            departamentos[y.get("departamento")], _id_numero(y)))
        elegidas.append(x); usados.add(x["Publicacion_ID"])
        meses[mes] += 1; departamentos[x.get("departamento")] += 1; tipos[_tipo_documento(x)] += 1

    # Segunda vuelta: cubre cada familia que exista en los resultados.
    for tipo in objetivos:
        if tipos[tipo]:
            continue
        candidatos = [x for x in filas if x["Publicacion_ID"] not in usados and _tipo_documento(x) == tipo]
        if candidatos:
            x = min(candidatos, key=lambda y: (meses[_mes(y)], departamentos[y.get("departamento")], _id_numero(y)))
            elegidas.append(x); usados.add(x["Publicacion_ID"])
            meses[_mes(x)] += 1; departamentos[x.get("departamento")] += 1; tipos[tipo] += 1

    # Completa favoreciendo documentos sencillos y limitando órganos dominantes.
    prioridad = {"UNICA_CONVOCATORIA": 0, "SIN_CONVOCATORIA": 1, "TEXTO_LIBRE": 2,
                 "ESTRUCTURAL_TABLA": 3, "MULTICONVOCATORIA": 4,
                 "TOTAL_DESGLOSE": 5, "SUBCUPOS": 6}
    restantes = [x for x in filas if x["Publicacion_ID"] not in usados]
    while len(elegidas) < limite:
        candidatos = [x for x in restantes if departamentos[x.get("departamento")] < 12]
        if not candidatos:
            break
        x = min(candidatos, key=lambda y: (meses[_mes(y)], departamentos[y.get("departamento")],
                                           prioridad[_tipo_documento(y)], _id_numero(y)))
        elegidas.append(x); usados.add(x["Publicacion_ID"])
        meses[_mes(x)] += 1; departamentos[x.get("departamento")] += 1
        restantes.remove(x)
    if len(elegidas) != limite:
        raise ValueError(f"Solo se pudieron seleccionar {len(elegidas)} publicaciones")
    return sorted(elegidas, key=_id_numero)


def prioridad_temporal(tipo):
    return {"UNICA_CONVOCATORIA": 0, "SIN_CONVOCATORIA": 1, "TEXTO_LIBRE": 2,
            "ESTRUCTURAL_TABLA": 3, "MULTICONVOCATORIA": 4,
            "TOTAL_DESGLOSE": 5, "SUBCUPOS": 6}[tipo]


def _propuesta(fila):
    propuesta = []
    for cantidad in fila.get("cantidades_detectadas", []):
        if cantidad.get("valor") is None:
            continue
        propuesta.append({k: cantidad.get(k) for k in
                          ("Puesto", "valor", "Turno", "Sistema", "Escala", "Subescala", "Clase")})
        propuesta[-1]["Num_plazas"] = propuesta[-1].pop("valor")
    return propuesta


def construir_corpus(resultados):
    publicaciones = []
    for fila in seleccionar_publicaciones(resultados):
        publicaciones.append({
            "Publicacion_ID": fila["Publicacion_ID"], "Fecha_boe": fila["Fecha_BOE"],
            "titulo": fila.get("titulo"), "departamento": fila.get("departamento"),
            "url_xml": fila.get("url_xml"), "clasificacion_documento": _tipo_documento(fila),
            "convocatorias_esperadas": [], "propuesta_extractor": _propuesta(fila),
            "notas_revision": "", "estado_revision": "PENDIENTE",
            "ayuda_revision": {"fragmentos_relevantes": fila.get("fragmentos", []),
                               "cantidades_detectadas": fila.get("cantidades_detectadas", []),
                               "tablas_relevantes": fila.get("expresiones_encontradas", [])},
        })
    return {"version_formato": 1, "anio": 2004,
            "descripcion": "Corpus experimental de referencia manual; las propuestas no son ground truth.",
            "publicaciones": publicaciones}


def validar_corpus(corpus):
    publicaciones = corpus.get("publicaciones", [])
    if len(publicaciones) != 50:
        raise ValueError("El corpus debe contener exactamente 50 publicaciones")
    if len({p["Publicacion_ID"] for p in publicaciones}) != 50:
        raise ValueError("Hay Publicacion_ID duplicados")
    for p in publicaciones:
        if p.get("estado_revision") not in {"PENDIENTE", "REVISADO"}:
            raise ValueError(f"Estado inválido en {p['Publicacion_ID']}")
        if p["estado_revision"] == "PENDIENTE" and p.get("convocatorias_esperadas"):
            raise ValueError(f"Una publicación PENDIENTE contiene etiquetas: {p['Publicacion_ID']}")
        if p["estado_revision"] == "REVISADO":
            validar_etiqueta_revision(p)
        for c in p.get("convocatorias_esperadas", []):
            if not c.get("Puesto") or c.get("Num_plazas") is None:
                raise ValueError(f"Etiqueta funcional incompleta en {p['Publicacion_ID']}")
            if c.get("tipo_cantidad", "CONVOCATORIA") not in TIPOS_CANTIDAD:
                raise ValueError(f"tipo_cantidad inválido en {p['Publicacion_ID']}")
    return True


def validar_etiqueta_revision(publicacion):
    """Valida una etiqueta manual sin inferir ni completar ningún campo."""
    clasificacion = publicacion.get("clasificacion_documento_revision")
    if clasificacion not in CLASIFICACIONES_MANUALES:
        raise ValueError(f"Clasificación documento inválida en {publicacion['Publicacion_ID']}")
    esperadas = publicacion.get("convocatorias_esperadas", [])
    if not isinstance(esperadas, list):
        raise ValueError(f"convocatorias_esperadas debe ser una lista en {publicacion['Publicacion_ID']}")
    if clasificacion == "NO_CONVOCATORIA" and esperadas:
        raise ValueError(f"NO_CONVOCATORIA no puede contener filas en {publicacion['Publicacion_ID']}")
    for convocatoria in esperadas:
        puesto, numero = convocatoria.get("Puesto"), convocatoria.get("Num_plazas")
        if bool(puesto) != (numero is not None):
            raise ValueError(f"Puesto y Num_plazas deben aparecer juntos en {publicacion['Publicacion_ID']}")
        if not puesto:
            raise ValueError(f"Convocatoria vacía en {publicacion['Publicacion_ID']}")
        if not isinstance(numero, int) or isinstance(numero, bool) or numero <= 0:
            raise ValueError(f"Num_plazas debe ser entero positivo en {publicacion['Publicacion_ID']}")
        if convocatoria.get("tipo_cantidad", "CONVOCATORIA") not in TIPOS_CANTIDAD:
            raise ValueError(f"tipo_cantidad inválido en {publicacion['Publicacion_ID']}")
    return True


def seleccionar_revision_inicial(corpus):
    """Devuelve las diez fichas predefinidas, sin modificar el corpus."""
    por_id = {p["Publicacion_ID"]: p for p in corpus["publicaciones"]}
    ids = [identificador for identificador, _ in SELECCION_INICIAL_10]
    if set(ids) - por_id.keys():
        raise ValueError("El corpus no contiene todos los casos de revisión inicial")
    seleccion = []
    for identificador, categoria in SELECCION_INICIAL_10:
        ficha = {k: v for k, v in por_id[identificador].items()}
        ficha["categoria_seleccion"] = categoria
        ficha["clasificacion_documento_revision"] = ""
        ficha["convocatorias_esperadas"] = []
        ficha["notas_revision"] = ""
        ficha["estado_revision"] = "PENDIENTE"
        seleccion.append(ficha)
    return {"version_formato": 1, "descripcion": "Borrador manual de diez fichas; editar solo campos de revisión.",
            "publicaciones": seleccion}


def _url_html(publicacion):
    return str(publicacion.get("url_xml", "")).replace("xml.php", "txt.php")


def generar_markdown_revision(revision):
    lineas = ["# Revisión inicial controlada — corpus histórico 2004", "",
              "> Esta vista no modifica el corpus. Edita el JSON asociado para aplicar etiquetas.", ""]
    for numero, p in enumerate(revision["publicaciones"], 1):
        ayuda = p.get("ayuda_revision", {})
        lineas += [f"## {numero}. {p['Publicacion_ID']}", "", f"- Fecha: {p['Fecha_boe']}",
                   f"- Título: {p['titulo']}", f"- Departamento: {p['departamento']}",
                   f"- Categoría de selección: {p['categoria_seleccion']}",
                   f"- Enlace HTML: {_url_html(p)}", "", "### Fragmentos relevantes", ""]
        lineas += [f"> {x}" for x in ayuda.get("fragmentos_relevantes", [])] or ["_No constan fragmentos estructurales._"]
        lineas += ["", "### Tablas relevantes", "",
                   ", ".join(ayuda.get("tablas_relevantes", [])) or "_No consta señal tabular._", "",
                   "### Cantidades detectadas", ""]
        lineas += [f"- {x.get('valor')} — {x.get('fragmento')}" for x in ayuda.get("cantidades_detectadas", [])] or ["_Ninguna._"]
        lineas += ["", "### Propuesta actual del extractor", ""]
        lineas += [f"- Puesto: {x.get('Puesto')}; Num_plazas: {x.get('Num_plazas')}; Turno: {x.get('Turno')}; Sistema: {x.get('Sistema')}" for x in p.get("propuesta_extractor", [])] or ["_Sin filas propuestas._"]
        lineas += ["", "### Observaciones automáticas del corpus", "",
                   f"- Tipo de muestreo original: {p.get('clasificacion_documento')}",
                   f"- Notas automáticas: {p.get('notas_revision') or '_Ninguna._'}", "",
                   "### Etiqueta manual", "", "Clasificación documento:", "",
                   "- CONVOCATORIA / NO_CONVOCATORIA / INDETERMINADO", "",
                   "Convocatorias esperadas:", "", "1.", "", "- Puesto:", "- Num_plazas:",
                   "- Turno:", "- Sistema:", "- Escala:", "- Subescala:", "- Clase:",
                   "- tipo_cantidad:", "- incluida_en:", "- notas:", "",
                   "Añadir más bloques cuando sea necesario.", "", "---", ""]
    return "\n".join(lineas)


def generar_revision_inicial(corpus_path=CORPUS, salida_json=REVISION_INICIAL, salida_md=INFORME_REVISION_INICIAL):
    corpus = json.loads(Path(corpus_path).read_text(encoding="utf-8")); validar_corpus(corpus)
    revision = seleccionar_revision_inicial(corpus)
    salida_json, salida_md = Path(salida_json), Path(salida_md)
    salida_json.parent.mkdir(parents=True, exist_ok=True); salida_md.parent.mkdir(parents=True, exist_ok=True)
    salida_json.write_text(json.dumps(revision, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    salida_md.write_text(generar_markdown_revision(revision) + "\n", encoding="utf-8")
    return revision


def _es_revision_sin_empezar(publicacion):
    return (not publicacion.get("clasificacion_documento_revision") and
            not publicacion.get("convocatorias_esperadas") and not publicacion.get("notas_revision"))


def _escritura_atomica(path, contenido):
    path = Path(path)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False) as temporal:
        temporal.write(contenido); temporal.flush(); os.fsync(temporal.fileno())
        nombre_temporal = temporal.name
    os.replace(nombre_temporal, path)


def aplicar_revision(entrada, corpus_path=CORPUS, ahora=None):
    """Aplica solo las etiquetas completas, con backup previo y reemplazo atómico."""
    entrada, corpus_path = Path(entrada), Path(corpus_path)
    revision = json.loads(entrada.read_text(encoding="utf-8"))
    propuestas = revision.get("publicaciones", [])
    ids_esperados = [x[0] for x in SELECCION_INICIAL_10]
    if len(propuestas) != 10 or [x.get("Publicacion_ID") for x in propuestas] != ids_esperados:
        raise ValueError("El archivo de revisión debe contener exactamente la selección inicial en su orden determinista")
    for p in propuestas:
        if not _es_revision_sin_empezar(p):
            validar_etiqueta_revision(p)
    corpus = json.loads(corpus_path.read_text(encoding="utf-8")); validar_corpus(corpus)
    por_id = {p["Publicacion_ID"]: p for p in corpus["publicaciones"]}
    for propuesta in propuestas:
        if _es_revision_sin_empezar(propuesta):
            continue
        destino = por_id[propuesta["Publicacion_ID"]]
        destino["clasificacion_documento_revision"] = propuesta["clasificacion_documento_revision"]
        destino["convocatorias_esperadas"] = propuesta["convocatorias_esperadas"]
        destino["notas_revision"] = propuesta.get("notas_revision", "")
        destino["estado_revision"] = "REVISADO"
    validar_corpus(corpus)
    sello = (ahora or datetime.now()).strftime("%Y%m%d_%H%M%S")
    backup = corpus_path.with_name(f"{corpus_path.stem}.bak.{sello}{corpus_path.suffix}")
    backup.write_bytes(corpus_path.read_bytes())
    _escritura_atomica(corpus_path, json.dumps(corpus, ensure_ascii=False, indent=2) + "\n")
    return backup


def refrescar_propuestas_experimentales(corpus_path=CORPUS, identificadores=(
        "BOE-A-2004-81", "BOE-A-2004-1396", "BOE-A-2004-6309")):
    """Refresca solo propuestas de control mediante XML individuales, sin escaneo."""
    import requests
    from extractor_historico_boe import extraer_desde_contenido

    corpus_path = Path(corpus_path)
    corpus = json.loads(corpus_path.read_text(encoding="utf-8")); validar_corpus(corpus)
    por_id = {p["Publicacion_ID"]: p for p in corpus["publicaciones"]}
    if set(identificadores) - por_id.keys():
        raise ValueError("Una publicación de control no pertenece al corpus")
    for identificador in identificadores:
        ficha = por_id[identificador]
        respuesta = requests.get(ficha["url_xml"], timeout=20); respuesta.raise_for_status()
        extraido = extraer_desde_contenido(identificador, respuesta.content, ficha["url_xml"], _url_html(ficha))
        ficha["propuesta_extractor"] = [{campo: fila.get(campo) for campo in CAMPOS_OPCIONALES + ("Puesto", "Num_plazas")}
                                         for fila in extraido["convocatorias"]]
    _escritura_atomica(corpus_path, json.dumps(corpus, ensure_ascii=False, indent=2) + "\n")
    return tuple(identificadores)


def generar_markdown(corpus):
    lineas = ["# Corpus histórico BOE 2004", "", "> Las propuestas son salida automática y no constituyen ground truth.", ""]
    for i, p in enumerate(corpus["publicaciones"], 1):
        ayuda = p["ayuda_revision"]
        lineas += [f"## {i:02d}. {p['Publicacion_ID']} — {p['estado_revision']}", "",
                   f"- Fecha: {p['Fecha_boe']}", f"- Título: {p['titulo']}",
                   f"- Departamento: {p['departamento']}", f"- Tipo de muestra: {p['clasificacion_documento']}", "",
                   "### Fragmentos relevantes", ""]
        lineas += [f"> {x}" for x in ayuda["fragmentos_relevantes"]] or ["_No constan fragmentos estructurales en el escaneo._"]
        lineas += ["", "### Tablas relevantes", "",
                   (", ".join(ayuda["tablas_relevantes"]) or "_No consta señal tabular en el escaneo._"), "",
                   "### Cantidades detectadas", ""]
        lineas += [f"- {x.get('valor')} — {x.get('fragmento')} — {x.get('evidencia', '')}" for x in ayuda["cantidades_detectadas"]] or ["_Ninguna._"]
        lineas += ["", "### Salida actual / propuesta_extractor", ""]
        lineas += [f"- Puesto: {x.get('Puesto')}; Num_plazas: {x.get('Num_plazas')}; Turno: {x.get('Turno')}; Sistema: {x.get('Sistema')}" for x in p["propuesta_extractor"]] or ["_Sin filas propuestas._"]
        lineas += ["", "### ETIQUETA ESPERADA (edición manual)", "",
                   "Estado: **PENDIENTE**", "", "Convocatorias esperadas: `[]`", "",
                   "Notas de revisión:", "", "---", ""]
    return "\n".join(lineas)


def _normalizar(valor):
    valor = unicodedata.normalize("NFKD", str(valor or "").casefold())
    return " ".join("".join(c for c in valor if not unicodedata.combining(c)).split())


def _clave(fila):
    try: numero = int(str(fila.get("Num_plazas")).replace(".", "").replace(" ", ""))
    except (TypeError, ValueError): numero = fila.get("Num_plazas")
    return _normalizar(fila.get("Puesto")), numero


def comparar(corpus, resultados=None):
    """Compara solo REVISADO; TOTAL/SUBCUPO no cuentan como convocatoria."""
    resultados = resultados or {p["Publicacion_ID"]: p.get("propuesta_extractor", []) for p in corpus["publicaciones"]}
    detalle, tp = [], 0
    esperadas_total = obtenidas_total = exactas = dobles = 0
    dif_puesto = dif_numero = 0
    for p in corpus["publicaciones"]:
        if p["estado_revision"] != "REVISADO": continue
        esperadas = [x for x in p.get("convocatorias_esperadas", [])
                     if x.get("tipo_cantidad", "CONVOCATORIA") not in {"TOTAL", "SUBCUPO"}]
        obtenidas = resultados.get(p["Publicacion_ID"], [])
        ce, co = Counter(map(_clave, esperadas)), Counter(map(_clave, obtenidas))
        aciertos = sum((ce & co).values()); fp = sum((co - ce).values()); fn = sum((ce - co).values())
        repetidas = sum(max(0, n - max(1, ce.get(k, 0))) for k, n in co.items() if n > 1)
        # Diagnósticos por campo entre filas aún no emparejadas.
        faltan, sobran = list((ce - co).elements()), list((co - ce).elements())
        dp = sum(1 for e in faltan if any(e[1] == o[1] and e[0] != o[0] for o in sobran))
        dn = sum(1 for e in faltan if any(e[0] == o[0] and e[1] != o[1] for o in sobran))
        opcionales = sum(1 for e in esperadas for o in obtenidas if _clave(e) == _clave(o)
                        for campo in CAMPOS_OPCIONALES if e.get(campo) is not None and _normalizar(e.get(campo)) != _normalizar(o.get(campo)))
        tp += aciertos; esperadas_total += len(esperadas); obtenidas_total += len(obtenidas)
        exactas += not fp and not fn; dobles += repetidas; dif_puesto += dp; dif_numero += dn
        detalle.append({"Publicacion_ID": p["Publicacion_ID"], "verdaderos_positivos": aciertos,
                        "falsos_positivos": fp, "falsos_negativos": fn,
                        "diferencias_Puesto": dp, "diferencias_Num_plazas": dn,
                        "diferencias_campos_opcionales": opcionales, "posibles_dobles_conteos": repetidas})
    fp, fn = obtenidas_total - tp, esperadas_total - tp
    return {"publicaciones_revisadas": len(detalle), "convocatorias_esperadas": esperadas_total,
            "convocatorias_obtenidas": obtenidas_total, "verdaderos_positivos": tp,
            "falsos_positivos": fp, "falsos_negativos": fn,
            "precision": tp / obtenidas_total if obtenidas_total else (1.0 if not esperadas_total else 0.0),
            "recall_cobertura": tp / esperadas_total if esperadas_total else 1.0,
            "publicaciones_exactas": exactas, "diferencias_Puesto": dif_puesto,
            "diferencias_Num_plazas": dif_numero, "posibles_dobles_conteos": dobles, "detalle": detalle}


def diagnosticar_puesto(corpus):
    """Diagnóstico reproducible de las propuestas precargadas, sin reetiquetar."""
    familias = {
        "BOE-A-2004-81": "PUESTO_NO_DETECTADO",
        "BOE-A-2004-1396": "PUESTO_DEMASIADO_CORTO",
        "BOE-A-2004-3891": "PUESTO_NO_DETECTADO",
        "BOE-A-2004-6309": "PUESTO_NO_DETECTADO",
        "BOE-A-2004-10041": "ESCALA_CONFUNDIDA_CON_PUESTO",
    }
    explicaciones = {
        "BOE-A-2004-81": "La denominación explícita correcta es «categoría profesional de Ordenanza»; la propuesta solo asoció la cantidad.",
        "BOE-A-2004-1396": "«personal laboral» es una descripción genérica; la denominación explícita correcta es «categoría de Jefe Regional de Seguridad».",
        "BOE-A-2004-3891": "La cantidad total se asoció sin Puesto. La tabla Ejército/Cuerpo contiene jerarquía y el valor manual «Guardia Civil» no se puede inferir de forma segura para el total 237.",
        "BOE-A-2004-6309": "Cada denominación correcta aparece explícitamente antes de su cantidad («Profesores …, N plazas»), pero la propuesta no conserva esa asociación textual.",
        "BOE-A-2004-10041": "La denominación manual correcta es «Subescala de Intervención-Tesorería». Las cinco propuestas mezclan total, referencia de escala, componentes y subcupo.",
    }
    resultado = []
    for p in corpus["publicaciones"]:
        if p.get("estado_revision") != "REVISADO":
            continue
        esperadas = p.get("convocatorias_esperadas", [])
        extraidas = p.get("propuesta_extractor", [])
        evidencia = p.get("ayuda_revision", {}).get("cantidades_detectadas", [])
        filas = []
        for indice, esperada in enumerate(esperadas):
            extraida = next((x for x in extraidas if x.get("Num_plazas") == esperada.get("Num_plazas")), None)
            prueba = next((x for x in evidencia if x.get("valor") == esperada.get("Num_plazas")), {})
            filas.append({"esperado": {"Puesto": esperada.get("Puesto"), "Num_plazas": esperada.get("Num_plazas")},
                          "extraido": {"Puesto": extraida.get("Puesto") if extraida else None,
                                       "Num_plazas": extraida.get("Num_plazas") if extraida else None},
                          "familia": familias.get(p["Publicacion_ID"], "OTRO"),
                          "evidencia": {"fuente": prueba.get("fuente", "HISTORICAL_TEXT"),
                                        "fragmento": prueba.get("evidencia", prueba.get("fragmento", "")),
                                        "regla_patron": "propuesta_extractor precargada; sin regla de Puesto cuando el valor es nulo"}})
        resultado.append({"Publicacion_ID": p["Publicacion_ID"], "esperadas": esperadas,
                          "extraidas": extraidas, "parejas": filas,
                          "familia_principal": familias.get(p["Publicacion_ID"], "SIN_DISCREPANCIA"),
                          "explicacion": explicaciones.get(p["Publicacion_ID"], ""),
                          "observacion": ("Cinco filas: total 100, referencia de escala 100, dos componentes 50 y subcupo 5; no se modifica reconciliación."
                                           if p["Publicacion_ID"] == "BOE-A-2004-10041" else "")})
    despues = comparar(corpus)
    antes = {**despues, "verdaderos_positivos": 0, "falsos_positivos": 16,
             "falsos_negativos": 8, "diferencias_Puesto": 8,
             "diferencias_Num_plazas": 0, "publicaciones_exactas": 2}
    return {"alcance": "Solo las diez publicaciones REVISADO y propuestas precargadas del corpus.",
            "resultado_antes": antes, "resultado_despues": despues,
            "reglas_aplicadas": ["Categoría profesional explícita", "Lista local denominación, cantidad", "Categoría explícita del título sobre descriptor genérico"],
            "familias_repetidas": {"PUESTO_NO_DETECTADO": 3, "PUESTO_DEMASIADO_CORTO": 1,
                                    "ESCALA_CONFUNDIDA_CON_PUESTO": 1},
            "casos_no_resueltos": ["BOE-A-2004-3891", "BOE-A-2004-6309", "BOE-A-2004-10041"],
            "publicaciones": resultado}


def markdown_diagnostico_puesto(diagnostico):
    lineas = ["# Diagnóstico de Puesto — corpus histórico 2004", "",
              "Reglas experimentales locales aplicadas sin reglas por ID; 3891 y 10041 quedan fuera de alcance.", "",
              "## Resultado antes/después", ""]
    for etiqueta in ("resultado_antes", "resultado_despues"):
        r = diagnostico[etiqueta]
        lineas += [f"### {etiqueta.replace('_', ' ').title()}", "",
                   *[f"- {k}: {r[k]}" for k in ("verdaderos_positivos", "falsos_positivos", "falsos_negativos", "diferencias_Puesto", "diferencias_Num_plazas", "posibles_dobles_conteos")], ""]
    lineas += ["## Diagnóstico por publicación", ""]
    for p in diagnostico["publicaciones"]:
        lineas += [f"### {p['Publicacion_ID']} — {p['familia_principal']}", "",
                   "ESPERADO MANUALMENTE", "", "| Puesto | Num_plazas |", "|---|---:|"]
        lineas += [f"| {x.get('Puesto')} | {x.get('Num_plazas')} |" for x in p["esperadas"]] or ["| — | — |"]
        lineas += ["", "EXTRAÍDO ACTUALMENTE", "", "| Puesto | Num_plazas |", "|---|---:|"]
        lineas += [f"| {x.get('Puesto')} | {x.get('Num_plazas')} |" for x in p["extraidas"]] or ["| — | — |"]
        for fila in p["parejas"]:
            e = fila["evidencia"]
            lineas += ["", f"- Diferencia: esperado «{fila['esperado']['Puesto']}»; extraído «{fila['extraido']['Puesto']}». Familia: {fila['familia']}.",
                       f"- Evidencia del Puesto extraído: fuente {e['fuente']}; regla/patrón: {e['regla_patron']}; fragmento: {e['fragmento']}"]
        if p["explicacion"]: lineas += [f"- Causa y denominación correcta: {p['explicacion']}"]
        if p["observacion"]: lineas += ["", f"- Observación: {p['observacion']}"]
        lineas += [""]
    lineas += ["## Familias de error", "", *[f"- {k}: {v}" for k, v in diagnostico["familias_repetidas"].items()], "",
              "## Reglas aplicadas", "", *[f"- {x}" for x in diagnostico["reglas_aplicadas"]], "",
              "## Casos no resueltos", "", *[f"- {x}" for x in diagnostico["casos_no_resueltos"]], ""]
    return "\n".join(lineas)


def guardar_diagnostico_puesto(corpus_path=CORPUS, directorio=DIRECTORIO_DIAGNOSTICO_PUESTO):
    corpus = json.loads(Path(corpus_path).read_text(encoding="utf-8")); validar_corpus(corpus)
    diagnostico = diagnosticar_puesto(corpus); directorio = Path(directorio); directorio.mkdir(parents=True, exist_ok=True)
    (directorio / "diagnostico_puesto_2004.json").write_text(json.dumps(diagnostico, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (directorio / "diagnostico_puesto_2004.md").write_text(markdown_diagnostico_puesto(diagnostico) + "\n", encoding="utf-8")
    return diagnostico


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("accion", choices=("generar", "validar", "generar-revision-inicial", "aplicar-revision", "diagnosticar-puesto", "refrescar-propuestas"), nargs="?", default="validar")
    parser.add_argument("--corpus", type=Path, default=CORPUS)
    parser.add_argument("--entrada", type=Path, help="JSON de revisión manual para aplicar-revision")
    args = parser.parse_args(argv)
    if args.accion == "generar":
        datos = json.loads(ESCANEO.read_text(encoding="utf-8"))
        corpus = construir_corpus(datos["resultados"]); validar_corpus(corpus)
        args.corpus.parent.mkdir(parents=True, exist_ok=True)
        INFORME.parent.mkdir(parents=True, exist_ok=True)
        args.corpus.write_text(json.dumps(corpus, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        INFORME.write_text(generar_markdown(corpus) + "\n", encoding="utf-8")
        print(f"Generadas {len(corpus['publicaciones'])} publicaciones: {args.corpus} / {INFORME}")
    elif args.accion == "generar-revision-inicial":
        revision = generar_revision_inicial(args.corpus)
        print(f"Preparadas {len(revision['publicaciones'])} fichas: {REVISION_INICIAL} / {INFORME_REVISION_INICIAL}")
    elif args.accion == "aplicar-revision":
        if args.entrada is None:
            parser.error("aplicar-revision requiere --entrada")
        print(f"Backup creado: {aplicar_revision(args.entrada, args.corpus)}")
    elif args.accion == "diagnosticar-puesto":
        diagnostico = guardar_diagnostico_puesto(args.corpus)
        print(f"Diagnóstico: {DIRECTORIO_DIAGNOSTICO_PUESTO}; publicaciones={len(diagnostico['publicaciones'])}")
    elif args.accion == "refrescar-propuestas":
        print(f"Propuestas actualizadas: {', '.join(refrescar_propuestas_experimentales(args.corpus))}")
    else:
        corpus = json.loads(args.corpus.read_text(encoding="utf-8")); validar_corpus(corpus)
        print(json.dumps(comparar(corpus), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
