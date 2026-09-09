"""Auditoría read-only de convocatorias sin enlace INE municipal.

El programa no propone ni persiste cambios: identifica qué información
existente permitiría (o no) enlazar una oposición con el maestro municipal.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import csv
import json
from pathlib import Path
import sqlite3
import time

from mapa_plazas import normalizar_nombre_municipal
from resolucion_geografica import (
    COMUNIDADES,
    PROVINCIAS_ALIAS,
    cargar_alias_sedes_administrativas,
    cargar_sedes_administrativas,
)


RAIZ = Path(__file__).resolve().parent
RUTA_ALIAS = RAIZ / "datos" / "alias_municipios.csv"
RUTA_HISTORICOS = RAIZ / "datos" / "municipios_historicos.v1.json"
RUTA_ISLAS = RAIZ / "datos" / "municipios_territorios_insulares.v1.json"


def vacio(valor):
    return valor is None or not str(valor).strip()


def clave(valor):
    return normalizar_nombre_municipal(valor or "")


def _clave_provincia(valor):
    valor = clave(valor)
    return clave(PROVINCIAS_ALIAS.get(valor, valor))


def _clave_comunidad(valor):
    valor = clave(valor)
    return clave(COMUNIDADES.get(valor, valor))


def _leer_aliases(ruta=RUTA_ALIAS):
    with Path(ruta).open(encoding="utf-8", newline="") as archivo:
        return [fila for fila in csv.DictReader(archivo, delimiter=";") if fila.get("Confianza") == "ALTA"]


def _indice(candidatos, funcion):
    resultado = defaultdict(list)
    for candidato in candidatos:
        resultado[funcion(candidato)].append(candidato)
    return resultado


def _filas_dict(con, consulta):
    cursor = con.execute(consulta)
    nombres = [columna[0] for columna in cursor.description]
    return [dict(zip(nombres, fila)) for fila in cursor]


def cargar_catalogos(con, ruta_alias=RUTA_ALIAS, ruta_historicos=RUTA_HISTORICOS, ruta_islas=RUTA_ISLAS):
    """Carga cada catálogo una vez; no ejecuta ninguna escritura SQLite."""
    municipios = _filas_dict(con, """
        SELECT m.codigo_ine, m.nombre, m.nombre_normalizado, m.provincia_id,
               m.comunidad_id, m.latitud, m.longitud,
               p.nombre AS provincia_maestra, c.nombre AS comunidad_maestra
          FROM municipios AS m
          LEFT JOIN provincias AS p ON p.provincia_id = m.provincia_id
          JOIN comunidades_autonomas AS c ON c.comunidad_id = m.comunidad_id
    """)
    por_codigo = {fila["codigo_ine"]: fila for fila in municipios}
    aliases = []
    for fila in _leer_aliases(ruta_alias):
        municipio = por_codigo.get(str(fila.get("Codigo_INE", "")).zfill(5))
        if municipio:
            aliases.append({"alias": fila["Alias"], "municipio": municipio})
    historicos = json.loads(Path(ruta_historicos).read_text(encoding="utf-8")).get("municipios", [])
    islas = json.loads(Path(ruta_islas).read_text(encoding="utf-8")).get("relaciones", {})
    return {
        "municipios": municipios,
        "por_codigo": por_codigo,
        "exactos": _indice(municipios, lambda x: x["nombre"]),
        "casefold": _indice(municipios, lambda x: (x["nombre"] or "").casefold()),
        "normalizados": _indice(municipios, lambda x: clave(x["nombre"])),
        "aliases": _indice(aliases, lambda x: clave(x["alias"])),
        "historicos": _indice(historicos, lambda x: clave(x["nombre"])),
        "islas": {clave(nombre): {str(codigo).zfill(5) for codigo in codigos} for nombre, codigos in islas.items()},
        "sedes": {**cargar_sedes_administrativas(), **cargar_alias_sedes_administrativas()},
    }


def _compatibles(candidatos, provincia, comunidad, catalogos):
    """Filtra por texto maestro; las islas sólo sirven como contexto compatible."""
    if not candidatos:
        return []
    provincia_clave = _clave_provincia(provincia)
    comunidad_clave = _clave_comunidad(comunidad)
    resultado = list(candidatos)
    if provincia_clave:
        resultado = [x for x in resultado if _clave_provincia(x["provincia_maestra"]) == provincia_clave]
        if not resultado:
            codigos_isla = catalogos["islas"].get(provincia_clave, set())
            resultado = [x for x in candidatos if x["codigo_ine"] in codigos_isla]
    if comunidad_clave:
        por_comunidad = [x for x in resultado if _clave_comunidad(x["comunidad_maestra"]) == comunidad_clave]
        if por_comunidad:
            resultado = por_comunidad
    return resultado


def _detalle_candidato(candidato):
    if not candidato:
        return {}
    return {
        "codigo_ine_candidato": candidato["codigo_ine"],
        "municipio_maestro_candidato": candidato["nombre"],
        "provincia_maestra": candidato["provincia_maestra"],
        "comunidad_maestra": candidato["comunidad_maestra"],
    }


PATRON_ENTIDAD = (
    "mancomunidad", "consorcio", "diputacion", "diputación", "cabildo", "consejo insular",
    "comarca", "ministerio", "universidad", "comunidad autonoma", "comunidad autónoma",
    "provincia", "isla", "nacional", "estatal", "servicio", "consejo",
)


def clasificar_registro(registro, catalogos):
    """Clasifica sin inferir: el resultado es una hipótesis diagnóstica."""
    municipio = registro.get("municipio") or ""
    provincia = registro.get("provincia") or ""
    comunidad = registro.get("comunidad_autonoma") or ""
    base = {"categoria": "", "confianza": "BAJA", "motivo": "", "requiere_provincia": False}
    if vacio(municipio):
        admin = clave(registro.get("administracion"))
        if admin in catalogos["sedes"]:
            base.update(categoria="sede_administrativa", confianza="MEDIA", motivo="sede catalogada; sólo pista, no asignable automáticamente")
        elif any(patron in admin for patron in PATRON_ENTIDAD):
            base.update(categoria="entidad_no_municipal", motivo="sin municipio y texto administrativo/territorial")
        else:
            base.update(categoria="sin_texto_municipio", motivo="municipio NULL o vacío")
        return base

    niveles = (
        ("coincidencia_exacta_unica", catalogos["exactos"].get(municipio, []), "nombre maestro exacto"),
        ("coincidencia_casefold_unica", catalogos["casefold"].get(municipio.casefold(), []), "coincidencia sin distinguir mayúsculas"),
        ("coincidencia_normalizada_unica", catalogos["normalizados"].get(clave(municipio), []), "coincidencia ortográfica normalizada"),
    )
    for categoria, candidatos, motivo in niveles:
        if not candidatos:
            continue
        compatibles = _compatibles(candidatos, provincia, comunidad, catalogos)
        if len(candidatos) == 1 and (not provincia or compatibles):
            base.update(categoria=categoria, confianza="ALTA", motivo=motivo, **_detalle_candidato(candidatos[0]))
            return base
        if len(compatibles) == 1:
            base.update(categoria="resoluble_con_provincia", confianza="ALTA", motivo=motivo + "; provincia/comunidad desambigua", requiere_provincia=True, **_detalle_candidato(compatibles[0]))
            return base
        if provincia and not compatibles:
            base.update(categoria="inconsistencia_territorial", motivo="municipio maestro incompatible con provincia/comunidad", **_detalle_candidato(candidatos[0] if len(candidatos) == 1 else None))
            return base
        base.update(categoria="ambiguo", motivo="varios municipios maestros compatibles")
        return base

    aliases = catalogos["aliases"].get(clave(municipio), [])
    alias_candidatos = [x["municipio"] for x in aliases]
    compatibles = _compatibles(alias_candidatos, provincia, comunidad, catalogos)
    if len(alias_candidatos) == 1 and (not provincia or compatibles):
        base.update(categoria="alias_existente", confianza="ALTA", motivo="alias exacto versionado", **_detalle_candidato(alias_candidatos[0]))
        return base
    if len(compatibles) == 1:
        base.update(categoria="alias_existente", confianza="ALTA", motivo="alias exacto y provincia/comunidad compatible", requiere_provincia=True, **_detalle_candidato(compatibles[0]))
        return base

    historicos = catalogos["historicos"].get(clave(municipio), [])
    if len(historicos) == 1:
        historico = historicos[0]
        base.update(categoria="municipio_historico", confianza="MEDIA", motivo="denominación presente en catálogo histórico", codigo_ine_historico=historico["codigo_ine"], tipo_alteracion=historico["tipo_alteracion"])
        return base
    if clave(municipio) in catalogos["islas"]:
        base.update(categoria="territorio_insular", motivo="territorio insular, no municipio", confianza="BAJA")
        return base

    texto = clave(municipio)
    if any(separador in texto for separador in (";", " / ", " y ", " varias localidades", "otras localidades")):
        base.update(categoria="multiples_localizaciones", motivo="texto con patrón de varias localizaciones")
    elif any(patron in texto for patron in PATRON_ENTIDAD):
        base.update(categoria="texto_administrativo", motivo="texto de entidad o territorio, no municipio")
    else:
        base.update(categoria="sin_resolver", motivo="sin correspondencia exacta, alias ni histórico")
    return base


def _ejemplo(registro, clasificacion):
    campos = ("oposicion_id", "puesto", "administracion", "municipio", "provincia", "comunidad_autonoma", "ambito", "tipo_entidad", "latitud", "longitud")
    return {**{campo: registro.get(campo) for campo in campos}, **clasificacion}


def cargar_registros_sin_codigo_ine(con):
    """Devuelve las fuentes reales de la auditoría sin cambiar la conexión."""
    return _filas_dict(con, """
        SELECT oposicion_id, puesto, puesto_normalizado, administracion, administracion_normalizada,
               municipio, provincia, comunidad_autonoma, ambito, tipo_entidad,
               municipio_codigo_ine, latitud, longitud, fecha_boe
          FROM oposiciones WHERE municipio_codigo_ine IS NULL
    """)


def _estadisticas_coincidencia(registro, catalogos):
    """Medidas independientes de cada nivel, sin ocultar solapamientos."""
    texto = registro.get("municipio") or ""
    if vacio(texto):
        return {"sin_texto": 1}
    provincia = registro.get("provincia") or ""
    comunidad = registro.get("comunidad_autonoma") or ""
    resultado = Counter()
    for prefijo, candidatos in (
        ("exacta", catalogos["exactos"].get(texto, [])),
        ("casefold", catalogos["casefold"].get(texto.casefold(), [])),
        ("normalizada", catalogos["normalizados"].get(clave(texto), [])),
    ):
        if not candidatos:
            resultado[f"{prefijo}_ninguna"] += 1
            continue
        resultado[f"{prefijo}_unica_nacional" if len(candidatos) == 1 else f"{prefijo}_multiple_nacional"] += 1
        compatibles = _compatibles(candidatos, provincia, comunidad, catalogos)
        if len(compatibles) == 1:
            resultado[f"{prefijo}_unica_con_contexto"] += 1
            if len(candidatos) > 1:
                resultado[f"{prefijo}_requiere_provincia"] += 1
        elif provincia and not compatibles:
            resultado[f"{prefijo}_provincia_incompatible"] += 1
    aliases = [x["municipio"] for x in catalogos["aliases"].get(clave(texto), [])]
    if aliases:
        resultado["alias_coincidente"] += 1
        if len(_compatibles(aliases, provincia, comunidad, catalogos)) == 1:
            resultado["alias_unico_con_contexto"] += 1
    if catalogos["historicos"].get(clave(texto)):
        resultado["historico_coincidente"] += 1
    if clave(texto) in catalogos["islas"]:
        resultado["territorio_insular_coincidente"] += 1
    return resultado


def auditar(ruta_bd="datos/boe.db", *, limite_ejemplos=8):
    """Ejecuta la auditoría completa contra una conexión SQLite de sólo lectura."""
    inicio = time.perf_counter()
    ruta = Path(ruta_bd).resolve()
    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        catalogos = cargar_catalogos(con)
        registros = cargar_registros_sin_codigo_ine(con)
    finally:
        con.close()
    clasificaciones = Counter()
    confianzas = Counter()
    ejemplos = defaultdict(list)
    top = Counter()
    variantes = defaultdict(lambda: {"provincias": Counter(), "comunidades": Counter()})
    coordenadas = Counter()
    candidatos_alta = Counter()
    coincidencias = Counter()
    for registro in registros:
        clasificacion = clasificar_registro(registro, catalogos)
        coincidencias.update(_estadisticas_coincidencia(registro, catalogos))
        categoria = clasificacion["categoria"]
        clasificaciones[categoria] += 1
        confianzas[clasificacion["confianza"]] += 1
        if len(ejemplos[categoria]) < limite_ejemplos:
            ejemplos[categoria].append(_ejemplo(registro, clasificacion))
        texto = registro.get("municipio") or ""
        if texto.strip():
            top[texto] += 1
            variantes[texto]["provincias"][registro.get("provincia") or ""] += 1
            variantes[texto]["comunidades"][registro.get("comunidad_autonoma") or ""] += 1
        latitud, longitud = registro.get("latitud"), registro.get("longitud")
        coordenadas["ambas" if latitud is not None and longitud is not None else "solo_latitud" if latitud is not None else "solo_longitud" if longitud is not None else "ninguna"] += 1
        if clasificacion["confianza"] == "ALTA":
            candidatos_alta["regla_existente_aparentemente_no_aplicada" if categoria == "alias_existente" else "nueva_regla_potencial"] += 1
    disponibles = lambda campo: sum(not vacio(r.get(campo)) for r in registros)
    combinaciones = {
        "municipio_y_provincia": sum(not vacio(r.get("municipio")) and not vacio(r.get("provincia")) for r in registros),
        "municipio_sin_provincia": sum(not vacio(r.get("municipio")) and vacio(r.get("provincia")) for r in registros),
        "provincia_sin_municipio": sum(vacio(r.get("municipio")) and not vacio(r.get("provincia")) for r in registros),
        "solo_comunidad": sum(vacio(r.get("municipio")) and vacio(r.get("provincia")) and not vacio(r.get("comunidad_autonoma")) for r in registros),
        "sin_informacion_territorial": sum(vacio(r.get("municipio")) and vacio(r.get("provincia")) and vacio(r.get("comunidad_autonoma")) for r in registros),
    }
    ranking = []
    for texto, cantidad in top.most_common(50):
        ranking.append({"municipio": texto, "convocatorias": cantidad,
                        "provincias": dict(variantes[texto]["provincias"]),
                        "comunidades": dict(variantes[texto]["comunidades"]),
                        "variantes_provincia": len(variantes[texto]["provincias"]),
                        "variantes_comunidad": len(variantes[texto]["comunidades"])})
    return {
        "version": "fase3-paso7a-v1", "generado_utc": datetime.now(timezone.utc).isoformat(),
        "base_datos": str(ruta), "total_sin_codigo_ine": len(registros),
        "catalogos": {"municipios": len(catalogos["municipios"]), "aliases_altos": sum(len(x) for x in catalogos["aliases"].values()), "historicos": sum(len(x) for x in catalogos["historicos"].values()), "territorios_insulares": len(catalogos["islas"]), "sedes": len(catalogos["sedes"])},
        "disponibilidad": {"municipio_no_vacio": disponibles("municipio"), "municipio_vacio": len(registros)-disponibles("municipio"), "provincia_no_vacia": disponibles("provincia"), "provincia_vacia": len(registros)-disponibles("provincia"), "comunidad_no_vacia": disponibles("comunidad_autonoma"), "comunidad_vacia": len(registros)-disponibles("comunidad_autonoma"), "combinaciones": combinaciones},
        "coordenadas_historicas_oposiciones": dict(coordenadas),
        "coincidencias_maestro": dict(coincidencias),
        "clasificacion": dict(clasificaciones), "confianza": dict(confianzas),
        "candidatos_alta_confianza": {"total": sum(candidatos_alta.values()), "por_origen": dict(candidatos_alta)},
        "ranking_municipios": ranking, "ejemplos": dict(ejemplos),
        "rendimiento_segundos": round(time.perf_counter()-inicio, 3),
    }


def imprimir_resumen(informe):
    print(f"Total sin código INE: {informe['total_sin_codigo_ine']}")
    print("Clasificación:")
    for categoria, total in sorted(informe["clasificacion"].items(), key=lambda x: (-x[1], x[0])):
        print(f"  {categoria}: {total}")
    print("Confianza:", ", ".join(f"{k}={v}" for k, v in sorted(informe["confianza"].items())))
    print(f"Rendimiento: {informe['rendimiento_segundos']} s")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-datos", default="datos/boe.db")
    parser.add_argument("--salida", default="informes/sin_coordenadas_auditoria.json")
    args = parser.parse_args(argv)
    informe = auditar(args.base_datos)
    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    imprimir_resumen(informe)
    print(f"Informe: {salida}")


if __name__ == "__main__":
    main()
