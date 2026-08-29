"""Validación histórica, de solo lectura, del extractor de convocatorias."""

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
from statistics import mean, median
import tempfile
import time
import unicodedata

from bs4 import BeautifulSoup, ParserRejectedMarkup
import pandas as pd
import requests

from boe_api import ErrorAPIBOE, extraer_publicaciones_2b_api, obtener_sumario_api
import coincidencias


LIMITE_PREDETERMINADO = 50
CAMPOS_RESULTADO = [
    "Puesto", "Num_plazas", "Turno", "Sistema", "Escala", "Subescala",
    "Clase", "Administración",
]
VALORES_PROBLEMATICOS = {"", "--", "no disponible"}
INDICIOS_CONVOCATORIA = {
    "número de plazas": r"numero\s+de\s+plazas",
    "número de vacantes": r"numero\s+de\s+vacantes",
    "se convocan": r"\bse\s+convocan\b",
    "convocatoria": r"\bconvocatori[ao]s?\b",
    "oposición": r"\boposicion\b",
    "concurso-oposición": r"\bconcurso\s*[- ]\s*oposicion\b",
    "turno libre": r"\bturno\s+libre\b",
}
INDICIOS_NO_CONVOCATORIA = {
    "admitidos/excluidos": r"\badmitid[oa]s?\b|\bexcluid[oa]s?\b",
    "tribunal": r"\btribunal\b",
    "aprobados": r"\baprobad[oa]s?\b",
    "nombramiento": r"\bnombramiento\b|\bse\s+nombra\b",
    "desierta": r"\bdesiert[oa]\b",
    "resultado": r"\bresultado\b|\brelacion\s+definitiva\b",
}


def descubrir_publicaciones(anio, desde=None, hasta=None, consultar_api=None):
    """Descubre por API todas las publicaciones II.B del intervalo."""
    consultar_api = consultar_api or obtener_sumario_api
    inicio, fin = _intervalo(anio, desde, hasta)
    publicaciones = []
    errores = []
    tiempos = []
    actual = inicio
    while actual <= fin:
        comienzo = time.perf_counter()
        try:
            resultado = extraer_publicaciones_2b_api(consultar_api(actual))
            documentos = resultado["publicaciones"]
            numero_dia = len(documentos)
            for documento in documentos:
                if documento.get("Publicacion_ID") and documento.get("url_html"):
                    publicaciones.append({
                        **documento,
                        "Fecha": actual.isoformat(),
                        "Mes": actual.month,
                        "Numero_publicaciones_dia": numero_dia,
                    })
        except (ErrorAPIBOE, ValueError, KeyError, TypeError) as error:
            errores.append({"Fecha": actual.isoformat(), "error": str(error)})
        tiempos.append(time.perf_counter() - comienzo)
        actual += timedelta(days=1)
    unicas = {}
    for publicacion in publicaciones:
        unicas.setdefault(publicacion["Publicacion_ID"], publicacion)
    return list(unicas.values()), errores, tiempos


