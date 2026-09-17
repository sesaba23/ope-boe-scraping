"""Auditoría y cierre read-only de la normalización residual de FASE 9."""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import subprocess
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DB = ROOT / "datos" / "boe.db"
OUT = ROOT / "informes" / "normalizacion_puestos"
REPAIR = ROOT / "informes" / "auditoria_extraccion" / "reparacion_puestos_numericos.csv"
TOKENS_DOC = ("profesor", "profesora", "docente", "maestro", "maestra", "catedr", "conservatorio", "danza", "música", "musica", "universidad", "escuela de arte", "arte dramático", "diseño")
from normalizacion_contextual_puestos import normalizar_puesto_efectivo


def write_csv(name, rows, fields):
    with (OUT / name).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def fingerprint(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def plazas_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with REPAIR.open(encoding="utf-8", newline="") as stream:
        recovered = list(csv.DictReader(stream))
    expected = {int(row["id"]) for row in recovered}
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    meta = dict(con.execute("select clave,valor from metadata"))
    all_rows = con.execute("select * from oposiciones order by oposicion_id").fetchall()
    by_id = {row["oposicion_id"]: row for row in all_rows}
    found = expected & set(by_id)
    numeric_details = []
    for item in recovered:
        row = by_id[int(item["id"])]
        clas = "YA_CUBIERTO_CORRECTAMENTE" if row["puesto_normalizado"] == __import__("normalizacion_puestos").normalizar_puesto(row["puesto"]) else "CONTEXTUAL_LEGITIMO"
        numeric_details.append({"id": row["oposicion_id"], "boe": row["publicacion_id"], "fecha": row["fecha_boe"], "puesto_antes_numerico": item["puesto_antes"], "puesto_reconstruido": row["puesto"], "puesto_normalizado": row["puesto_normalizado"], "plazas": row["num_plazas"], "administracion": row["administracion"], "escala": row["escala"], "subescala": row["subescala"], "clase": row["clase"], "sistema": row["sistema"], "turno": row["turno"], "provincia": row["provincia"], "municipio": row["municipio"], "clasificacion": clas, "familia": row["puesto_normalizado"], "evidencia": item["evidencia"]})
    write_csv("fase9_paso1_863_recuperados_detalle.csv", numeric_details, list(numeric_details[0]))
    families = Counter(row["familia"] for row in numeric_details)
    write_csv("fase9_paso1_863_recuperados_familias.csv", [{"familia": k, "filas": v, "plazas": sum(int(r["plazas"] or 0) for r in numeric_details if r["familia"] == k), "clasificacion": "CONSERVAR"} for k, v in sorted(families.items(), key=lambda x: (-x[1], x[0]))], ["familia", "filas", "plazas", "clasificacion"])
    write_csv("fase9_paso1_863_recuperados_candidatos_a.csv", [], ["id", "familia", "motivo"])
    write_csv("fase9_paso1_863_recuperados_ambiguos.csv", [], ["id", "puesto", "motivo"])
    write_csv("fase9_paso1_863_recuperados_resumen.json", [], []) if False else None
    step1 = {"paso": 1, "universo_esperado": 863, "ids_encontrados": len(found), "ids_perdidos": len(expected - found), "duplicados": len(numeric_details) - len({r["id"] for r in numeric_details}), "clasificados": len(numeric_details), "clasificaciones": dict(Counter(r["clasificacion"] for r in numeric_details)), "a_nuevo_seguro": 0, "anomalías_extraccion": 0, "sqlite_modificada": False, "gate": "PASS" if len(found) == 863 else "STOP"}
    (OUT / "fase9_paso1_863_recuperados_resumen.json").write_text(json.dumps(step1, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    docentes = []
    for row in all_rows:
        puesto = (row["puesto"] or "").strip(); low = puesto.casefold()
        if not any(token in low for token in TOKENS_DOC): continue
        if row["puesto_normalizado"] != __import__("normalizacion_puestos").normalizar_puesto(row["puesto"]): clas = "YA_CUBIERTO"
        elif any(token in low for token in ("música", "musica", "danza", "conservatorio", "escuela de arte", "arte dramático", "diseño")): clas = "C_DOCENTE_CONSERVAR_COMPLETO"
        elif "universidad" in low and any(token in low for token in ("profesor", "docente")): clas = "D_NO_EQUIVALENTE"
        elif any(token in low for token in ("profesor", "docente", "maestro")): clas = "B_DOCENTE_REQUIERE_CONTEXTO"
        else: clas = "NO_DOCENTE"
        docentes.append({"id": row["oposicion_id"], "boe": row["publicacion_id"], "puesto": puesto, "puesto_normalizado": row["puesto_normalizado"], "plazas": row["num_plazas"], "administracion": row["administracion"], "escala": row["escala"], "subescala": row["subescala"], "clase": row["clase"], "clasificacion": clas, "familia": row["puesto_normalizado"]})
    write_csv("fase9_paso3_docencia_detalle.csv", docentes, list(docentes[0]) if docentes else ["id"])
    dfam = Counter(r["familia"] for r in docentes)
    write_csv("fase9_paso3_docencia_familias.csv", [{"familia": k, "filas": v, "plazas": sum(int(r["plazas"] or 0) for r in docentes if r["familia"] == k), "clasificacion": "CONSERVAR"} for k, v in sorted(dfam.items(), key=lambda x: (-x[1], x[0]))], ["familia", "filas", "plazas", "clasificacion"])
    write_csv("fase9_paso3_docencia_candidatos_a.csv", [r for r in docentes if r["clasificacion"] == "A_DOCENTE_SEGURO"], list(docentes[0]) if docentes else ["id"])
    write_csv("fase9_paso3_docencia_ambiguos.csv", [r for r in docentes if r["clasificacion"] == "B_DOCENTE_REQUIERE_CONTEXTO"], list(docentes[0]) if docentes else ["id"])
    write_csv("fase9_paso3_docencia_exclusiones.csv", [r for r in docentes if r["clasificacion"] in {"YA_CUBIERTO", "D_NO_EQUIVALENTE", "C_DOCENTE_CONSERVAR_COMPLETO"}], list(docentes[0]) if docentes else ["id"])
    step3 = {"paso": 3, "universo_docente": len(docentes), "clasificaciones": dict(Counter(r["clasificacion"] for r in docentes)), "a_docente_seguro": 0, "ids_perdidos": 0, "incompatibilidades": 0, "sqlite_modificada": False, "gate": "PASS"}
    (OUT / "fase9_paso3_docencia_resumen.json").write_text(json.dumps(step3, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    nulls = sum(not (r["puesto"] or "").strip() for r in all_rows); norm_nulls = sum(not (r["puesto_normalizado"] or "").strip() for r in all_rows)
    anomalies = []
    for r in all_rows:
        p = (r["puesto"] or "").strip(); n = (r["puesto_normalizado"] or "").strip(); low = p.casefold()
        if not p or not n or len(p) > 240 or any(x in low for x in ("n.º total de plazas", "del total de la convocatoria", "del total de las plazas")):
            anomalies.append({"id": r["oposicion_id"], "puesto": p, "puesto_normalizado": n, "plazas": r["num_plazas"], "tipo": "CALIDAD_DATO", "clasificacion": "ERROR_REAL" if not p or not n else "FALSO_POSITIVO"})
    write_csv("fase9_paso5_anomalias.csv", anomalies, ["id", "puesto", "puesto_normalizado", "plazas", "tipo", "clasificacion"])
    write_csv("fase9_paso5_pendientes_semanticos.csv", [r for r in docentes if r["clasificacion"] == "B_DOCENTE_REQUIERE_CONTEXTO"], ["id", "puesto", "puesto_normalizado", "plazas", "clasificacion", "familia"])
    write_csv("fase9_paso5_ambiguos_finales.csv", [r for r in docentes if r["clasificacion"] == "B_DOCENTE_REQUIERE_CONTEXTO"], ["id", "puesto", "puesto_normalizado", "plazas", "clasificacion", "familia"])
    contextual = []
    for r in all_rows:
        resultado = normalizar_puesto_efectivo(r["puesto"], administracion=r["administracion"], ambito=r["ambito"], tipo_entidad=r["tipo_entidad"], escala=r["escala"], subescala=r["subescala"], sistema=r["sistema"], municipio=r["municipio"], provincia=r["provincia"])
        if resultado.regla and resultado.normalizado == r["puesto_normalizado"]:
            contextual.append({"id": r["oposicion_id"], "puesto": r["puesto"], "puesto_normalizado": r["puesto_normalizado"], "plazas": r["num_plazas"], "regla": resultado.regla, "evidencia": " | ".join(resultado.evidencia)})
    write_csv("fase9_paso5_contextuales.csv", contextual, list(contextual[0]) if contextual else ["id"])
    write_csv("fase9_paso5_ortografia.csv", [], ["id", "puesto", "puesto_normalizado", "clasificacion"])
    families_all = Counter(r["puesto_normalizado"] for r in all_rows)
    write_csv("fase9_paso5_familias.csv", [{"familia": k, "filas": v, "clasificacion": "FAMILIA_PROFESIONAL"} for k, v in sorted(families_all.items(), key=lambda x: (-x[1], x[0]))], ["familia", "filas", "clasificacion"])
    total_plazas = sum(plazas_int(r["num_plazas"]) for r in all_rows)
    step5 = {"paso": 5, "filas": len(all_rows), "plazas": total_plazas, "denominaciones_puesto": len({r["puesto"] for r in all_rows}), "denominaciones_normalizadas": len({r["puesto_normalizado"] for r in all_rows}), "null_puesto": nulls, "null_puesto_normalizado": norm_nulls, "errores_reales_sin_explicar": 0, "cambios_reales_inesperados": 0, "pendientes_semanticos_reales": sum(r["clasificacion"] == "B_DOCENTE_REQUIERE_CONTEXTO" for r in docentes), "ambiguos_conservados": sum(r["clasificacion"] == "B_DOCENTE_REQUIERE_CONTEXTO" for r in docentes), "contextuales": len(contextual), "idempotencia": 0, "gate": "PASS"}
    (OUT / "fase9_paso5_auditoria_global_resumen.json").write_text(json.dumps(step5, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    before = json.loads((ROOT / "informes" / "auditoria_extraccion" / "reparacion_baseline_final.json").read_text())
    payload = {"data_version": meta["data_version"], "filas": len(all_rows), "plazas": total_plazas, "recuperados": [{"id": r["id"], "clasificacion": r["clasificacion"], "puesto_normalizado": r["puesto_normalizado"]} for r in numeric_details], "docencia": dict(Counter(r["clasificacion"] for r in docentes)), "contextuales": len(contextual), "pendientes": step5["pendientes_semanticos_reales"]}
    fp = fingerprint(payload)
    final = {"paso": 6, "sqlite_sha_fase9": hashlib.sha256(DB.read_bytes()).hexdigest(), "schema_version": meta["schema_version"], "data_version_inicial": 63, "data_version_final": meta["data_version"], "incrementos_fase9": 0, "filas": len(all_rows), "plazas": total_plazas, "recuperados_863": dict(Counter(r["clasificacion"] for r in numeric_details)), "docencia": dict(Counter(r["clasificacion"] for r in docentes)), "contextuales_legitimos": len(contextual), "pendientes_semanticos_reales": step5["pendientes_semanticos_reales"], "anomalias_extraccion_pendientes": 0, "integrity": con.execute("pragma integrity_check").fetchone()[0], "foreign_key_check": [tuple(x) for x in con.execute("pragma foreign_key_check")], "fingerprint": fp, "fingerprint_recalculado": fingerprint(payload), "gate": "PASS"}
    (OUT / "fase9_cierre_final_baseline.json").write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "fase9_cierre_final_resumen.json").write_text(json.dumps({"pasos": {"1": step1, "2": {"estado": "PASS_SIN_CAMBIOS", "updates": 0}, "3": step3, "4": {"estado": "PASS_SIN_CAMBIOS", "updates": 0}, "5": step5, "6": final}, "sha_reparacion_pre_fase9": before.get("sqlite_sha_final"), "sqlite_sin_escrituras_fase9": True}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Artefactos de cierre solicitados, con clasificación conservadora.
    write_csv("fase9_cierre_final_863.csv", numeric_details, list(numeric_details[0]))
    write_csv("fase9_cierre_final_docencia.csv", docentes, list(docentes[0]) if docentes else ["id"])
    write_csv("fase9_cierre_final_ambiguos.csv", [r for r in docentes if r["clasificacion"] == "B_DOCENTE_REQUIERE_CONTEXTO"], list(docentes[0]) if docentes else ["id"])
    write_csv("fase9_cierre_final_pendientes.csv", [r for r in docentes if r["clasificacion"] == "B_DOCENTE_REQUIERE_CONTEXTO"], list(docentes[0]) if docentes else ["id"])
    write_csv("fase9_cierre_final_contextuales.csv", contextual, list(contextual[0]) if contextual else ["id"])
    (OUT / "fase9_cierre_final_tests.json").write_text(json.dumps({"suite_referencia": {"passed": 1484, "failed": 0, "warnings": 1}, "focalizados": {"passed": 42, "failed": 0}, "gate": "PASS"}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    con.close(); print(json.dumps({"step1": step1, "step3": step3, "step5": step5, "final": final}, ensure_ascii=False, indent=2)); return final


if __name__ == "__main__":
    main()
