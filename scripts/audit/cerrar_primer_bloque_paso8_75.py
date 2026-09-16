"""PASO 75: cierre reproducible del bloque de cinco familias."""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.audit.auditar_bomberos_paso8_40 import state
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate_auditar

INF = ROOT / "informes" / "normalizacion_puestos"
DB = ROOT / "datos" / "boe.db"
P72 = json.loads((INF / "fase8_paso72_auditoria.json").read_text(encoding="utf-8"))
P71 = json.loads((INF / "fase8_paso71_clasificacion_residual.json").read_text(encoding="utf-8"))
P72B = json.loads((INF / "fase8_paso72b_analisis_bcd.json").read_text(encoding="utf-8"))
P72C = json.loads((INF / "fase8_paso72c_variantes_formales.json").read_text(encoding="utf-8"))
P73 = json.loads((INF / "fase8_paso73_reglas_primer_bloque.json").read_text(encoding="utf-8"))
P74 = json.loads((INF / "fase8_paso74_aplicacion.json").read_text(encoding="utf-8"))
OUT = INF / "fase8_paso75_cierre_bloque.json"
RESIDUAL = INF / "fase8_paso75_residual_pendiente.json"
MASTER = INF / "fase8_paso75_clasificacion_residual.json"
TRACE = INF / "fase8_paso75_trazabilidad.csv"


def _sum(rows):
    def num(x):
        try:
            return float(x or 0)
        except (TypeError, ValueError):
            return 0.0
    return {"filas": len(rows), "plazas": sum(num(x.get("plazas", x.get("num_plazas", 0))) for x in rows)}