def seleccionar_muestra(publicaciones, limite=LIMITE_PREDETERMINADO):
    """Selecciona de forma determinista una muestra temporal y organizativa."""
    if limite is None:
        limite = LIMITE_PREDETERMINADO
    if limite < 1:
        raise ValueError("--limite debe ser mayor que cero")
    candidatas = sorted(
        publicaciones,
        key=lambda p: (
            p["Mes"], _categoria_departamento(p.get("departamento")),
            p.get("Numero_publicaciones_dia", 0), p["Publicacion_ID"],
        ),
    )
    por_mes = defaultdict(list)
    for publicacion in candidatas:
        por_mes[publicacion["Mes"]].append(publicacion)

    seleccion = []
    vistos = set()
    categorias_vistas = set()

    def añadir(publicacion):
        if publicacion["Publicacion_ID"] not in vistos and len(seleccion) < limite:
            seleccion.append(publicacion)
            vistos.add(publicacion["Publicacion_ID"])
            categorias_vistas.add(_categoria_departamento(publicacion.get("departamento")))

    # Primera vuelta: un documento por cada mes disponible, alternando carga baja/alta.
    for mes in sorted(por_mes):
        grupo = sorted(
            por_mes[mes],
            key=lambda p: (p.get("Numero_publicaciones_dia", 0), p["Publicacion_ID"]),
            reverse=mes % 2 == 0,
        )
        añadir(grupo[0])

    # Segunda vuelta: garantiza las categorías administrativas presentes.
    for categoria in ("LOCAL", "ESTADO", "OTRAS"):
        if categoria not in categorias_vistas:
            candidata = next(
                (p for p in candidatas if _categoria_departamento(p.get("departamento")) == categoria),
                None,
            )
            if candidata:
                añadir(candidata)

    # Relleno round-robin mensual para impedir concentración cronológica.
    posicion = 0
    while len(seleccion) < min(limite, len(candidatas)):
        hubo_adicion = False
        for mes in sorted(por_mes):
            restantes = [p for p in por_mes[mes] if p["Publicacion_ID"] not in vistos]
            if restantes:
                añadir(restantes[posicion % len(restantes)])
                hubo_adicion = True
                if len(seleccion) == limite:
                    break
        if not hubo_adicion:
            break
        posicion += 1
    return seleccion


def analizar_publicacion(publicacion, obtener=None):
    """Descarga una vez, ejecuta los extractores actuales y diagnostica el texto."""
    obtener = obtener or requests.get
    comienzo = time.perf_counter()
    base = {
        clave: publicacion.get(clave)
        for clave in ("Publicacion_ID", "Fecha", "titulo", "departamento", "url_html")
    }
    try:
        respuesta = obtener(publicacion["url_html"], timeout=10)
        respuesta.raise_for_status()
        soup = BeautifulSoup(respuesta.content, "html.parser")
        contenidos = soup.find_all("div", id="textoxslt")
        titulo = soup.find(class_="documento-tit")
        fecha = soup.find("div", class_="metadatos")
        if not contenidos or titulo is None or fecha is None:
            raise ValueError("Faltan elementos esperados en el HTML documental")
        texto = "\n".join(contenido.get_text(" ", strip=True) for contenido in contenidos)
        convocatorias = []
        for contenido in contenidos:
            extraidas = coincidencias.extraer_convocatorias_local(
                contenido.text, titulo.text.strip(), fecha.text.strip(), publicacion["url_html"]
            )
            if not extraidas:
                extraidas = coincidencias.extraer_convocatorias_estatal(
                    contenido.text, titulo.text.strip(), fecha.text.strip(), publicacion["url_html"]
                )
            convocatorias.extend(extraidas)
        diagnostico, indicios = diagnosticar_texto(texto, titulo.text)
        problematicos = campos_problematicos(convocatorias)
        multiconvocatoria = detectar_multiconvocatoria(texto)
        return {
            **base,
            "clasificacion_extractor": "EXTRAIDA" if convocatorias else "SIN_RESULTADOS",
            "clasificacion_diagnostica": diagnostico,
            "indicios_encontrados": indicios,
            "numero_convocatorias_extraidas": len(convocatorias),
            "convocatorias_extraidas": [
                {campo: _json_valor(fila.get(campo)) for campo in CAMPOS_RESULTADO}
                for fila in convocatorias
            ],
            "campos_problematicos": problematicos,
            "posible_multiconvocatoria": multiconvocatoria,
            "error": None,
            "tiempo_documental": time.perf_counter() - comienzo,
        }
    except (requests.exceptions.RequestException, ParserRejectedMarkup, TypeError, ValueError) as error:
        return {
            **base,
            "clasificacion_extractor": "ERROR",
            "clasificacion_diagnostica": "REVISAR",
            "indicios_encontrados": [],
            "numero_convocatorias_extraidas": 0,
            "convocatorias_extraidas": [],
            "campos_problematicos": [],
            "posible_multiconvocatoria": False,
            "error": {"tipo": type(error).__name__, "mensaje": str(error)},
            "tiempo_documental": time.perf_counter() - comienzo,
        }


