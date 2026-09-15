"""Auditoría independiente, sólo lectura, de los casos B de Maestros del paso 20."""
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
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as auditar_global

DB = ROOT / "datos/boe.db"
PASO20 = ROOT / "informes/normalizacion_puestos/fase8_paso20_maestros.json"
OUT = ROOT / "informes/normalizacion_puestos/fase8_paso23_maestros_clase_b.json"
CSV_OUT = ROOT / "informes/normalizacion_puestos/fase8_paso23_maestros_clase_b_detalle.csv"
CANON = "Maestro de Educación Infantil"
DECISIONES = {"ASCENDER_A", "MANTENER_B", "BAJAR_C", "BAJAR_D"}
KNOWN_C = (
    "Maestro/a de Educación Infantil de la plantilla de personal laboral fijo",
    "Maestro/a Educación Infantil de la plantilla de personal laboral fijo",
    "Maestro/a de Escuela Infantil",
    "Maestro/a de la plantilla de personal laboral fijo",
)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def estado(path=DB):
    path = Path(path)
    stat = path.stat()
    con = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        metadata = dict(con.execute("SELECT clave, valor FROM metadata"))
        count = lambda table: con.execute(f"SELECT count(*) FROM [{table}]").fetchone()[0] if table in tables else None
        return {
            "sha256": sha(path), "tamano": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            "schema_version": metadata.get("schema_version"), "data_version": metadata.get("data_version"),
            "oposiciones": count("oposiciones"),
            "plazas": con.execute("SELECT coalesce(sum(num_plazas),0) FROM oposiciones").fetchone()[0],
            "publicaciones": count("publicaciones"), "busquedas": count("busquedas"), "cobertura": count("cobertura"),
            "integrity_check": con.execute("PRAGMA integrity_check").fetchone()[0],
            "foreign_key_check": [list(x) for x in con.execute("PRAGMA foreign_key_check")],
            "wal_existe": path.with_name(path.name + "-wal").exists(),
            "shm_existe": path.with_name(path.name + "-shm").exists(),
        }
    finally:
        con.close()


def git_state():
    def run(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True)
    return {"rama": run("branch", "--show-current"), "head": run("rev-parse", "HEAD"),
            "origin_main": run("rev-parse", "origin/main"), "status_short": run("status", "--short"),
            "diff_stat": run("diff", "--stat")}


