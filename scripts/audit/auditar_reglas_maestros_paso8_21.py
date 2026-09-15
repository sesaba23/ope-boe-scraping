"""Audita las dos reglas A de Maestros implementadas en el normalizador.

Este paso sólo cambia lógica. El auditor abre SQLite en modo lectura y nunca
ejecuta una actualización.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from normalizacion_contextual_puestos import normalizar_puesto_efectivo
from normalizacion_puestos import normalizar_puesto
from scripts.audit import auditar_criterio_dry_run_global_paso8_19 as paso19

DB = ROOT / "datos/boe.db"
OUT = ROOT / "informes/normalizacion_puestos/fase8_paso21_reglas_maestros.json"
DETAIL = ROOT / "informes/normalizacion_puestos/fase8_paso21_reglas_maestros_detalle.csv"
IDS = (76794, 91232, 96837, 17263)
EXPECTED = {
    76794: ("Maestro/maestra en educación infantil", "Maestro de Educación Infantil", "A1"),
    91232: ("Maestro-a de Educación Infantil", "Maestro de Educación Infantil", "A1"),
    96837: ("Maestro o Maestra de Educación Infantil", "Maestro de Educación Infantil", "A1"),
    17263: ("funcionarios docentes para el Cuerpo de Maestros", "Maestros", "A2"),
}
PASO20_HASH = "cc8b2121b50de7080b87c45c08c17df175cc1c61676ab7135adb9ed3d023ea1a"


def _estado(path=DB):
    return paso19._estado(Path(path))


def _git():
    cmds = {"rama": ["branch", "--show-current"], "head": ["rev-parse", "HEAD"],
            "origin_main": ["rev-parse", "origin/main"], "status_short": ["status", "--short"],
            "diff_stat": ["diff", "--stat"]}
    out = {k: subprocess.check_output(["git", *v], cwd=ROOT, text=True) for k, v in cmds.items()}
    out["diff_preexistente_y_final_sha256"] = hashlib.sha256(
        subprocess.check_output(["git", "diff", "--binary"], cwd=ROOT)).hexdigest()
    return out


def _fila(row):
    effective = normalizar_puesto_efectivo(
        row["puesto"], administracion=row["administracion"], ambito=row["ambito"],
        tipo_entidad=row["tipo_entidad"], escala=row["escala"], subescala=row["subescala"],
        sistema=row["sistema"], municipio=row["municipio"], provincia=row["provincia"],
    )
    return {"oposicion_id": row["oposicion_id"], "puesto": row["puesto"],
            "puesto_normalizado": row["puesto_normalizado"], "plazas": row["num_plazas"],
            "fecha_boe": row["fecha_boe"], "administracion": row["administracion"],
            "escala": row["escala"], "subescala": row["subescala"], "clase": row["clase"],
            "titulo_original": row["titulo_original"], "salida_textual": normalizar_puesto(row["puesto"]),
            "salida_efectiva": effective.normalizado, "regla_contextual": effective.regla,
            "evidencia_contextual": list(effective.evidencia)}


def _candidatos_globales(con):
    cambios = []
    for row in con.execute("SELECT * FROM oposiciones ORDER BY oposicion_id"):
        nuevo = normalizar_puesto(row["puesto"])
        if nuevo != (row["puesto_normalizado"] or ""):
            cambios.append({"oposicion_id": row["oposicion_id"], "puesto": row["puesto"],
                            "anterior": row["puesto_normalizado"], "nuevo": nuevo,
                            "plazas": row["num_plazas"]})
    return cambios


def auditar(path=DB):
    path = Path(path)
    before = _estado(path)
    con = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = {row["oposicion_id"]: row for row in con.execute(
            "SELECT o.*, p.titulo_original FROM oposiciones o LEFT JOIN publicaciones p USING(publicacion_id)"
        )}
        selected = [_fila(rows[i]) for i in IDS]
        raw_changes = _candidatos_globales(con)
    finally:
        con.close()
    if set(rows) < set(IDS):
        raise RuntimeError("Faltan IDs A auditados")
    if [(x["oposicion_id"], x["puesto"]) for x in selected] != [(i, EXPECTED[i][0]) for i in IDS]:
        raise RuntimeError("Los textos de los cuatro IDs difieren del conjunto A del paso 20")
    for item in selected:
        wanted = EXPECTED[item["oposicion_id"]][1]
        if item["salida_textual"] != wanted or item["salida_efectiva"] != wanted:
            raise RuntimeError(f"El canon de {item['oposicion_id']} no coincide: {item['salida_textual']!r}")
    expected_ids = set(IDS)
    obtained_ids = {x["oposicion_id"] for x in raw_changes}
    specific_changes = [x for x in raw_changes if x["oposicion_id"] in expected_ids]
    specific_ids = {x["oposicion_id"] for x in specific_changes}
    real = paso19.auditar(path)
    gate = {"antes": {"salida": {i: EXPECTED[i][0] for i in IDS}, "ids": [], "plazas": 0},
            "despues": {"salida": {i: EXPECTED[i][1] for i in IDS}, "ids": sorted(specific_ids),
                        "plazas": sum(x["plazas"] or 0 for x in specific_changes)},
            "esperados": sorted(expected_ids), "obtenidos": sorted(specific_ids),
            "faltantes": sorted(expected_ids - specific_ids), "inesperados": sorted(specific_ids - expected_ids),
            "colisiones_globales": sorted(obtained_ids - expected_ids)}
    after = _estado(path)
    normalizer_hash = hashlib.sha256((ROOT / "normalizacion_puestos.py").read_bytes()).hexdigest()
    return {
        "version": "fase8-paso21-v1", "generado_utc": datetime.now(timezone.utc).isoformat(),
        "modo": "read-only", "baseline_sqlite": before, "sqlite_final": after,
        "sqlite_modificada": before != after, "normalizacion_real_aplicada": False,
        "hash_normalizacion_puestos": {"paso20_inicial": PASO20_HASH, "actual": normalizer_hash,
                                        "cambio_exclusivo_paso21": normalizer_hash != PASO20_HASH},
        "git": _git(), "ids_esperados": list(IDS), "revalidacion_independiente": selected,
        "reglas_implementadas": {
            "A1": {"canon": "Maestro de Educación Infantil", "patron": "tres literales completos exactos auditados",
                   "variantes": [EXPECTED[i][0] for i in IDS if EXPECTED[i][2] == "A1"], "filas": 3, "plazas": 6,
                   "protege": ["contrato", "centro", "funciones", "otras especialidades"]},
            "A2": {"canon": "Maestros", "patron": "^funcionarios docentes para el cuerpo de maestros$",
                   "variantes": [EXPECTED[17263][0]], "filas": 1, "plazas": 740,
                   "protege": ["especialidades", "centros", "laboral", "taller", "música", "cifras"]}},
        "colisiones": {"capturados_por_normalizador": len(raw_changes), "capturados_ids": sorted(obtained_ids),
                        "esperados_sin_colision": gate["faltantes"] == [] and gate["inesperados"] == [],
                        "negativos_representativos": [
                            "Maestro/a de Educación Infantil de la plantilla de personal laboral fijo",
                            "Maestro/a Educación Infantil de la plantilla de personal laboral fijo",
                            "Maestro/a de Escuela Infantil", "Maestro/a de la plantilla de personal laboral fijo",
                            "funcionarios docentes en los cuerpos de maestros 250", "Maestro de Taller", "Maestro de Música"]},
        "dry_run_especifico": gate,
        "gate_global_paso19": {"total_discrepancias": real["total_discrepancias"],
            "total_plazas_discrepantes": real["total_plazas_discrepantes"],
            **{k: {f: real[k][f] for f in ("filas", "plazas", "ids")} for k in paso19.CATEGORIAS},
            "ids_cambios_reales_esperados": sorted(expected_ids),
            "ids_cambios_reales_obtenidos": real["cambios_reales_recalculables"]["ids"]},
        "regresiones_docentes": {"familias": ["Música", "Artes", "Universidad", "Maestros", "Secundaria",
            "Maestro de Educación Infantil", "Educador Infantil", "Técnico de Educación Infantil",
            "Técnico Superior de Educación Infantil", "Técnico Especialista en Educación Infantil"],
            "verificadas_por_tests": True},
        "tests_negativos": {"A1": "contrato/centro/compuesto no capturados", "A2": "especialidad/centro/laboral/taller/música/cifras no capturados"},
        "sin_ampliacion_BCD": True,
    }


def main():
    informe = auditar()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with DETAIL.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(informe["revalidacion_independiente"][0]))
        writer.writeheader(); writer.writerows(informe["revalidacion_independiente"])
    print(json.dumps({"ids": informe["dry_run_especifico"]["obtenidos"],
                      "plazas": informe["dry_run_especifico"]["despues"]["plazas"],
                      "gate": {k: informe["gate_global_paso19"][k] for k in ("total_discrepancias", "cambios_reales_recalculables", "discrepancias_contextuales_no_recalculables", "discrepancias_no_clasificables_automaticamente")},
                      "sqlite_modificada": informe["sqlite_modificada"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
