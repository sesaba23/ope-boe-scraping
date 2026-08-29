"""Auditoría experimental, de solo lectura, del origen de la administración BOE.

No forma parte de la extracción ni escribe Excel o estados.  Sirve para mostrar
qué información llega del sumario, qué queda en el estado histórico y qué
información ofrece el XML de una muestra acotada.
"""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

import requests

from analizar_xml_boe import analizar_xml
from boe_api import extraer_publicaciones_2b_api, obtener_sumario_api
from diagnostico_administraciones_historicas import cargar_historicos


ESTADOS_GLOB = "informes/procesamiento_historico_2004/estado_*.json"
ADMINISTRACION_LOCAL = "Administración Local"
FAMILIAS_CONCRETAS = re.compile(
    r"\b(?:ayuntamiento|diputaci[oó]n(?:\s+provincial)?|universidad)\s+de\s+"
    r"(?:la\s+)?[^,.;\n]{2,100}", re.I)
PATRON_CONVOCANTE_TITULO = re.compile(
    r",\s*(?:del|de\s+la|de\s+los|de\s+las)\s+"
    r"([A-ZÁÉÍÓÚÑ][^,.;\n]{2,160}?)(?=,\s*(?:referente|por\s+la\s+que|para|se\s+convoca))",
    re.I,
)


def firma_archivo(ruta):
    ruta = Path(ruta)
    estadistica = ruta.stat()
    return {
        "sha256": hashlib.sha256(ruta.read_bytes()).hexdigest(),
        "tamano": estadistica.st_size,
        "mtime_ns": estadistica.st_mtime_ns,
    }


def _ano(valor):
    coincidencia = re.search(r"(\d{4})", str(valor or ""))
    return int(coincidencia.group(1)) if coincidencia else None


def seleccionar_muestra(publicaciones, oposiciones, cantidad=30):
    """Devuelve hasta 10 IDs por tramo temporal, siempre en el mismo orden."""
    locales = oposiciones[oposiciones["Administración"].astype(str).eq(ADMINISTRACION_LOCAL)]
    ids_locales = set(locales["Publicacion_ID"].dropna().astype(str))
    fechas = publicaciones.set_index("Publicacion_ID")["Fecha_BOE"].to_dict()
    grupos = {"historicos_antiguos": [], "intermedios": [], "recientes": []}
    for publicacion_id in ids_locales:
        ano = _ano(fechas.get(publicacion_id))
        if ano is None:
            continue
        tramo = "historicos_antiguos" if ano <= 2009 else "intermedios" if ano <= 2016 else "recientes"
        grupos[tramo].append(publicacion_id)
    por_tramo = cantidad // 3
    sobrantes = cantidad % 3
    seleccion = []
    for indice, tramo in enumerate(("historicos_antiguos", "intermedios", "recientes")):
        limite = por_tramo + (1 if indice < sobrantes else 0)
        seleccion.extend(sorted(grupos[tramo], key=lambda x: hashlib.sha256(x.encode()).hexdigest())[:limite])
    return sorted(seleccion, key=lambda x: (_ano(fechas.get(x)) or 0, x))


def cargar_resultados_estados(ids, patron=ESTADOS_GLOB):
    """Localiza únicamente las entradas seleccionadas en estados persistidos."""
    buscados, encontrados = set(ids), {}
    for ruta in sorted(Path().glob(patron)):
        estado = json.loads(ruta.read_text(encoding="utf-8"))
        for publicacion_id in buscados - encontrados.keys():
            resultado = estado.get("resultados", {}).get(publicacion_id)
            if resultado:
                encontrados[publicacion_id] = {"ruta_estado": str(ruta), **resultado}
    return encontrados


def resumir_metadatos_estados(patron=ESTADOS_GLOB):
    """Cuenta lo aprovechable sin modificar ni normalizar estados solapados."""
    resumen = Counter()
    for ruta in sorted(Path().glob(patron)):
        estado = json.loads(ruta.read_text(encoding="utf-8"))
        for ficha in estado.get("resultados", {}).values():
            resumen["entradas"] += 1
            metadatos = ficha.get("metadatos") or {}
            resumen["metadatos_no_vacios"] += bool(metadatos)
            resumen["titulos"] += bool(metadatos.get("titulo"))
            resumen["departamentos"] += bool(metadatos.get("departamento"))
            resumen["evidencias"] += bool(ficha.get("evidencias"))
    return dict(resumen)


