"""Prototipo experimental, de solo lectura, para tablas del XML del BOE."""

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import unicodedata
from xml.etree import ElementTree

import requests

from boe_api import extraer_publicaciones_2b_api, obtener_sumario_api


DOCUMENTOS = {
    "BOE-A-2004-6389": "2004-04-10",
    "BOE-A-2004-6488": "2004-04-13",
}
CAMPOS_RESULTADO = ["Puesto", "Num_plazas", "Escala", "Turno", "Sistema"]
EQUIVALENCIAS = {
    "Puesto": {"puesto", "denominacion", "denominacion del puesto", "categoria", "cuerpo", "escala", "especialidad", "categoria cuerpo escala tipo"},
    "Num_plazas": {"plazas", "numero de plazas", "num de plazas", "n de plazas", "n o plazas", "vacantes", "numero de vacantes", "numero vacantes", "plazas vacantes"},
    "Escala": {"escala", "categoria cuerpo escala tipo"},
    "Turno": {"turno"},
    "Sistema": {"sistema", "sistema selectivo"},
}


def _local(etiqueta):
    return etiqueta.rsplit("}", 1)[-1].casefold()


def normalizar_texto(valor):
    """Normaliza exclusivamente espacios y saltos del contenido textual."""
    return " ".join(str(valor or "").split())


def _clave_encabezado(valor):
    texto = unicodedata.normalize("NFKD", normalizar_texto(valor).casefold())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", texto).split())


def _entero_positivo(valor):
    texto = normalizar_texto(valor)
    if not re.fullmatch(r"[0-9]{1,3}(?:[. ][0-9]{3})*|[0-9]+", texto):
        return None
    numero = int(texto.replace(".", "").replace(" ", ""))
    return numero if numero >= 0 else None


def _expandir_filas(tabla):
    """Expande la rejilla sin perder la célula XML de la que procede cada valor."""
    filas, pendientes = [], {}
    for fila_original, tr in enumerate(n for n in tabla.iter() if _local(n.tag) == "tr"):
        celdas = [n for n in list(tr) if _local(n.tag) in {"th", "td"}]
        if not celdas:
            continue
        fila, columna = [], 0

        def consumir_pendientes():
            nonlocal columna
            while columna in pendientes:
                restantes, celda = pendientes[columna]
                heredada = {**celda, "heredada": True}
                fila.append(heredada)
                if restantes == 1:
                    del pendientes[columna]
                else:
                    pendientes[columna] = (restantes - 1, celda)
                columna += 1

        for columna_original, celda in enumerate(celdas):
            consumir_pendientes()
            texto, tipo = normalizar_texto(" ".join(celda.itertext())), _local(celda.tag)
            try:
                colspan = max(1, int(celda.get("colspan", "1")))
                rowspan = max(1, int(celda.get("rowspan", "1")))
            except ValueError:
                colspan = rowspan = 1
            for _ in range(colspan):
                estructura = {"texto": texto, "fila_original": fila_original,
                              "columna_original": columna_original, "rowspan": rowspan,
                              "colspan": colspan, "heredada": False,
                              "celda_origen": [fila_original, columna_original], "tipo": tipo}
                fila.append(estructura)
                if rowspan > 1:
                    pendientes[columna] = (rowspan - 1, estructura)
                columna += 1
        consumir_pendientes()
        filas.append(fila)
    return filas


def parsear_tablas_xml(contenido):
    """Devuelve las tablas situadas dentro de ``texto`` en su orden original."""
    if not contenido:
        raise ValueError("XML vacío")
    mayusculas = contenido.upper()
    if b"<!DOCTYPE" in mayusculas or b"<!ENTITY" in mayusculas:
        raise ValueError("El XML contiene una declaración no admitida")
    try:
        raiz = ElementTree.fromstring(contenido)
    except ElementTree.ParseError as error:
        raise ValueError(f"XML inválido: {error}") from error
    texto = next((n for n in raiz.iter() if _local(n.tag) == "texto"), None)
    if texto is None:
        raise LookupError("No existe el bloque texto")
    resultado = []
    for indice, tabla in enumerate(n for n in texto.iter() if _local(n.tag) == "table"):
        filas_estructura = _expandir_filas(tabla)
        cabecera = next((i for i, fila in enumerate(filas_estructura) if any(c["tipo"] == "th" for c in fila)), None)
        encabezados = [c["texto"] for c in filas_estructura[cabecera]] if cabecera is not None else []
        datos_estructura = [fila for i, fila in enumerate(filas_estructura) if i != cabecera]
        datos = [[c["texto"] for c in fila] for fila in datos_estructura]
        resultado.append({"indice": indice, "encabezados": encabezados, "filas": datos,
                          "filas_estructuradas": [{"celdas": fila, "grupo_padre": None,
                                                   "nivel_jerarquico": 0, "es_grupo": False}
                                                  for fila in datos_estructura]})
    return resultado


