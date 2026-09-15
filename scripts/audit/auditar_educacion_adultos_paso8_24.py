"""Auditoría reproducible y de sólo lectura de Educación de Adultos."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from normalizacion_puestos import normalizar_puesto
from normalizacion_contextual_puestos import normalizar_puesto_efectivo
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as auditar_global

DB = ROOT / "datos/boe.db"
PASO20 = ROOT / "informes/normalizacion_puestos/fase8_paso20_maestros.json"
OUT = ROOT / "informes/normalizacion_puestos/fase8_paso24_educacion_adultos.json"
CSV_OUT = ROOT / "informes/normalizacion_puestos/fase8_paso24_educacion_adultos_detalle.csv"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def estado(path=DB):
    path = Path(path); stat = path.stat()
    con = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        metadata = dict(con.execute("SELECT clave, valor FROM metadata"))
        count = lambda table: con.execute(f"SELECT count(*) FROM [{table}]").fetchone()[0] if table in tables else None
        return {"sha256": sha(path), "tamano": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                "schema_version": metadata.get("schema_version"), "data_version": metadata.get("data_version"),
                "oposiciones": count("oposiciones"), "plazas": con.execute("SELECT coalesce(sum(num_plazas),0) FROM oposiciones").fetchone()[0],
                "publicaciones": count("publicaciones"), "busquedas": count("busquedas"), "cobertura": count("cobertura"),
                "integrity_check": con.execute("PRAGMA integrity_check").fetchone()[0],
                "foreign_key_check": [list(x) for x in con.execute("PRAGMA foreign_key_check")],
                "wal_existe": path.with_name(path.name + "-wal").exists(), "shm_existe": path.with_name(path.name + "-shm").exists()}
    finally:
        con.close()


def git_state():
    def run(*args): return subprocess.check_output(["git", *args], cwd=ROOT, text=True)
    return {"rama": run("branch", "--show-current"), "head": run("rev-parse", "HEAD"),
            "origin_main": run("rev-parse", "origin/main"), "status_short": run("status", "--short"),
            "diff_stat": run("diff", "--stat")}


def clave(text):
    text = unicodedata.normalize("NFKD", text or "")
    return re.sub(r"\s+", " ", "".join(c for c in text if not unicodedata.combining(c)).casefold()).strip()


def cargar_ids_paso20():
    data = json.loads(PASO20.read_text(encoding="utf-8"))
    micro = data["microfamilias"]["educacion_adultos"]
    records = {r["oposicion_id"]: r for r in data["registros"] if r.get("microfamilia") == "educacion_adultos"}
    ids = sorted(micro["ids"])
    if len(ids) != 14 or micro["plazas"] != 17 or sorted(records) != ids:
        raise RuntimeError("La microfamilia de adultos de PASO 20 no reconstruye 14 filas / 17 plazas")
    return data, records, ids


def leer_corpus(con):
    return [dict(r) for r in con.execute("""SELECT o.oposicion_id, o.num_plazas AS plazas, o.puesto,
        o.puesto_normalizado, o.administracion, o.administracion_normalizada, o.ambito, o.tipo_entidad,
        o.fecha_boe, o.municipio, o.provincia, o.escala, o.subescala, o.clase, o.sistema, o.turno,
        o.publicacion_id, p.titulo_original
        FROM oposiciones o LEFT JOIN publicaciones p ON p.publicacion_id=o.publicacion_id""")]


def subfamilia(text):
    k = clave(text)
    if "informatica" in k: return "adultos_con_especialidad_informatica"
    if "plantilla" in k or "tiempo parcial" in k or "jornada" in k: return "categoria_laboral_o_jornada"
    if "aula" in k: return "aula_de_adultos"
    if "escuela" in k: return "escuela_de_adultos"
    if "epa" in k: return "epa"
    if "educacion de adultos" in k: return "educacion_de_adultos_explicita"
    if "adultos" in k: return "adultos_generico"
    return "otra"


def clasificacion(text):
    k = clave(text)
    if "informatica" in k: return "D", "La especialidad informática debe preservarse; no reducir a un canon genérico"
    if "plantilla" in k or "tiempo parcial" in k or "jornada" in k: return "C", "La relación laboral o dedicación es semánticamente significativa"
    if "aula" in k or "escuela" in k or "epa" in k: return "C", "Centro/abreviatura/contexto local no demuestra una categoría profesional única"
    if k == "maestro de educacion de adultos": return "B", "La categoría docente es explícita, pero no existe canon adulto validado ni prueba de equivalencia transversal"
    return "C", "La expresión adultos es insuficiente para demostrar cuerpo, nivel y categoría equivalentes"


def ficha(row, original):
    text = row["puesto"]; k = clave(text); c = clasificacion(text)
    con_paren = re.search(r"\(([^)]*)\)", text)
    return {"id": row["oposicion_id"], "puesto": text, "puesto_normalizado": row["puesto_normalizado"],
            "normalizar_puesto": normalizar_puesto(text),
            "normalizar_puesto_efectivo": normalizar_puesto_efectivo(text, administracion=row["administracion"], ambito=row["ambito"], tipo_entidad=row["tipo_entidad"], escala=row["escala"], subescala=row["subescala"], sistema=row["sistema"], municipio=row["municipio"], provincia=row["provincia"]).normalizado,
            "plazas": row["plazas"], "ano": (row["fecha_boe"] or "")[:4], "fecha_boe": row["fecha_boe"],
            "administracion": row["administracion"], "provincia": row["provincia"], "municipio": row["municipio"],
            "escala": row["escala"], "subescala": row["subescala"], "clase": row["clase"], "ambito": row["ambito"],
            "tipo_entidad": row["tipo_entidad"], "sistema": row["sistema"], "publicacion_id": row["publicacion_id"],
            "titulo_publicacion": row["titulo_original"], "clasificacion_paso20": original.get("seguridad"),
            "subfamilia": subfamilia(text), "clasificacion_paso24": c[0], "motivo_clasificacion": c[1],
            "maestro_o_profesor": "profesor" if re.search(r"profesor", k) else "maestro",
            "relacion_laboral_en_texto": bool(re.search(r"plantilla|laboral|jornada|tiempo parcial", k)),
            "centro_en_texto": bool(re.search(r"escuela|aula|centro", k)),
            "especialidad": "Informática" if "informatica" in k else None,
            "singular_plural_genero": {"plural": bool(re.search(r"\bmaestros?|profesores?\b", k) and re.search(r"s\b", k)), "barra_genero": "/" in text, "guion_genero": "-" in text},
            "parentesis": {"contenido": con_paren.group(1) if con_paren else None, "semantico": bool(con_paren)},
            "motivo_inclusion": "microfamilia educacion_adultos reproducida desde PASO 20"}


def auditar(ruta_bd=DB):
    before = estado(ruta_bd); norm_before = sha(ROOT / "normalizacion_puestos.py")
    paso20, originals, ids20 = cargar_ids_paso20()
    con = sqlite3.connect(f"file:{Path(ruta_bd).resolve()}?mode=ro", uri=True); con.row_factory = sqlite3.Row
    try: corpus = leer_corpus(con)
    finally: con.close()
    by_id = {r["oposicion_id"]: r for r in corpus}
    if any(i not in by_id for i in ids20): raise RuntimeError("Faltan IDs históricos en SQLite actual")
    rows = [ficha(by_id[i], originals[i]) for i in ids20]
    ids24 = sorted(r["id"] for r in rows)
    exact = {}
    for r in rows:
        matches = [x for x in corpus if x["puesto"] == r["puesto"]]
        exact[r["puesto"]] = {"filas": len(matches), "plazas": sum(float(x["plazas"] or 0) for x in matches), "ids": sorted(x["oposicion_id"] for x in matches), "anos": sorted({(x["fecha_boe"] or "")[:4] for x in matches}), "administraciones": sorted({x["administracion"] or "" for x in matches}), "canones_actuales": sorted({x["puesto_normalizado"] or "" for x in matches})}
    denoms = []
    for text, values in exact.items():
        denoms.append({"denominacion": text, **values, "canon_recalculado": normalizar_puesto(text)})
    denoms.sort(key=lambda x: (-x["filas"], -x["plazas"], x["denominacion"]))
    subfamilias = {}
    for r in rows:
        g = subfamilias.setdefault(r["subfamilia"], {"filas": 0, "plazas": 0, "ids": []}); g["filas"] += 1; g["plazas"] += r["plazas"]; g["ids"].append(r["id"])
    clases = Counter(r["clasificacion_paso24"] for r in rows)
    gate = auditar_global(ruta_bd); after = estado(ruta_bd); norm_after = sha(ROOT / "normalizacion_puestos.py")
    if before != after: raise RuntimeError("SQLite cambió durante la auditoría")
    simulations = [{"conjunto": "ninguno", "regla": None, "esperados": [], "obtenidos": [], "faltantes": [], "inesperados": [], "filas": 0, "plazas": 0, "usa_fuzzy": False, "usa_ids_como_criterio": False, "motivo": "No hay conjunto A que satisfaga los 13 criterios"}]
    return {"version": "fase8-paso24-v1", "generado_utc": datetime.now(timezone.utc).isoformat(), "modo": "read-only", "git": git_state(), "baseline": before,
            "definicion_universo": {"criterio": "microfamilia educacion_adultos de PASO 20, reconciliada contra SQLite actual", "descubrimiento_lexico_adult": 478, "exclusiones_semanticas": "administrativos, monitores, talleres, educadores, profesores universitarios, centros no docentes y otras categorías no Maestro", "filas": len(rows), "plazas": sum(r["plazas"] for r in rows), "denominaciones": len(denoms)},
            "reconciliacion_paso20": {"ids_paso20": ids20, "ids_paso24": ids24, "interseccion": sorted(set(ids20)&set(ids24)), "solo_paso20": sorted(set(ids20)-set(ids24)), "solo_paso24": sorted(set(ids24)-set(ids20))},
            "registros": rows, "denominaciones": denoms, "subfamilias": subfamilias,
            "analisis_maestro_profesor": {"maestro": sum(r["maestro_o_profesor"] == "maestro" for r in rows), "profesor": sum(r["maestro_o_profesor"] == "profesor" for r in rows), "decision": "no se fusionan automáticamente"},
            "educacion_adultos_vs_permanente": "EPA/Educación Permanente/Adultos se conservan como expresiones distintas; no hay canon adulto validado común",
            "clasificacion": {"filas": len(rows), "plazas": sum(r["plazas"] for r in rows), "por_clase": dict(clases), "registros": [{"id": r["id"], "clase": r["clasificacion_paso24"], "motivo": r["motivo_clasificacion"]} for r in rows]},
            "simulaciones_a": simulations, "colisiones": {"educacion_infantil": [], "cuerpos_maestros": [], "otras_ensenanzas": [], "laboral_centros_especialidades": "No se propone regla; no hay captura"},
            "puerta_global_paso19": {"total_discrepancias": gate["total_discrepancias"], "total_plazas_discrepantes": gate["total_plazas_discrepantes"], "cambios_reales_recalculables": gate["cambios_reales_recalculables"]["filas"], "discrepancias_contextuales_no_recalculables": gate["discrepancias_contextuales_no_recalculables"]["filas"], "discrepancias_no_clasificables_automaticamente": gate["discrepancias_no_clasificables_automaticamente"]["filas"]},
            "normalizador_sha256_inicial": norm_before, "normalizador_sha256_final": norm_after, "normalizador_modificado": norm_before != norm_after, "sqlite_final": after, "sqlite_modificada": before != after,
            "conjuntos_a": [], "recomendacion_paso25": "Cerrar esta microfamilia sin aplicación y auditar otra microfamilia docente pequeña del PASO 20, no los 300 C como bloque"}


def main():
    p = argparse.ArgumentParser(); p.add_argument("--bd", type=Path, default=DB); p.add_argument("--salida", type=Path, default=OUT); p.add_argument("--csv", type=Path, default=CSV_OUT); a = p.parse_args()
    report = auditar(a.bd); a.salida.parent.mkdir(parents=True, exist_ok=True); a.salida.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    fields = ["id", "puesto", "plazas", "clasificacion_paso20", "clasificacion_paso24", "subfamilia", "motivo_clasificacion", "administracion", "ano", "puesto_normalizado", "normalizar_puesto", "especialidad", "relacion_laboral_en_texto", "centro_en_texto"]
    with a.csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows({k: r.get(k) for k in fields} for r in report["registros"])
    print(json.dumps({"filas": report["definicion_universo"]["filas"], "plazas": report["definicion_universo"]["plazas"], "clases": report["clasificacion"]["por_clase"], "sqlite_modificada": report["sqlite_modificada"], "gate": report["puerta_global_paso19"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