def extraer_administracion_concreta(*textos):
    """Extrae una entidad explícita del encabezado, sin resolver su sede."""
    for texto in textos:
        if isinstance(texto, str):
            coincidencia = FAMILIAS_CONCRETAS.search(texto)
            if coincidencia:
                return " ".join(coincidencia.group(0).split()).strip()
            coincidencia = PATRON_CONVOCANTE_TITULO.search(texto)
            if coincidencia:
                return " ".join(coincidencia.group(1).split()).strip()
    return ""


def construir_muestra_persistida(publicaciones, oposiciones, ids, estados):
    titulos = publicaciones.set_index("Publicacion_ID")["Titulo_original"].to_dict()
    fechas = publicaciones.set_index("Publicacion_ID")["Fecha_BOE"].to_dict()
    filas_por_id = Counter(oposiciones["Publicacion_ID"].astype(str))
    resultado = []
    for publicacion_id in ids:
        estado = estados.get(publicacion_id, {})
        meta = estado.get("metadatos") or {}
        resultado.append({
            "Publicacion_ID": publicacion_id,
            "ano": _ano(fechas.get(publicacion_id)),
            "filas_oposiciones": int(filas_por_id[publicacion_id]),
            "administracion_actual": ADMINISTRACION_LOCAL,
            "titulo_persistido": titulos.get(publicacion_id) or "",
            "metadatos_estado": meta,
            "estado_json": estado.get("estado", "NO_ENCONTRADO"),
            "ruta_estado": estado.get("ruta_estado", ""),
        })
    return resultado


def seleccionar_submuestra(muestra, limite=10):
    """Reparte las consultas entre los mismos tres tramos de la muestra."""
    grupos = [
        [x for x in muestra if (x.get("ano") or 0) <= 2009],
        [x for x in muestra if 2010 <= (x.get("ano") or 0) <= 2016],
        [x for x in muestra if (x.get("ano") or 0) >= 2017],
    ]
    base, extra = divmod(limite, len(grupos))
    seleccion = []
    for indice, grupo in enumerate(grupos):
        seleccion.extend(grupo[:base + (1 if indice < extra else 0)])
    return seleccion


def consultar_submuestra(muestra, limite=10, consultar_api=obtener_sumario_api,
                         obtener_xml=requests.get):
    """Consulta como máximo `limite` publicaciones; agrupa API por fecha."""
    seleccion = seleccionar_submuestra(muestra, limite)
    por_fecha = {}
    for fila in seleccion:
        fecha = str(fila.get("metadatos_estado", {}).get("fecha_publicacion") or "")
        if not fecha:
            # Fecha_BOE se conserva en el informe persistido solo como año; la URL
            # de estado sí conserva la fecha completa del catálogo.
            fecha = ""
        if not fecha:
            # El llamador completa fecha_iso antes de consultar.
            fecha = fila["fecha_iso"]
        por_fecha.setdefault(fecha, []).append(fila["Publicacion_ID"])

    api_por_id = {}
    for fecha, ids in por_fecha.items():
        publicaciones = extraer_publicaciones_2b_api(consultar_api(fecha)).get("publicaciones", [])
        disponibles = {x.get("Publicacion_ID"): x for x in publicaciones}
        for publicacion_id in ids:
            api_por_id[publicacion_id] = disponibles.get(publicacion_id, {})

    consultas = []
    for fila in seleccion:
        api = api_por_id.get(fila["Publicacion_ID"], {})
        url_xml = api.get("url_xml") or str(fila.get("Enlace", "")).replace("txt.php", "xml.php")
        xml_meta, texto, error = {}, "", ""
        try:
            respuesta = obtener_xml(url_xml, timeout=20)
            respuesta.raise_for_status()
            analisis = analizar_xml(respuesta.content)
            xml_meta = analisis.get("metadatos", {})
            texto = analisis.get("texto_relevante", "")
        except Exception as exc:  # diagnóstico: conserva el error sin alterar estado
            error = str(exc)
        admin_api = extraer_administracion_concreta(api.get("titulo"), api.get("departamento"))
        admin_xml_meta = extraer_administracion_concreta(xml_meta.get("titulo"), xml_meta.get("departamento"))
        admin_xml_texto = extraer_administracion_concreta(texto)
        fuente = ("API_SUMARIO" if admin_api else "XML_METADATOS" if admin_xml_meta
                  else "XML_TEXTO" if admin_xml_texto else "NO_RESUELTA")
        consultas.append({
            "Publicacion_ID": fila["Publicacion_ID"], "fecha": fila["fecha_iso"],
            "titulo_api": api.get("titulo", ""), "departamento_api": api.get("departamento", ""),
            "titulo_xml": xml_meta.get("titulo", ""), "departamento_xml": xml_meta.get("departamento", ""),
            "encabezamiento_xml": texto[:500],
            "administracion_concreta": admin_api or admin_xml_meta or admin_xml_texto,
            "fuente_mas_fiable": fuente, "error_consulta": error,
        })
    return consultas