def diagnosticar_texto(texto, titulo=""):
    normalizado = _normalizar(f"{titulo}\n{texto}")
    positivos = [nombre for nombre, patron in INDICIOS_CONVOCATORIA.items() if re.search(patron, normalizado)]
    negativos = [nombre for nombre, patron in INDICIOS_NO_CONVOCATORIA.items() if re.search(patron, normalizado)]
    if any(x in positivos for x in ("número de plazas", "número de vacantes", "se convocan", "turno libre", "concurso-oposición")):
        return "PROBABLE_CONVOCATORIA", positivos + negativos
    if negativos and not positivos:
        return "PROBABLE_NO_CONVOCATORIA", negativos
    return "REVISAR", positivos + negativos


def detectar_multiconvocatoria(texto):
    normalizado = _normalizar(texto)
    cantidades = re.findall(r"\b\d+\s+(?:plazas?|vacantes?)\b", normalizado)
    bloques = re.findall(r"(?:^|\s)[a-z]\)|\b(?:categoria|especialidad|puesto)s?\b", normalizado)
    return len(cantidades) >= 2 or len(bloques) >= 2


def campos_problematicos(convocatorias):
    contador = Counter()
    for fila in convocatorias:
        for campo in CAMPOS_RESULTADO:
            valor = fila.get(campo)
            if valor is None or (not isinstance(valor, (list, dict)) and pd.isna(valor)) or str(valor).strip().casefold() in VALORES_PROBLEMATICOS:
                contador[campo] += 1
    return dict(sorted(contador.items()))


def resumir_resultados(detalles, errores_api, tiempos_api, estrategia):
    clases = Counter(d["clasificacion_extractor"] for d in detalles)
    diagnosticos_sin = Counter(
        d["clasificacion_diagnostica"] for d in detalles
        if d["clasificacion_extractor"] == "SIN_RESULTADOS"
    )
    campos = Counter()
    por_mes = Counter()
    por_departamento = Counter()
    for detalle in detalles:
        por_mes[detalle["Fecha"][:7]] += 1
        por_departamento[detalle.get("departamento") or "Sin departamento"] += 1
        campos.update(detalle["campos_problematicos"])
    tiempos_documentales = [d["tiempo_documental"] for d in detalles]
    return {
        "estrategia_muestra": estrategia,
        "Publicaciones analizadas": len(detalles),
        "EXTRAIDA": clases["EXTRAIDA"],
        "SIN_RESULTADOS": clases["SIN_RESULTADOS"],
        "ERROR": clases["ERROR"],
        "SIN_RESULTADOS_diagnostico": dict(diagnosticos_sin),
        "total_convocatorias_extraidas": sum(d["numero_convocatorias_extraidas"] for d in detalles),
        "publicaciones_una_convocatoria": sum(d["numero_convocatorias_extraidas"] == 1 for d in detalles),
        "publicaciones_varias_convocatorias": sum(d["numero_convocatorias_extraidas"] > 1 for d in detalles),
        "posibles_multiconvocatoria_una_fila": sum(d["posible_multiconvocatoria"] and d["numero_convocatorias_extraidas"] <= 1 for d in detalles),
        "campos_problematicos": dict(campos.most_common()),
        "por_mes": dict(sorted(por_mes.items())),
        "por_departamento": dict(por_departamento.most_common()),
        "errores_descubrimiento_api": errores_api,
        "rendimiento_api": _metricas_tiempo(tiempos_api),
        "rendimiento_documental": _metricas_tiempo(tiempos_documentales),
    }