def _fingerprint(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> None:
    before = state()
    gate = gate_auditar(DB)
    if (gate["cambios_reales_recalculables"]["filas"], gate["discrepancias_contextuales_no_recalculables"]["filas"], gate["discrepancias_no_clasificables_automaticamente"]["filas"]) != (0, 329, 0):
        raise RuntimeError("gate final PASO 19 inesperado")
    con = sqlite3.connect(f"file:{DB.resolve()}?mode=ro", uri=True); con.row_factory = sqlite3.Row
    try:
        id30709 = con.execute("select puesto_normalizado from oposiciones where oposicion_id=30709").fetchone()[0]
    finally: con.close()
    if id30709 != "Policía Local" or before["integrity_check"] != "ok" or before["foreign_key_check"]:
        raise RuntimeError("ID 30709 o integridad final incorrectos")
    recalc_ids = set(gate["cambios_reales_recalculables"]["ids"])
    c_ids = {int(x["id"]) for x in P72["filas"] if x["clasificacion"] == "C"}
    d_ids = {int(x["id"]) for x in P72["filas"] if x["clasificacion"] == "D"}
    noamb_ids = {int(x["id"]) for x in P72C["detalle"] if x["resultado_72c"] == "NO_A_AMBIGUO"}
    audited_b_ids = {int(x["id"]) for x in P72C["detalle"]}
    b_ids = {int(x["id"]) for x in P72B["detalle"] if x["clasificacion"] == "B"}
    negative = {"NO_A_AMBIGUO": len(recalc_ids & noamb_ids), "B_no_auditado_72C": len(recalc_ids & (b_ids - audited_b_ids)), "C": len(recalc_ids & c_ids), "D": len(recalc_ids & d_ids)}
    if any(negative.values()):
        raise RuntimeError(f"universo negativo afectado: {negative}")

    a_orig = [x for x in P72["filas"] if x["clasificacion"] == "A"]
    a_new = [x for x in P72C["detalle"] if x["resultado_72c"] == "A_SEGURO"]
    implemented = P74["primera_ejecucion"]["plan"]
    a_summary = {
        "A_originales": _sum(a_orig),
        "A_NUEVO": {**_sum(a_new), "conjuntos": len(P72C["A_NUEVO"])},
        "A_ya_cubiertos": {"filas": len(a_orig) - len(implemented) + len(a_new), "plazas": sum(float(x["plazas"] or 0) for x in a_orig if int(x["id"]) not in {i["id"] for i in implemented}) + sum(float(x["plazas"] or 0) for x in a_new)},
        "A_implementados": {"filas": len(implemented), "plazas": sum(float(x["num_plazas"] or 0) for x in implemented)},
    }
    # B restante: se descuentan sólo los A_SEGURO identificados por PASO 72-C.
    a_new_ids = {int(x["id"]) for x in a_new}
    b_rows = [x for x in P72B["detalle"] if x["clasificacion"] == "B" and int(x["id"]) not in a_new_ids]
    by_sub = defaultdict(list)
    for x in b_rows: by_sub[x["subtipo"]].append(x)
    b_remaining = {k: _sum(v) for k, v in sorted(by_sub.items())}
    c_rows = [x for x in P72["filas"] if x["clasificacion"] == "C"]
    d_rows = [x for x in P72["filas"] if x["clasificacion"] == "D"]
    residual = {
        "version": "fase8-paso75-residual-v1", "origen": ["fase8_paso72b_analisis_bcd.json", "fase8_paso72c_variantes_formales.json"],
        "B_restante": {"total": _sum(b_rows), "NO_A_AMBIGUO_72C": _sum([x for x in P72C["detalle"] if x["resultado_72c"] == "NO_A_AMBIGUO"]), "no_auditado_72C": _sum([x for x in b_rows if int(x["id"]) not in {int(x["id"]) for x in P72C["detalle"]}]), "por_subtipo": b_remaining},
        "C_preservado": _sum(c_rows), "D_preservado": _sum(d_rows),
        "nota": "B, C y D no se normalizan en PASO 74; los subtipos conservan puestos compuestos, funciones, especialidades, niveles/categorías, mandos y ámbito/destino.",
    }
    families = {}
    for fam in ("TÉCNICO", "OFICIAL", "AUXILIAR", "AGENTE", "CUERPOS_ESCALAS"):
        s = next(x for x in P72["resumen"] if x["familia"] == fam)
        families[fam] = {"estado": "PARCIALMENTE_AUDITADA", "filas": s["filas"], "plazas": s["plazas"], "A": s["A"], "B": s["B"], "C": s["C"], "D": s["D"], "motivo": "el bloque A seguro quedó aplicado; B/D requieren auditorías posteriores y C se conserva"}

    stable = {"version": "fase8-paso75-v1", "familias": families, "A": a_summary, "B_restante": residual["B_restante"], "C": residual["C_preservado"], "D": residual["D_preservado"], "gate": {k: {"filas": gate[k]["filas"], "plazas": gate[k]["plazas"]} for k in ("cambios_reales_recalculables", "discrepancias_contextuales_no_recalculables", "discrepancias_no_clasificables_automaticamente")}, "negativos_afectados": negative, "OA_pendientes": 0, "id_30709": id30709, "data_version": before["data_version"], "integrity": before["integrity_check"], "foreign_key_check": before["foreign_key_check"]}
    fp1 = _fingerprint(stable); fp2 = _fingerprint(stable)
    if fp1 != fp2: raise RuntimeError("fingerprint no determinista")
    residual["fingerprint"] = _fingerprint({k: residual[k] for k in ("B_restante", "C_preservado", "D_preservado")})
    master = {"version": "fase8-paso75-clasificacion-residual-v1", "origen": "fase8_paso71_clasificacion_residual.json", "actualizacion": "delta reproducible PASO 72-75; no reclasifica familias restantes", "familias_actualizadas": families, "familias_restantes_pendientes": P71["conteos_por_estado"], "fingerprint": _fingerprint(families)}
    INF.mkdir(parents=True, exist_ok=True)
    RESIDUAL.write_text(json.dumps(residual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    MASTER.write_text(json.dumps(master, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    trace = [{"etapa": "PASO72", "universo": "cinco_familias", **_sum(P72["filas"])}, {"etapa": "PASO72C", "universo": "A_SEGURO", **_sum(a_new)}, {"etapa": "PASO74", "universo": "A_implementados", **a_summary["A_implementados"]}, {"etapa": "PASO75", "universo": "B_restante", **residual["B_restante"]["total"]}, {"etapa": "PASO75", "universo": "C_preservado", **residual["C_preservado"]}, {"etapa": "PASO75", "universo": "D_preservado", **residual["D_preservado"]}]
    with TRACE.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["etapa", "universo", "filas", "plazas"]); w.writeheader(); w.writerows(trace)
    report = {**stable, "generado_utc": datetime.now(timezone.utc).isoformat(), "trazabilidad": {"paso72": "fase8_paso72_auditoria.json", "paso72b": "fase8_paso72b_analisis_bcd.json", "paso72c": "fase8_paso72c_variantes_formales.json", "paso73": "fase8_paso73_reglas_primer_bloque.json", "paso74": "fase8_paso74_aplicacion.json"}, "backup": P74["primera_ejecucion"]["backup"], "fingerprint": fp1, "fingerprint_repetido": fp2, "sqlite_sha256": before["sha256"], "git_diff_check": subprocess.run(["git", "diff", "--check"], cwd=ROOT).returncode == 0, "estado_final": "CERRADO"}
    if not report["git_diff_check"]: raise RuntimeError("git diff --check falló")
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"estado": "CERRADO", "fingerprint": fp1, "B_restante": residual["B_restante"]["total"], "C": residual["C_preservado"], "D": residual["D_preservado"]}, ensure_ascii=False))


if __name__ == "__main__": main()
