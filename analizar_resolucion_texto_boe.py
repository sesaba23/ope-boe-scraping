"""Dry-run conservador de resolución municipio → provincia/capital desde texto BOE.

La base actual no persiste cuerpos BOE. El analizador acepta texto explícito
para pruebas y futuros archivos locales, pero en producción sólo diagnostica
la calidad de los fragmentos locales disponibles; jamás descarga ni escribe.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time

from analizar_sin_coordenadas import cargar_catalogos, clave, _compatibles
from mapa_plazas import _variantes_nombre_catalogo


PATRON_MUNICIPIO = r"(?:municipio|ayuntamiento|ajuntament|concello|destino|plaza(?:s)?s+en)\s+(?:de|d'|en)\s+([^,;().]+)"
PATRON_PROVINCIA = r"(?:en\s+la\s+|de\s+la\s+|)provincia\s+de\s+([^,;().]+)"
PATRON_INCIDENTAL = r"(?:bolet[ií]n\s+oficial|diputaci[oó]n|cabildo|consejo\s+insular|mancomunidad|consorcio)"


def _capitales_por_provincia(catalogos):
    """Deriva capitales desde maestro y denominaciones oficiales, sin hardcodear."""
    resultado = {}
    for municipio in catalogos["municipios"]:
        variantes = _variantes_nombre_catalogo(municipio["provincia_maestra"])
        if any(clave(municipio["nombre"]) == clave(variante) for variante in variantes):
            resultado[municipio["provincia_maestra"]] = municipio
    return resultado


def _candidatos_municipio(nombre, catalogos, provincia="", comunidad=""):
    candidatos = catalogos["normalizados"].get(clave(nombre), [])
    compatibles = _compatibles(candidatos, provincia, comunidad, catalogos)
    if len(compatibles) == 1:
        return compatibles[0], None
    if candidatos and provincia and not compatibles:
        return None, "conflicto_municipio_provincia"
    return None, "ambiguo_municipio" if len(candidatos) > 1 else "municipio_no_encontrado"


def analizar_texto(texto, catalogos, *, provincia="", comunidad="", fuente="texto_boe"):
    """Extrae sólo evidencias explícitas; una mención aislada nunca basta."""
    import re
    texto = texto or ""
    respuesta = {"origen_resolucion": None, "confianza": "BAJA", "regla": "sin_texto_localizable", "fragmento": ""}
    if not texto.strip():
        return respuesta
    for encontrado in re.finditer(PATRON_MUNICIPIO, texto, flags=re.I):
        nombre = encontrado.group(1).strip()
        candidato, problema = _candidatos_municipio(nombre, catalogos, provincia, comunidad)
        if candidato:
            return {"origen_resolucion": "municipio_boe", "confianza": "ALTA", "regla": "municipio_explicito_contextual", "fragmento": encontrado.group(0), "municipio_detectado": nombre, **{k: candidato[k] for k in ("codigo_ine", "nombre", "provincia_maestra", "comunidad_maestra", "latitud", "longitud")}}
        if problema == "conflicto_municipio_provincia":
            return {**respuesta, "regla": problema, "fragmento": encontrado.group(0), "municipio_detectado": nombre}
        if catalogos.get("historicos", {}).get(clave(nombre)):
            return {**respuesta, "regla": "municipio_historico_no_asignable", "fragmento": encontrado.group(0), "municipio_detectado": nombre}
    # Un boletín provincial o una entidad territorial no identifica destino.
    if re.search(PATRON_INCIDENTAL, texto, flags=re.I):
        return {**respuesta, "regla": "referencia_administrativa_incidental"}
    capitales = _capitales_por_provincia(catalogos)
    for encontrado in re.finditer(PATRON_PROVINCIA, texto, flags=re.I):
        texto_provincia = encontrado.group(1).strip()
        provincia_canon = next((m["provincia_maestra"] for m in catalogos["municipios"] if clave(m["provincia_maestra"]) == clave(texto_provincia)), None)
        capital = capitales.get(provincia_canon)
        if capital:
            return {"origen_resolucion": "capital_provincia", "confianza": "MEDIA", "regla": "provincia_explicita_contextual", "fragmento": encontrado.group(0), "provincia_detectada": provincia_canon, **{k: capital[k] for k in ("codigo_ine", "nombre", "provincia_maestra", "comunidad_maestra", "latitud", "longitud")}}
    return respuesta


def comparar_legacy(resultado, latitud, longitud, tolerancia=0.0001):
    """Contrasta resultados ya obtenidos; nunca participa en su selección."""
    if latitud is None or longitud is None:
        return "sin_coordenadas_legacy"
    if resultado.get("origen_resolucion") is None:
        return "sin_reconstruccion"
    coincide = abs(latitud - resultado["latitud"]) <= tolerancia and abs(longitud - resultado["longitud"]) <= tolerancia
    return "coincide" if coincide else "no_coincide"


def _filas_dict(con, consulta):
    cursor = con.execute(consulta)
    nombres = [x[0] for x in cursor.description]
    return [dict(zip(nombres, fila)) for fila in cursor]


def auditar_texto_boe(ruta_bd="datos/boe.db", *, limite_ejemplos=30):
    """Audita la base en modo URI read-only, sin solicitudes de red."""
    inicio = time.perf_counter(); ruta = Path(ruta_bd).resolve()
    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        catalogos = cargar_catalogos(con); capitales = _capitales_por_provincia(catalogos)
        filas = _filas_dict(con, """
            SELECT o.oposicion_id,o.puesto,o.administracion,o.publicacion,o.enlace,o.municipio,o.provincia,
                   o.comunidad_autonoma,o.latitud AS latitud_legacy,o.longitud AS longitud_legacy,
                   p.titulo_original
              FROM oposiciones o LEFT JOIN publicaciones p USING(publicacion_id)
             WHERE o.municipio_codigo_ine IS NULL
        """)
    finally:
        con.close()
    estadisticas = Counter(); confianza = Counter(); legacy = Counter(); origenes = Counter(); ejemplos = defaultdict(list)
    municipios, provincias = set(), set()
    territorios = Counter(); fuentes = Counter()
    for fila in filas:
        # Se reserva para el futuro texto BOE completo; los campos locales son
        # sólo metadatos y no satisfacen la evidencia contextual requerida.
        texto = fila.get("titulo_original") or ""
        fuente = "titulo_original" if texto.strip() else "sin_texto_boe_persistido"
        fuentes[fuente] += 1
        resultado = analizar_texto(texto, catalogos, provincia=fila.get("provincia") or "", comunidad=fila.get("comunidad_autonoma") or "", fuente=fuente)
        estadisticas[resultado["regla"]] += 1; confianza[resultado["confianza"]] += 1
        if resultado["origen_resolucion"]:
            origenes[resultado["origen_resolucion"]] += 1
        if resultado.get("nombre"): municipios.add(resultado["codigo_ine"])
        if resultado.get("provincia_detectada") or resultado.get("provincia_maestra"):
            provincias.add(resultado.get("provincia_detectada") or resultado.get("provincia_maestra"))
        comunidad = clave(fila.get("comunidad_autonoma")); provincia = clave(fila.get("provincia"))
        if comunidad in {"ceuta", "melilla"}: territorios[comunidad] += 1
        if comunidad == "canarias" or provincia in {"las palmas", "santa cruz de tenerife"}: territorios["canarias"] += 1
        if comunidad == "illes balears" or provincia == "illes balears": territorios["illes_balears"] += 1
        estado_legacy = comparar_legacy(resultado, fila["latitud_legacy"], fila["longitud_legacy"])
        legacy[estado_legacy] += 1
        if resultado.get("origen_resolucion") is not None and estado_legacy != "sin_coordenadas_legacy":
            legacy[resultado["origen_resolucion"]] += 1
        if len(ejemplos[resultado["regla"]]) < limite_ejemplos:
            ejemplos[resultado["regla"]].append({
                "oposicion_id": fila["oposicion_id"], "puesto": fila["puesto"], "administracion": fila["administracion"],
                "referencia_publicacion": fila["publicacion"], "municipio_preextraido": fila["municipio"],
                "provincia_preextraida": fila["provincia"], "coordenadas_legacy": [fila["latitud_legacy"], fila["longitud_legacy"]], **resultado,
            })
    return {
        "version": "fase3-paso7c-v1", "generado_utc": datetime.now(timezone.utc).isoformat(), "base_datos": str(ruta),
        "fuente_textual": {"texto_boe_completo_persistido": False, "campos_disponibles": ["titulo_original", "publicacion", "administracion", "puesto", "municipio", "provincia"], "uso_primario": "titulo_original", "limitacion": "No se conserva cuerpo HTML/XML/TXT del BOE; no se realizan descargas."},
        "total_analizado": len(filas), "fuentes": dict(fuentes), "estadisticas_regla": dict(estadisticas),
        "confianza": dict(confianza), "potenciales": {"municipio_boe": origenes["municipio_boe"], "capital_provincia": origenes["capital_provincia"]},
        "municipios_distintos": len(municipios), "provincias_distintas": len(provincias), "capitales_derivadas_maestro": len(capitales),
        "territorios": dict(territorios), "legacy": dict(legacy), "ejemplos": dict(ejemplos),
        "rendimiento_segundos": round(time.perf_counter()-inicio, 3),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bd", "--base-datos", dest="ruta_bd", default="datos/boe.db")
    parser.add_argument("--salida", default="informes/resolucion_texto_boe_dry_run.json")
    args = parser.parse_args(argv)
    informe = auditar_texto_boe(args.ruta_bd)
    salida = Path(args.salida); salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"total_analizado": informe["total_analizado"], "fuentes": informe["fuentes"], "confianza": informe["confianza"], "rendimiento_segundos": informe["rendimiento_segundos"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