def guardar_informes(detalles, resumen, integridad, directorio="informes/historico_2004", momento=None):
    instante = momento or datetime.now()
    marca = instante.strftime("%Y%m%d_%H%M%S")
    carpeta = Path(directorio)
    carpeta.mkdir(parents=True, exist_ok=True)
    base = carpeta / f"validacion_historico_2004_{marca}"
    ruta_json = _ruta_unica(base.with_suffix(".json"))
    ruta_md = ruta_json.with_suffix(".md")
    datos = {"fecha_ejecucion": instante.strftime("%Y-%m-%d %H:%M:%S"), **resumen, "integridad_excel": integridad, "publicaciones": detalles}
    _guardar_atomico(ruta_json, json.dumps(datos, ensure_ascii=False, indent=2, default=_json_valor))
    _guardar_atomico(ruta_md, _markdown(detalles, resumen, integridad))
    return ruta_json, ruta_md


def ejecutar_validacion(anio, limite=50, desde=None, hasta=None, ruta_excel="BOE-oposiciones.xlsx"):
    antes = integridad_excel(ruta_excel)
    inicio_total = time.perf_counter()
    publicaciones, errores_api, tiempos_api = descubrir_publicaciones(anio, desde, hasta)
    muestra = seleccionar_muestra(publicaciones, limite)
    detalles = [analizar_publicacion(publicacion) for publicacion in muestra]
    estrategia = (
        "Un documento por mes disponible alternando días de baja/alta carga; después "
        "cobertura de Administración Local, Estado y otras; relleno round-robin mensual "
        "con orden estable por mes, categoría, carga diaria y Publicacion_ID."
    )
    resumen = resumir_resultados(detalles, errores_api, tiempos_api, estrategia)
    resumen["tiempo_total"] = time.perf_counter() - inicio_total
    despues = integridad_excel(ruta_excel)
    integridad = {"antes": antes, "despues": despues, "sin_cambios": antes == despues}
    rutas = guardar_informes(detalles, resumen, integridad)
    return detalles, resumen, integridad, rutas


def integridad_excel(ruta="BOE-oposiciones.xlsx"):
    ruta = Path(ruta)
    contenido = ruta.read_bytes()
    estado = ruta.stat()
    return {"sha256": hashlib.sha256(contenido).hexdigest(), "tamano": estado.st_size, "mtime_ns": estado.st_mtime_ns}


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Validación histórica del extractor BOE")
    parser.add_argument("--anio", type=int, required=True)
    parser.add_argument("--limite", type=int, default=LIMITE_PREDETERMINADO)
    parser.add_argument("--desde")
    parser.add_argument("--hasta")
    opciones = parser.parse_args(argumentos)
    detalles, resumen, integridad, rutas = ejecutar_validacion(
        opciones.anio, opciones.limite, opciones.desde, opciones.hasta
    )
    for clave in ("Publicaciones analizadas", "EXTRAIDA", "SIN_RESULTADOS", "ERROR", "total_convocatorias_extraidas"):
        print(f"{clave}: {resumen[clave]}")
    print(f"JSON: {rutas[0]}\nMarkdown: {rutas[1]}")
    if not integridad["sin_cambios"]:
        raise SystemExit("El Excel cambió durante la validación")


def _intervalo(anio, desde, hasta):
    inicio = datetime.strptime(desde, "%Y-%m-%d").date() if desde else date(anio, 1, 1)
    fin = datetime.strptime(hasta, "%Y-%m-%d").date() if hasta else date(anio, 12, 31)
    if inicio.year != anio or fin.year != anio or inicio > fin:
        raise ValueError("El intervalo debe pertenecer al año indicado y ser válido")
    return inicio, fin


def _categoria_departamento(nombre):
    texto = _normalizar(nombre or "")
    if "administracion local" in texto:
        return "LOCAL"
    if texto.startswith("ministerio") or "administracion del estado" in texto:
        return "ESTADO"
    return "OTRAS"


def _normalizar(texto):
    return "".join(c for c in unicodedata.normalize("NFD", str(texto).casefold()) if unicodedata.category(c) != "Mn")


