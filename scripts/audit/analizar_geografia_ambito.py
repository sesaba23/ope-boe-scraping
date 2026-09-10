"""Auditoría read-only de geografía y ámbito administrativo (FASE 3)."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sqlite3

import pandas as pd

from mapa_plazas import _variantes_nombre_catalogo, normalizar_nombre_municipal


ALIAS_PROVINCIAS = {
    "la coruna": "A Coruña", "coruna": "A Coruña", "orense": "Ourense",
    "guipuzcoa": "Gipuzkoa", "guipuzkoa": "Gipuzkoa", "vizcaya": "Bizkaia", "alava": "Araba/Álava",
    "alicante": "Alicante/Alacant", "alacant": "Alicante/Alacant",
    "valencia": "Valencia/València", "valencia/valencia": "Valencia/València",
    "castellon": "Castellón/Castelló", "gerona": "Girona", "lerida": "Lleida",
    "islas baleares": "Illes Balears", "illes baleares": "Illes Balears", "baleares": "Illes Balears",
    "ciudad de ceuta": "Ciudad Autónoma de Ceuta",
    "ciudad de melilla": "Ciudad Autónoma de Melilla",
    "tenerife": "Santa Cruz de Tenerife",
}
ISLAS = {normalizar_nombre_municipal(x) for x in (
    "Tenerife", "Gran Canaria", "Lanzarote", "Fuerteventura", "La Palma",
    "La Gomera", "El Hierro", "Mallorca", "Menorca", "Ibiza", "Formentera",
)}
FALSOS_POSITIVOS = [
    ("Gran Canaria", "Cáñar", "Granada"),
    ("Servicios", "Vic", "Barcelona"),
    ("Sierra de San Pedro (Cáceres)", "San Pedro", "Albacete"),
    ("Osona (Barcelona)", "Oña", "Burgos"),
    ("La Vera (Cáceres)", "Vera", "Almería"),
    ("Debabarrena (Gipuzkoa)", "Marçà", "Tarragona"),
    ("Gran Canaria (Las Palmas)", "Cáñar", "Granada"),
]


def clave(texto):
    return normalizar_nombre_municipal(texto).replace("/", "/")


def estado_base(ruta):
    ruta = Path(ruta); stat = ruta.stat(); digest = hashlib.sha256(ruta.read_bytes()).hexdigest()
    con = sqlite3.connect(f"file:{ruta.resolve()}?mode=ro", uri=True)
    try:
        return {"sha256": digest, "tamano": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                "metadata": dict(con.execute("SELECT clave,valor FROM metadata")),
                "conteos": {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                            for t in ("publicaciones","oposiciones","busquedas","cobertura","log_errores")},
                "integrity_check": [x[0] for x in con.execute("PRAGMA integrity_check")],
                "foreign_key_check": con.execute("PRAGMA foreign_key_check").fetchall()}
    finally: con.close()


def catalogos():
    mun = pd.read_csv("datos/municipios_oficial.csv", sep=";", dtype=str).fillna("")
    aliases = pd.read_csv("datos/alias_municipios.csv", sep=";", dtype=str).fillna("")
    provincias = sorted(mun["Provincia"].unique())
    indice_prov = {}
    for provincia in provincias:
        variantes = {provincia, *provincia.split("/")}
        for variante in variantes: indice_prov[clave(variante)] = provincia
    indice_prov.update({clave(k): v for k, v in ALIAS_PROVINCIAS.items()})
    indice_mun = defaultdict(list)
    for fila in mun.to_dict("records"):
        for variante in _variantes_nombre_catalogo(fila["Municipio"]):
            indice_mun[clave(variante)].append(fila)
    por_codigo = {str(x["Codigo_INE"]).zfill(5): x for x in mun.to_dict("records")}
    for fila in aliases.to_dict("records"):
        oficial = por_codigo.get(str(fila["Codigo_INE"]).zfill(5))
        if oficial and fila["Confianza"] == "ALTA": indice_mun[clave(fila["Alias"])].append(oficial)
    comunidades = {clave(x): x for x in mun["Comunidad"].unique() if x}
    return mun, aliases, indice_prov, indice_mun, comunidades


def provincia(texto, indice):
    return indice.get(clave(str(texto).strip(" ,.;")))


def ultimo_parentesis(texto):
    m = re.search(r"\(([^()]*)\)\s*(?:[,.;]|$)", str(texto))
    todos = re.findall(r"\(([^()]*)\)", str(texto))
    return todos[-1].strip() if todos else ""


def municipio_exacto(nombre, indice_mun, provincia_contexto=None):
    candidatos = indice_mun.get(clave(nombre), [])
    unicos = {(x["Codigo_INE"], x["Municipio"], x["Provincia"]): x for x in candidatos}
    if provincia_contexto:
        unicos = {k:v for k,v in unicos.items() if v["Provincia"] == provincia_contexto}
    return next(iter(unicos.values())) if len(unicos) == 1 else None


def clasificar_parentesis(valor, indice_prov, indice_mun, comunidades):
    if provincia(valor, indice_prov):
        canon = provincia(valor, indice_prov)
        return ("PROVINCIA" if clave(valor) == clave(canon) else "PROVINCIA_ALIAS", canon)
    if clave(valor) in ISLAS: return "ISLA", ""
    candidatos = {(x["Codigo_INE"], x["Municipio"]) for x in indice_mun.get(clave(valor), [])}
    if len(candidatos) == 1: return "MUNICIPIO", next(iter(candidatos))[1]
    if len(candidatos) > 1: return "AMBIGUO", ""
    if clave(valor) in comunidades: return "COMUNIDAD_AUTONOMA", comunidades[clave(valor)]
    if re.search(r"comarca|campina|valle|sierra|ribera|valles", clave(valor)): return "COMARCA", ""
    if not valor.strip() or re.search(r"\d{3,}|convocatoria|anula|modifica", valor, re.I): return "ERROR_TEXTO", ""
    return "OTRO", ""


def ambito(administracion):
    a = clave(administracion)
    if a in {"administracion local"} or re.match(
        r"^(ayuntamiento|ajuntament|concello|diputacion|diputacio|deputacion|"
        r"mancomunidad|cabildo|consell insular|consejo insular|consorcio)", a
    ): return "LOCAL", "ALTA"
    if re.match(r"^(ministerio|consejo de estado|consejo general del poder judicial|tribunal supremo|agencia estatal)", a):
        return "ESTATAL", "ALTA"
    if re.match(r"^(comunidad autonoma|junta de andalucia|generalitat|gobierno vasco|gobierno de canarias|principado de asturias)", a):
        return "AUTONOMICO", "ALTA"
    if a.startswith("universidad de "): return "OTRO", "ALTA"
    return "INDETERMINADO", "NO_ENCONTRADO"


def analizar(ruta="datos/boe.db"):
    antes = estado_base(ruta); mun, aliases, ip, im, comunidades = catalogos()
    con = sqlite3.connect(f"file:{Path(ruta).resolve()}?mode=ro", uri=True)
    columnas = "oposicion_id,administracion,puesto,municipio,provincia,fecha_boe,version_extractor"
    filas = [dict(zip(columnas.split(","), x)) for x in con.execute(f"SELECT {columnas} FROM oposiciones")]
    con.close()

    parentesis = Counter(); detalle_parentesis = {}
    for f in filas:
        valores = re.findall(r"\(([^()]*)\)", str(f["administracion"] or ""))
        for valor in valores:
            valor = valor.strip(); parentesis[valor] += 1
            categoria, canon = clasificar_parentesis(valor, ip, im, comunidades)
            detalle_parentesis[valor] = {"texto": valor, "frecuencia": 0, "clasificacion": categoria, "canon": canon}
    for valor,n in parentesis.items(): detalle_parentesis[valor]["frecuencia"] = n

    entidades = {"DIPUTACIONES": re.compile(r"diputaci|deputaci|cabildo|consell insular|consejo insular", re.I),
                 "AYUNTAMIENTOS": re.compile(r"^(ayuntamiento|ajuntament|concello|.+\budala\b)", re.I),
                 "OTRAS_LOCALES": re.compile(r"^(mancomunidad|consorcio|comarca|entidad local)", re.I)}
    resumen_entidades = {}
    for nombre, patron in entidades.items():
        candidatas = [f for f in filas if patron.search(str(f["administracion"] or ""))]
        resolubles = sum(bool(provincia(ultimo_parentesis(f["administracion"]), ip)) for f in candidatas)
        resumen_entidades[nombre] = {"total":len(candidatas), "provincia_parentesis_alta":resolubles,
                                      "no_resolubles_o_ambiguas":len(candidatas)-resolubles}

    sin = [f for f in filas if f["provincia"] is None]
    recupera_prov = {}; recupera_mun = {}; ambitos = Counter(); ambito_indeterminado = 0
    evidencias = Counter()
    for f in sin:
        adm = str(f["administracion"] or ""); p = provincia(ultimo_parentesis(adm), ip)
        if p: recupera_prov[f["oposicion_id"]] = p; evidencias["PROVINCIA_PARENTESIS"] += 1
        # Ayuntamiento: solo nombre exacto, con provincia como contexto.
        m = re.match(r"^(?:Ayuntamiento|Ajuntament|Concello)\s+(?:de(?:l| la)?|d['’])\s+(.+)$", adm, re.I)
        if m:
            nombre = re.split(r"\s*\(|\s+referente\b|\s*[-,]\s*(?:Organismo|Patronato)", m.group(1),1,flags=re.I)[0].strip()
            mm = municipio_exacto(nombre, im, p)
            if mm:
                recupera_mun[f["oposicion_id"]] = mm["Municipio"]
                recupera_prov[f["oposicion_id"]] = mm["Provincia"]
                evidencias["AYUNTAMIENTO_EXACTO"] += 1
        # Destino provincial cerrado en Puesto.
        for patron in (r"Fiscal[ií]a Provincial de\s+([^,;.()]+)", r"Tribunal Superior de Justicia de\s+([^,;.()]+)"):
            for match in re.finditer(patron, str(f["puesto"] or ""), re.I):
                palabras=match.group(1).split(); candidatos={provincia(" ".join(palabras[:i]),ip) for i in range(1,len(palabras)+1)}-{None}
                if len(candidatos)==1:
                    recupera_prov[f["oposicion_id"]]=next(iter(candidatos)); evidencias["DESTINO_PUESTO"]+=1
        a,c=ambito(adm); ambitos[a]+=1
        if c != "ALTA": ambito_indeterminado += 1

    # Normalización conservadora: solo elimina el último paréntesis provincial validado.
    originales = Counter(str(f["administracion"] or "").strip() for f in filas)
    normalizadas = Counter()
    filas_limpiables = 0
    for adm,n in originales.items():
        par=ultimo_parentesis(adm)
        limpio=adm
        if par and provincia(par,ip):
            limpio=re.sub(r"\s*\([^()]*\)\s*$", "", adm).strip(" ,.;")
            filas_limpiables += n
        normalizadas[limpio]+=n

    cat_parentesis=Counter(x["clasificacion"] for x in detalle_parentesis.values())
    filas_cat_parentesis=Counter()
    for x in detalle_parentesis.values(): filas_cat_parentesis[x["clasificacion"]]+=x["frecuencia"]
    despues = estado_base(ruta)
    if antes != despues: raise RuntimeError("La base cambió durante el análisis")
    return {
        "estado_base": antes,
        "catalogos": {"municipios_oficial":len(mun), "campos":list(mun.columns),
                      "alias_municipios":len(aliases),
                      "alias_provincias_propuestos":ALIAS_PROVINCIAS},
        "buscar_municipio": {"diagnostico":"Subcadenas y elección del nombre más largo sin resolver homónimos ni validar contexto.",
                             "falsos_positivos_reales":FALSOS_POSITIVOS},
        "parentesis": {"filas_con_parentesis":sum(bool(re.findall(r"\(([^()]*)\)",str(f['administracion'] or ''))) for f in filas),
                       "valores_distintos":len(detalle_parentesis), "por_clasificacion_distintos":dict(cat_parentesis),
                       "por_clasificacion_filas":dict(filas_cat_parentesis),
                       "detalle":sorted(detalle_parentesis.values(),key=lambda x:(-x["frecuencia"],x["texto"]))},
        "entidades":resumen_entidades,
        "ambito_12640": {"por_valor":dict(ambitos), "alta":len(sin)-ambito_indeterminado,
                         "indeterminado":ambito_indeterminado},
        "simulacion_12640": {"total":len(sin), "provincia_alta":len(recupera_prov),
                             "municipio_alta":len(recupera_mun),
                             "provincia_restante":len(sin)-len(recupera_prov),
                             "evidencias":dict(evidencias)},
        "administracion_normalizada": {"filas_beneficiadas":filas_limpiables,
                                        "distintas_antes":len(originales), "distintas_despues":len(normalizadas)},
        "administraciones_genericas": {
            "Administración Local":sum(f["administracion"]=="Administración Local" for f in sin),
            "Universidades":sum(f["administracion"]=="Universidades" for f in sin)},
        "universidades": {"total":sum("universidad" in clave(f["administracion"] or "") for f in filas),
                          "genericas_sin_provincia":sum(f["administracion"]=="Universidades" for f in sin)},
    }


def markdown(r):
    s=r["simulacion_12640"]; p=r["parentesis"]; a=r["ambito_12640"]
    lines=["# FASE 3: geografía y ámbito", "",
           "Análisis exclusivamente local y de sólo lectura. No aplica migraciones, no recalcula filas y no modifica SQLite.",
           "", "## Resumen cuantitativo", "",
           f"- Provincia ALTA recuperable: {s['provincia_alta']}",
           f"- Municipio ALTA recuperable: {s['municipio_alta']}",
           f"- Ámbito ALTA: {a['alta']}", f"- Ámbito indeterminado: {a['indeterminado']}",
           f"- Paréntesis distintos: {p['valores_distintos']}",
           f"- Administraciones normalizables: {r['administracion_normalizada']['filas_beneficiadas']}",
           "", "## Ámbito (12.640 sin provincia)", ""]
    lines += [f"- {k}: {v}" for k,v in a["por_valor"].items()]
    lines += ["", "## Inventario de la lógica actual", "",
              "- `plazasboe.py` extrae la administración y encadena el enriquecimiento.",
              "- `resolutor_administraciones.py` y los catálogos de `datos/` constituyen la vía moderna: entidad administrativa, sede, municipio oficial, provincia y código INE.",
              "- `mapa_plazas.py::buscar_municipio()` mantiene una vía histórica paralela basada en coincidencias parciales y selección del nombre más largo.",
              "- `base_datos.py` persiste el resultado ya resuelto; no es el lugar adecuado para inferir geografía.",
              "", "## Diagnóstico de `buscar_municipio()`", "",
              "La coincidencia por palabras o subcadenas no resuelve homónimos, no exige contexto provincial y puede elegir el primer municipio del catálogo. Debe retirarse como fuente autoritativa, manteniendo como única vía el índice oficial exacto.",
              "", "Falsos positivos observados:", "",
              "| Entrada | Municipio erróneo | Provincia errónea |", "|---|---|---|"]
    for entrada, municipio, provincia_erronea in r["buscar_municipio"]["falsos_positivos_reales"]:
        lines.append(f"| {entrada} | {municipio} | {provincia_erronea} |")
    lines += ["", "## Paréntesis administrativos", "",
              "No todo paréntesis es una provincia: también aparecen municipios, islas, comunidades autónomas, comarcas, texto incidental y erratas. La regla segura es aceptar exclusivamente el último paréntesis que coincida de forma exacta con una provincia canónica o un alias provincial aprobado.",
              "", "| Texto | Frecuencia | Clasificación | Canon |", "|---|---:|---|---|"]
    for x in p["detalle"]:
        lines.append(f"| {x['texto']} | {x['frecuencia']} | {x['clasificacion']} | {x['canon']} |")
    lines += ["", "## Normalización de Administración", "",
              f"La separación conservadora `Administración original` / `Administración normalizada` beneficiaría {r['administracion_normalizada']['filas_beneficiadas']} filas y reduciría {r['administracion_normalizada']['distintas_antes']} valores distintos a {r['administracion_normalizada']['distintas_despues']}.",
              "Sólo se elimina el último paréntesis cuando es provincia canónica o alias aprobado. El original debe conservarse siempre para auditoría.",
              "", "## Diseño propuesto del resolutor", "",
              "1. Normalizar sólo ortografía y espacios, conservando el texto original.",
              "2. Extraer por separado entidad, último paréntesis y destinos explícitos del puesto.",
              "3. Resolver provincias únicamente por nombre exacto o alias cerrado.",
              "4. Resolver municipios únicamente por nombre/alias exacto en el catálogo oficial.",
              "5. Filtrar homónimos por provincia y, cuando exista de forma explícita, comunidad autónoma.",
              "6. Resolver sedes institucionales sólo mediante catálogo explícito y versionado.",
              "7. Si dos evidencias de confianza ALTA discrepan, devolver `AMBIGUA`; nunca decidir por prioridad silenciosa.",
              "8. Persistir geografía únicamente con confianza `ALTA`. `MEDIA`, `AMBIGUA` y `NO_ENCONTRADO` quedan para revisión.",
              "", "Prioridad orientativa de evidencias: destino local exacto; municipio exacto con contexto provincial; entidad municipal exacta; provincia explícita entre paréntesis; institución provincial; sede institucional catalogada. La prioridad no anula la regla de conflicto.",
              "", "## Modelo de ámbito", "",
              "- `ESTATAL`: ministerios y órganos estatales, con independencia del destino geográfico.",
              "- `AUTONOMICO`: gobiernos y departamentos de comunidad autónoma.",
              "- `LOCAL`: ayuntamientos, diputaciones, cabildos, consejos insulares, mancomunidades y entidades supramunicipales.",
              "- `OTRO`: universidad o entidad pública nombrada que no encaje en los tres niveles territoriales.",
              "- `INDETERMINADO`: etiqueta genérica, identidad insuficiente o conflicto.",
              "", "El ámbito y la ubicación son dimensiones independientes. Una oposición estatal puede tener destino provincial; una etiqueta `Administración Local` no permite inventar municipio ni provincia.",
              "", "## Casos especiales", "",
              f"- `Administración Local` genérica sin provincia: {r['administraciones_genericas']['Administración Local']}. La identidad detallada se perdió antes de persistir la oposición; sólo puede recuperarse si otra evidencia local exacta la conserva.",
              f"- `Universidades` genérica sin provincia: {r['administraciones_genericas']['Universidades']}. Debe quedar `INDETERMINADO`; una universidad nombrada y catalogada puede ser `OTRO`.",
              "- Diputaciones, cabildos y consejos insulares son `LOCAL`, pero su subtipo debe conservarse en una familia/tipo de entidad separado.",
              "- Una comunidad autónoma sirve como contexto, no como sustituto automático de provincia.",
              "", "## Arquitectura y trazabilidad", "",
              "El resolutor debe devolver un objeto puro con: textos originales y normalizados, entidad/familia, ámbito, municipio, provincia, comunidad, código INE, regla aplicada, evidencia, catálogo y versión, confianza y motivos de descarte/conflicto. La persistencia recibe ese objeto pero no vuelve a inferir.",
              "", "Los tests deben cubrir catálogos canónicos, aliases aprobados, homónimos, conflicto de evidencias, paréntesis no provinciales, idempotencia y todos los falsos positivos de este informe. Un fixture versionado debe fijar entradas, salida esperada, regla y confianza.",
              "", "## Conclusión", "",
              f"De las {s['total']} filas sin provincia, la simulación conservadora recupera {s['provincia_alta']} provincias y {s['municipio_alta']} municipios con confianza ALTA; {s['provincia_restante']} provincias permanecen sin resolver. Es preferible conservar esas ausencias a reintroducir inferencias por subcadena."]
    return "\n".join(lines)+"\n"


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--base-datos",default="datos/boe.db");parser.add_argument("--salida",default="informes/geografia")
    args=parser.parse_args(argv); resultado=analizar(args.base_datos); salida=Path(args.salida);salida.mkdir(parents=True,exist_ok=True)
    (salida/"fase3_geografia_ambito.json").write_text(json.dumps(resultado,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (salida/"fase3_geografia_ambito.md").write_text(markdown(resultado),encoding="utf-8")
    print(json.dumps({"simulacion":resultado["simulacion_12640"],"ambito":resultado["ambito_12640"],"normalizacion":resultado["administracion_normalizada"]},ensure_ascii=False,indent=2))


if __name__ == "__main__": main()