def identificar_columnas(encabezados):
    columnas = {}
    for indice, encabezado in enumerate(encabezados):
        clave = _clave_encabezado(encabezado)
        for campo, equivalentes in EQUIVALENCIAS.items():
            if clave in equivalentes and campo not in columnas:
                columnas[campo] = indice
    return columnas


def estructurar_grupos_tabla(tabla):
    """Marca filas agrupadoras solo cuando la propia rejilla XML lo demuestra."""
    copia = {**tabla, "filas_estructuradas": [{**fila, "celdas": [dict(c) for c in fila["celdas"]]}
                                                   for fila in tabla.get("filas_estructuradas", [])]}
    columnas = identificar_columnas(copia["encabezados"])
    grupo_actual, nivel = None, 0
    for indice, fila in enumerate(copia["filas_estructuradas"]):
        celdas = fila["celdas"]
        no_vacias = [c for c in celdas if c["texto"]]
        cantidad = (columnas.get("Num_plazas") is not None and columnas["Num_plazas"] < len(celdas)
                    and _entero_positivo(celdas[columnas["Num_plazas"]]["texto"]) is not None)
        expandida = any(c["colspan"] > 1 for c in no_vacias)
        es_grupo = bool(no_vacias and not cantidad and (len(no_vacias) == 1 or expandida))
        if es_grupo:
            grupo_actual = no_vacias[0]["texto"]; nivel += 1
            fila.update({"es_grupo": True, "grupo_padre": grupo_actual, "nivel_jerarquico": nivel})
        else:
            fila.update({"es_grupo": False, "grupo_padre": grupo_actual, "nivel_jerarquico": nivel})
    return copia


def extraer_bloques_tabla_estructurados(tabla):
    """Asocia resultados con su fila, celdas y padre estructural exactos."""
    tabla = estructurar_grupos_tabla(tabla)
    columnas = identificar_columnas(tabla["encabezados"])
    bloques = []
    for indice, fila in enumerate(tabla["filas"]):
        temporal = {**tabla, "filas": [fila]}
        resultados = extraer_resultados_tabla(temporal)
        if resultados:
            bloques.append({"fila_indice": indice, "campos": resultados[0],
                            "estructura": tabla["filas_estructuradas"][indice]})
    return bloques


def extraer_resultados_tabla(tabla):
    """Extrae solo campos respaldados por encabezados explícitos."""
    encabezados, filas = tabla["encabezados"], tabla["filas"]
    columnas = identificar_columnas(encabezados)
    claves = [_clave_encabezado(x) for x in encabezados]
    indice_codigo = claves.index("codigo") if "codigo" in claves else None
    if "Num_plazas" not in columnas and not (indice_codigo is not None and "Puesto" in columnas):
        return []
    resultados, contexto = [], None
    for fila in filas:
        valor = lambda campo: normalizar_texto(fila[columnas[campo]]) if campo in columnas and columnas[campo] < len(fila) else None
        puesto = valor("Puesto")
        # Totales y etiquetas genéricas de sección no son denominaciones
        # suficientemente específicas para constituir una convocatoria.
        if _clave_encabezado(puesto) in {"total", "general"}:
            puesto = None
        if indice_codigo is not None:
            codigo = normalizar_texto(fila[indice_codigo]) if indice_codigo < len(fila) else ""
            if not codigo and puesto and not any(normalizar_texto(x) for i, x in enumerate(fila) if i != columnas["Puesto"]):
                contexto = puesto
                continue
            if codigo and contexto and puesto and puesto.casefold().startswith("actividades"):
                puesto = contexto
        resultado = {
            "Puesto": puesto or None,
            "Num_plazas": _entero_positivo(valor("Num_plazas")),
            "Escala": (contexto if indice_codigo is not None and contexto and puesto == contexto else valor("Escala")) or None,
            "Turno": valor("Turno") or None,
            "Sistema": valor("Sistema") or None,
        }
        if any(v is not None for v in resultado.values()):
            resultados.append(resultado)
    return resultados


def clasificar_utilidad(tablas, resultados):
    if not tablas:
        return "SIN_TABLAS"
    if not resultados:
        return "TABLA_NO_UTIL"
    if any(r["Puesto"] and r["Num_plazas"] is not None for r in resultados):
        return "TABLA_UTIL"
    return "TABLA_PARCIAL"