def diagnosticar(excel="BOE-oposiciones.xlsx", max_consultas=10):
    publicaciones, oposiciones = cargar_historicos(excel)
    # Fecha completa y enlace se obtienen del propio Publicaciones, sin red.
    columnas = publicaciones.set_index("Publicacion_ID")
    ids = seleccionar_muestra(publicaciones, oposiciones)
    estados = cargar_resultados_estados(ids)
    muestra = construir_muestra_persistida(publicaciones, oposiciones, ids, estados)
    for fila in muestra:
        origen = columnas.loc[fila["Publicacion_ID"]]
        fila["fecha_iso"] = str(origen.get("Fecha_BOE") or "")[:10]
        fila["Enlace"] = origen.get("Enlace") or (estados.get(fila["Publicacion_ID"], {}).get("Enlace") or "")
    consultas = consultar_submuestra(muestra, max_consultas)
    api = sum(bool(x["administracion_concreta"]) and x["fuente_mas_fiable"] == "API_SUMARIO" for x in consultas)
    xml_total = sum(bool(extraer_administracion_concreta(
        x.get("titulo_xml"), x.get("departamento_xml"), x.get("encabezamiento_xml"))) for x in consultas)
    xml = sum(bool(x["administracion_concreta"]) and x["fuente_mas_fiable"] in {"XML_METADATOS", "XML_TEXTO"} for x in consultas)
    solo_texto = sum(x["fuente_mas_fiable"] == "XML_TEXTO" for x in consultas)
    no_resuelta = sum(x["fuente_mas_fiable"] == "NO_RESUELTA" for x in consultas)
    estados_utiles = sum(bool(x.get("metadatos_estado")) for x in muestra)
    metadatos_estados = resumir_metadatos_estados()
    fechas_sumario = publicaciones["Fecha_BOE"].dropna().astype(str).str[:10].nunique()
    return {
        "metodologia": {"muestra": "hash SHA-256 de Publicacion_ID, 10 IDs por tramo 2004-2009/2010-2016/2017-2026", "consultas_maximas": max_consultas},
        "flujo": [
            "API/sumario: item.titulo, item.url_html, item.url_xml y departamento.nombre",
            "cargar_historico_boe.descubrir: conserva en el sumario normalizado, pero persiste solo Publicacion_ID, Fecha_boe y Enlace",
            "XML/extractor: analizar_xml conserva titulo/departamento; procesar_publicacion devuelve solo clasificación y filas válidas",
            "estado JSON: registrar_resultado recibe sin metadatos/evidencias desde cargar_historico_boe",
            "Publicaciones: _publicaciones_historicas lee metadatos.titulo; al estar vacío, Titulo_original queda vacío",
            "Oposiciones: extractor histórico asigna Administración=metadatos.departamento, que para esta muestra es Administración Local genérica",
        ],
        "punto_perdida": "cargar_historico_boe.descubrir descarta titulo/departamento del sumario; después procesar_publicacion/ejecutar descartan metadatos XML. El extractor asigna el departamento BOE genérico a Administración, no la entidad concreta del título.",
        "muestra_persistida": muestra,
        "consultas_reales": consultas,
        "resumen": {
            "publicaciones_historicas": len(publicaciones), "filas_historicas": len(oposiciones),
            "filas_administracion_local": int((oposiciones["Administración"].astype(str) == ADMINISTRACION_LOCAL).sum()),
            "muestra_publicaciones": len(muestra), "estado_json_con_metadatos": estados_utiles,
            "entradas_estados_revisadas": metadatos_estados.get("entradas", 0),
            "titulos_en_estados": metadatos_estados.get("titulos", 0),
            "departamentos_en_estados": metadatos_estados.get("departamentos", 0),
            "evidencias_en_estados": metadatos_estados.get("evidencias", 0),
            "fechas_distintas_para_consultar_sumario": int(fechas_sumario),
            "consultas_reales": len(consultas), "api_identifica_administracion": api,
            "xml_identifica_administracion": xml_total,
            "xml_identifica_administracion_adicional": xml,
            "solo_texto_xml": solo_texto, "no_resoluble_en_consulta": no_resuelta,
            "porcentaje_api": round(100 * api / len(consultas), 1) if consultas else 0,
            "porcentaje_xml": round(100 * xml_total / len(consultas), 1) if consultas else 0,
            "porcentaje_xml_adicional": round(100 * xml / len(consultas), 1) if consultas else 0,
            "porcentaje_solo_texto": round(100 * solo_texto / len(consultas), 1) if consultas else 0,
            "porcentaje_no_resoluble": round(100 * no_resuelta / len(consultas), 1) if consultas else 0,
        },
    }