def _metricas_tiempo(valores):
    return {"total": sum(valores), "media": mean(valores) if valores else 0, "mediana": median(valores) if valores else 0, "maximo": max(valores) if valores else 0}


def _json_valor(valor):
    if valor is None or (not isinstance(valor, (dict, list)) and pd.isna(valor)):
        return None
    if hasattr(valor, "item"):
        return valor.item()
    return valor


def _ruta_unica(ruta):
    numero = 1
    candidata = ruta
    while candidata.exists():
        candidata = ruta.with_name(f"{ruta.stem}_{numero}{ruta.suffix}")
        numero += 1
    return candidata


def _guardar_atomico(destino, contenido):
    temporal = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=destino.parent, delete=False) as archivo:
            temporal = Path(archivo.name)
            archivo.write(contenido)
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(temporal, destino)
    except BaseException:
        if temporal:
            temporal.unlink(missing_ok=True)
        raise


def _markdown(detalles, resumen, integridad):
    lineas = ["# Validación histórica BOE 2004", "", "## Resumen", ""]
    for clave in ("Publicaciones analizadas", "EXTRAIDA", "SIN_RESULTADOS", "ERROR", "total_convocatorias_extraidas", "publicaciones_una_convocatoria", "publicaciones_varias_convocatorias", "posibles_multiconvocatoria_una_fila"):
        lineas.append(f"- {clave}: {resumen[clave]}")
    lineas.extend(["", "## Construcción de la muestra", "", resumen["estrategia_muestra"], "", "## Distribución por mes", ""])
    lineas.extend(f"- {k}: {v}" for k, v in resumen["por_mes"].items())
    lineas.extend(["", "## Distribución por departamento/administración", ""])
    lineas.extend(f"- {k}: {v}" for k, v in resumen["por_departamento"].items())
    lineas.extend(_lista_casos("SIN_RESULTADOS + PROBABLE_CONVOCATORIA", [d for d in detalles if d["clasificacion_extractor"] == "SIN_RESULTADOS" and d["clasificacion_diagnostica"] == "PROBABLE_CONVOCATORIA"], True))
    lineas.extend(_lista_casos("EXTRAIDA + POSIBLE_MULTICONVOCATORIA", [d for d in detalles if d["clasificacion_extractor"] == "EXTRAIDA" and d["posible_multiconvocatoria"]]))
    lineas.extend(_lista_casos("Extracciones con campos problemáticos", [d for d in detalles if d["campos_problematicos"]]))
    lineas.extend(["", "## Campos problemáticos más frecuentes", ""])
    lineas.extend(f"- {k}: {v}" for k, v in resumen["campos_problematicos"].items())
    for nombre, clave in (("Descubrimiento mediante API", "rendimiento_api"), ("Descarga y análisis documental", "rendimiento_documental")):
        datos = resumen[clave]
        lineas.extend(["", f"## Rendimiento: {nombre}", "", f"- Total: {datos['total']:.3f} s", f"- Media: {datos['media']:.3f} s", f"- Mediana: {datos['mediana']:.3f} s", f"- Máximo: {datos['maximo']:.3f} s"])
    lineas.extend(["", "## Integridad del Excel", "", f"- Antes: `{integridad['antes']}`", f"- Después: `{integridad['despues']}`", f"- Sin cambios: **{integridad['sin_cambios']}**", ""])
    return "\n".join(lineas)


def _lista_casos(titulo, casos, mostrar_indicios=False):
    lineas = ["", f"## {titulo}", ""]
    if not casos:
        return lineas + ["Sin casos."]
    for d in casos[:10]:
        extra = f" · indicios: {', '.join(d['indicios_encontrados'])}" if mostrar_indicios else f" · filas: {d['numero_convocatorias_extraidas']}"
        lineas.append(f"- {d['Publicacion_ID']} · {d['Fecha']} · {d.get('titulo') or 'sin título'} · {d['url_html']}{extra}")
    return lineas


if __name__ == "__main__":
    main()