def clave(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    return re.sub(r"\s+", " ", text.strip())


def estructural(text):
    """Clave determinista; no fuzzy matching ni similitud."""
    value = clave(text)
    value = value.replace("/", " o ").replace("-", " ")
    value = re.sub(r"[()]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\bmaestras\b", "maestra", value)
    value = re.sub(r"\bmaestros\b", "maestro", value)
    return value


def variantes_controladas(text):
    forms = {text, text.lower(), text.replace("/", " o "), text.replace("-", " ")}
    if "(" in text and ")" in text:
        forms.add(re.sub(r"\s*\([^)]*\)", "", text).strip())
        forms.add(re.sub(r"[()]", "", text))
    return sorted(forms)


def cargar_b():
    data = json.loads(PASO20.read_text(encoding="utf-8"))
    clas = data["clasificacion_seguridad"]["B"]
    if clas["filas"] != 4 or clas["plazas"] != 11:
        raise RuntimeError("La reconstrucción B del paso 20 no contiene 4 filas / 11 plazas")
    records = {r["oposicion_id"]: r for r in data["registros"] if r.get("seguridad") == "B"}
    ids = sorted(clas["ids"])
    if sorted(records) != ids or len(records) != 4:
        raise RuntimeError("Los registros B no coinciden con la clasificación reproducible del paso 20")
    if sum(float(r["plazas"] or 0) for r in records.values()) != 11:
        raise RuntimeError("Las plazas reconstruidas no suman 11")
    return data, [records[i] for i in ids]


def leer_corpus(con):
    return [dict(r) for r in con.execute("""SELECT oposicion_id, num_plazas AS plazas, puesto,
        puesto_normalizado, administracion, administracion_normalizada, ambito, tipo_entidad,
        fecha_boe, municipio, provincia, escala, subescala, clase, sistema, turno, publicacion_id
        FROM oposiciones""")]


def ficha(record, corpus):
    text = record["puesto"]
    exact = [r for r in corpus if r["puesto"] == text]
    forms = variantes_controladas(text)
    structural_matches = [r for r in corpus if estructural(r["puesto"]) == estructural(text)]
    paren = re.search(r"\(([^)]*)\)", text)
    return {
        "id": record["oposicion_id"], "denominacion": text, "plazas": record["plazas"],
        "clasificacion_paso20": "B", "administracion": record["administracion"],
        "administracion_normalizada": record.get("administracion_normalizada"),
        "ambito": record["ambito"], "tipo_entidad": record["tipo_entidad"],
        "ano": (record["fecha_boe"] or "")[:4], "fecha_boe": record["fecha_boe"],
        "municipio": record["municipio"], "provincia": record["provincia"],
        "escala": record["escala"], "subescala": record["subescala"], "clase": record["clase"],
        "sistema": record["sistema"], "puesto_normalizado_actual": record["puesto_normalizado"],
        "normalizar_puesto_actual": normalizar_puesto(text), "canon_potencial": CANON,
        "motivo_original_b": record.get("motivo"), "especialidad": "Educación Infantil",
        "analisis_plural": {
            "forma": "plural" if re.search(r"\bMaestr(?:os|as)\b", text, re.I) else "singular",
            "lectura": "morfología plural compatible con varias plazas, pero el corpus local no acredita por sí solo cuerpo docente oficial",
            "clasificacion_elemento": "incierto_semantico",
        },
        "analisis_parentesis": {
            "contenido": paren.group(1) if paren else None,
            "tipo": "especialidad" if paren else "no_aplica",
            "clasificacion_elemento": "semantico_significativo" if paren else "no_aplica",
            "lectura": "Educación Infantil dentro del paréntesis identifica especialidad; no se elimina como mero adorno",
        },
        "elementos_adicionales": {
            "centro": bool(re.search(r"escuela|centro|guarder", clave(text))),
            "laboral": bool(re.search(r"laboral|plantilla|personal", clave(text))),
            "cuerpo": bool(re.search(r"cuerpo|funcionari", clave(text))),
            "funcion": False,
            "numero": bool(re.search(r"\d", text)),
        },
        "repeticiones_exactas": {
            "filas": len(exact), "plazas": sum(float(r["plazas"] or 0) for r in exact),
            "ids": sorted(r["oposicion_id"] for r in exact),
            "anos": sorted({(r["fecha_boe"] or "")[:4] for r in exact}),
            "administraciones": sorted({r["administracion"] or "" for r in exact}),
            "canones_persistidos": sorted({r["puesto_normalizado"] or "" for r in exact}),
        },
        "variantes_ortotipograficas": {
            "formas_controladas": forms,
            "clave_estructural": estructural(text),
            "filas_capturadas_clave": len(structural_matches),
            "ids_capturados_clave": sorted(r["oposicion_id"] for r in structural_matches),
            "denominaciones_capturadas_clave": sorted({r["puesto"] for r in structural_matches}),
        },
    }


def clasificar(ficha_data):
    # La condición A exige prueba positiva de equivalencia, no sólo parecido.
    return {
        "id": ficha_data["id"], "denominacion": ficha_data["denominacion"],
        "plazas": ficha_data["plazas"], "clasificacion_paso20": "B", "clasificacion_paso23": "B",
        "canon_potencial": CANON, "evidencia": [
            "La especialidad Educación Infantil aparece completa",
            "La variación de género/número es compatible con una categoría plural",
            "No existe evidencia suficiente en los campos disponibles para demostrar cuerpo docente o equivalencia contractual",
        ],
        "riesgo": "singularizar una categoría municipal plural o reinterpretar una especialidad como nombre individual",
        "decision": "MANTENER_B",
    }


def auditar(ruta_bd=DB):
    before = estado(ruta_bd)
    normalizer_before = sha(ROOT / "normalizacion_puestos.py")
    data, originals = cargar_b()
    con = sqlite3.connect(f"file:{Path(ruta_bd).resolve()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        corpus = leer_corpus(con)
    finally:
        con.close()
    by_id = {r["oposicion_id"]: r for r in corpus}
    if sorted(by_id[i]["oposicion_id"] for i in [r["oposicion_id"] for r in originals]) != sorted(r["oposicion_id"] for r in originals):
        raise RuntimeError("IDs B ausentes en SQLite")
    fichas = [ficha(by_id[r["oposicion_id"]], corpus) for r in originals]
    clasificaciones = [clasificar(f) for f in fichas]
    conocidos_c = [{"denominacion": text, "filas": sum(r["puesto"] == text for r in corpus),
                    "ids": sorted(r["oposicion_id"] for r in corpus if r["puesto"] == text),
                    "absorbida_por_simulacion": False} for text in KNOWN_C]
    conjuntos = [{"canon": CANON, "variantes": [f["denominacion"] for f in fichas],
                  "ids": [f["id"] for f in fichas], "filas": 4, "plazas": 11,
                  "administraciones": sorted({f["administracion"] for f in fichas}),
                  "anos": sorted({f["ano"] for f in fichas}),
                  "clasificacion_final": "B", "riesgo_colision": "alto: plural local y paréntesis no demuestran equivalencia individual"}]
    gate = auditar_global(ruta_bd)
    after = estado(ruta_bd)
    normalizer_after = sha(ROOT / "normalizacion_puestos.py")
    if before != after:
        raise RuntimeError("SQLite cambió durante auditoría de solo lectura")
    simulations = [{"conjunto": "plural_y_parentesis_educacion_infantil", "regla": None,
                    "motivo_no_propuesta": "ningún conjunto supera simultáneamente los criterios 1–12 de 23P",
                    "esperados": [], "obtenidos": [], "faltantes": [], "inesperados": [],
                    "usa_fuzzy": False, "usa_ids_como_criterio": False,
                    "casos_c_no_absorbidos": conocidos_c}]
    return {
        "version": "fase8-paso23-v1", "generado_utc": datetime.now(timezone.utc).isoformat(),
        "modo": "read-only", "git": git_state(), "baseline": before,
        "reconstruccion_paso20": {"informe": str(PASO20), "filas": 4, "plazas": 11,
                                  "ids": [r["oposicion_id"] for r in originals],
                                  "clasificacion_original": "B", "denominaciones": [r["puesto"] for r in originals]},
        "casos": fichas, "clasificacion_individual": clasificaciones, "conjuntos": conjuntos,
        "comparacion_casos_c": conocidos_c,
        "simulaciones": simulations,
        "puerta_global_paso19": {"total_discrepancias": gate["total_discrepancias"],
            "total_plazas_discrepantes": gate["total_plazas_discrepantes"],
            "cambios_reales_recalculables": gate["cambios_reales_recalculables"]["filas"],
            "discrepancias_contextuales_no_recalculables": gate["discrepancias_contextuales_no_recalculables"]["filas"],
            "discrepancias_no_clasificables_automaticamente": gate["discrepancias_no_clasificables_automaticamente"]["filas"]},
        "normalizador_sha256_inicial": normalizer_before, "normalizador_sha256_final": normalizer_after,
        "normalizador_modificado": normalizer_before != normalizer_after,
        "sqlite_final": after, "sqlite_modificada": before != after,
        "ascensos": {"filas": 0, "plazas": 0, "ids": [], "decision": "ninguno"},
        "recomendacion_paso24": "No implementar reglas: los cuatro casos permanecen B y esta microfamilia queda cerrada sin aplicación.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bd", type=Path, default=DB)
    parser.add_argument("--salida", type=Path, default=OUT)
    parser.add_argument("--csv", type=Path, default=CSV_OUT)
    args = parser.parse_args()
    report = auditar(args.bd)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with args.csv.open("w", newline="", encoding="utf-8") as fh:
        fields = ["id", "denominacion", "plazas", "clasificacion_paso20", "clasificacion_paso23", "canon_potencial", "decision", "riesgo", "evidencia"]
        writer = csv.DictWriter(fh, fieldnames=fields); writer.writeheader()
        writer.writerows({**row, "evidencia": " | ".join(row["evidencia"])} for row in report["clasificacion_individual"])
    print(json.dumps({"ids": report["reconstruccion_paso20"]["ids"], "ascensos": report["ascensos"],
                      "gate": report["puerta_global_paso19"], "sqlite_modificada": report["sqlite_modificada"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