def escribir_informes(datos, directorio="informes/diagnostico_administraciones_historicas"):
    destino = Path(directorio); destino.mkdir(parents=True, exist_ok=True)
    (destino / "diagnostico_origen_administracion.json").write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    r = datos["resumen"]
    lineas = ["# Origen de la Administración convocante", "", "## Punto de pérdida", "", datos["punto_perdida"], "", "## Flujo", ""]
    lineas += [f"1. {x}" for x in datos["flujo"]]
    lineas += ["", "## Resumen", ""] + [f"- {k}: {v}" for k, v in r.items()]
    lineas += ["", "## Muestra persistida (30)", "", "| ID | Año | Filas | Título Excel | Metadatos estado |", "|---|---:|---:|---|---|"]
    lineas += [f"| {x['Publicacion_ID']} | {x['ano']} | {x['filas_oposiciones']} | {x['titulo_persistido'][:100]} | {bool(x['metadatos_estado'])} |" for x in datos["muestra_persistida"]]
    lineas += ["", "## Consultas individuales BOE (máximo 10)", "", "| ID | API título/departamento | XML título/departamento | Administración concreta | Fuente |", "|---|---|---|---|---|"]
    lineas += [f"| {x['Publicacion_ID']} | {x['titulo_api'][:120]} / {x['departamento_api'][:80]} | {x['titulo_xml'][:120]} / {x['departamento_xml'][:80]} | {x['administracion_concreta']} | {x['fuente_mas_fiable']} |" for x in datos["consultas_reales"]]
    lineas += ["", "## Coste y recomendación", "", "Los estados existentes no permiten reconstruir de forma fiable los títulos perdidos. La opción mínima que conserva título y departamento es consultar de nuevo el sumario/API para cada fecha de edición y asociar sus items por Publicacion_ID; no requiere XML ni reextraer Puesto/Num_plazas. XML solo sería necesario para los casos en que el título/sumario no identifique explícitamente la entidad."]
    (destino / "diagnostico_origen_administracion.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--excel", default="BOE-oposiciones.xlsx")
    parser.add_argument("--salida", default="informes/diagnostico_administraciones_historicas")
    parser.add_argument("--max-consultas", type=int, default=10)
    args = parser.parse_args(argv)
    if not 0 <= args.max_consultas <= 10:
        parser.error("--max-consultas debe estar entre 0 y 10")
    datos = diagnosticar(args.excel, args.max_consultas)
    escribir_informes(datos, args.salida)
    print(json.dumps(datos["resumen"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