def obtener_documentos_api(consultar_api=None):
    consultar_api = consultar_api or obtener_sumario_api
    encontrados = {}
    for identificador, fecha in DOCUMENTOS.items():
        publicaciones = extraer_publicaciones_2b_api(consultar_api(fecha))["publicaciones"]
        encontrados.update({p.get("Publicacion_ID"): {**p, "Fecha": fecha} for p in publicaciones})
    faltantes = [x for x in DOCUMENTOS if x not in encontrados or not encontrados[x].get("url_xml")]
    if faltantes:
        raise ValueError(f"La API no devolvió URL XML para: {', '.join(faltantes)}")
    return [encontrados[x] for x in DOCUMENTOS]


def analizar_documento(documento, obtener=requests.get):
    respuesta = obtener(documento["url_xml"], timeout=10)
    respuesta.raise_for_status()
    tablas = parsear_tablas_xml(respuesta.content)
    detalles = []
    resultados = []
    for tabla in tablas:
        extraidos = extraer_resultados_tabla(tabla)
        detalles.append({**tabla, "columnas_identificadas": identificar_columnas(tabla["encabezados"]), "resultados": extraidos})
        resultados.extend(extraidos)
    return {
        "Publicacion_ID": documento["Publicacion_ID"], "Fecha": documento["Fecha"],
        "url_xml": documento["url_xml"], "numero_tablas": len(tablas),
        "tablas": detalles, "resultados_parciales": resultados,
        "filas_utiles": len(resultados), "extractor_actual_filas": 0,
        "clasificacion": clasificar_utilidad(tablas, resultados),
        "campos_no_recuperados": [c for c in CAMPOS_RESULTADO if not any(r[c] is not None for r in resultados)],
    }


def resumir(documentos):
    conteos = {k: sum(d["clasificacion"] == k for d in documentos) for k in ("TABLA_UTIL", "TABLA_PARCIAL", "TABLA_NO_UTIL", "SIN_TABLAS")}
    total = len(documentos)
    return {"documentos_analizados": total, **conteos,
            "porcentajes": {k: round(v * 100 / total, 2) if total else 0 for k, v in conteos.items()}}


def guardar_informes(documentos, directorio, ahora=None):
    directorio = Path(directorio); directorio.mkdir(parents=True, exist_ok=True)
    ahora = ahora or datetime.now(); sello = ahora.strftime("%Y%m%d_%H%M%S_%f")
    resumen = resumir(documentos)
    datos = {"fecha_ejecucion": ahora.isoformat(timespec="seconds"), "resumen": resumen, "documentos": documentos,
             "criterios": {"TABLA_UTIL": "Algún resultado contiene Puesto y Num_plazas explícitos.", "TABLA_PARCIAL": "Hay campos recuperables, pero ningún resultado contiene ambos.", "TABLA_NO_UTIL": "Hay tablas, pero no campos recuperables de forma controlada.", "SIN_TABLAS": "El bloque texto no contiene tablas."}}
    ruta_json = directorio / f"tablas_xml_2004_{sello}.json"
    ruta_md = directorio / f"tablas_xml_2004_{sello}.md"
    ruta_json.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    lineas = ["# Tablas XML del BOE (2004)", "", "## Resumen", "", f"Documentos analizados: {resumen['documentos_analizados']}", "", "## Documentos analizados", ""]
    for d in documentos:
        lineas += [f"### {d['Publicacion_ID']} — {d['clasificacion']}", "", f"Tablas: {d['numero_tablas']}; filas útiles: {d['filas_utiles']}; extractor actual: {d['extractor_actual_filas']} filas.", "", "Encabezados encontrados:", ""]
        lineas += [f"- {', '.join(t['encabezados']) or '(sin encabezados)'}" for t in d["tablas"]]
        lineas += ["", f"Campos que siguen requiriendo texto libre o no están presentes: {', '.join(d['campos_no_recuperados']) or 'ninguno'}.", ""]
    lineas += ["## Variabilidad entre documentos", "", "Los encabezados no forman un esquema común y mezclan información de plazas con tablas de tribunales.", "", "## Recomendación", "", "Usar tablas como fuente auxiliar histórica, manteniendo análisis textual para completar y validar convocatorias.", ""]
    ruta_md.write_text("\n".join(lineas), encoding="utf-8")
    return ruta_json, ruta_md


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salida", default="informes/tablas_xml_2004")
    args = parser.parse_args(argv)
    documentos = [analizar_documento(d) for d in obtener_documentos_api()]
    rutas = guardar_informes(documentos, args.salida)
    for d in documentos:
        print(f"{d['Publicacion_ID']}: {d['clasificacion']} ({d['numero_tablas']} tablas, {d['filas_utiles']} resultados)")
    print(f"Informes: {rutas[0]} / {rutas[1]}")


if __name__ == "__main__":
    main()
