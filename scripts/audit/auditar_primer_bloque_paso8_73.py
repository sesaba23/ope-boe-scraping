"""PASO 73: valida el primer bloque de PASO 72 sin tocar SQLite."""
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

from normalizacion_puestos import normalizar_puesto
from scripts.audit.auditar_bomberos_paso8_40 import state
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate_auditar

DB = ROOT / "datos" / "boe.db"
INF = ROOT / "informes" / "normalizacion_puestos"
P72 = INF / "fase8_paso72_auditoria.json"
P72B = INF / "fase8_paso72b_analisis_bcd.json"
P72C = INF / "fase8_paso72c_variantes_formales.json"
OUT = INF / "fase8_paso73_reglas_primer_bloque.json"
DETAIL = INF / "fase8_paso73_detalle.csv"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(ids: set[int]) -> dict[int, sqlite3.Row]:
    con = sqlite3.connect(f"file:{DB.resolve()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        marks = ",".join("?" for _ in ids)
        return {int(r["oposicion_id"]): r for r in con.execute(
            f"select oposicion_id, puesto, puesto_normalizado, num_plazas from oposiciones where oposicion_id in ({marks})",
            sorted(ids),
        )}
    finally:
        con.close()


def main() -> None:
    before = state()
    if before["integrity_check"] != "ok" or before["foreign_key_check"]:
        raise RuntimeError("SQLite no supera integridad/FK")
    p72, p72b, p72c = (json.loads(p.read_text(encoding="utf-8")) for p in (P72, P72B, P72C))
    expected_fp = "476e8c46b01d7bb6564a23a88db5423f53e4192eeafa6ece243bd8956fdc328b"
    if p72c["fingerprint"] != expected_fp:
        raise RuntimeError("fingerprint PASO 72-C inesperado")
    recomputed = hashlib.sha256(json.dumps(
        [(x["id"], x["resultado_72c"]) for x in p72c["detalle"]], separators=(",", ":")
    ).encode()).hexdigest()
    if recomputed != expected_fp:
        raise RuntimeError("fingerprint PASO 72-C no reproducible")

    a_originales = [x for x in p72["filas"] if x["clasificacion"] == "A"]
    canon_por_familia = {x["familia"]: x["canon_propuesto"] for x in p72["conjuntos_A"]}
    a_ids = {int(x["id"]) for x in a_originales}
    a_nuevo = [x for x in p72c["detalle"] if x["resultado_72c"] == "A_SEGURO"]
    nuevo_ids = {int(x["id"]) for x in a_nuevo}
    rows = _rows(a_ids | nuevo_ids)
    detalle = []
    for x in a_originales:
        rid = int(x["id"]); row = rows[rid]; actual = normalizar_puesto(row["puesto"])
        canon = canon_por_familia[x["familia"]]
        if actual != canon:
            raise RuntimeError(f"A original {rid} no produce canon aprobado: {actual!r} != {canon!r}")
        detalle.append({"id": rid, "universo": "A_ORIGINAL", "familia": x["familia"], "puesto": row["puesto"],
                        "canon_aprobado": canon, "persistido": row["puesto_normalizado"], "recalculado": actual,
                        "estado": "IMPLEMENTADO" if actual != row["puesto_normalizado"] else "YA_CUBIERTO"})
    for x in a_nuevo:
        rid = int(x["id"]); row = rows[rid]; actual = normalizar_puesto(row["puesto"])
        if actual != x["canon_propuesto"]:
            raise RuntimeError(f"A_NUEVO {rid} altera el canon completo: {actual!r} != {x['canon_propuesto']!r}")
        detalle.append({"id": rid, "universo": "A_NUEVO", "familia": x["familia"], "puesto": row["puesto"],
                        "canon_aprobado": x["canon_propuesto"],
                        "persistido": row["puesto_normalizado"], "recalculado": actual,
                        "estado": "YA_CUBIERTO_ORTOGRAFIA_O_REGLA_PREVIA"})

    gate = gate_auditar(DB)
    gate_ids = set(gate["cambios_reales_recalculables"]["ids"])
    approved_ids = {x["id"] for x in detalle if x["estado"] == "IMPLEMENTADO"}
    inesperados = sorted(gate_ids - approved_ids)
    ausentes = sorted(approved_ids - gate_ids)
    if inesperados or ausentes:
        raise RuntimeError(f"gate global no coincide: inesperados={inesperados}, ausentes={ausentes}")
    if gate["discrepancias_contextuales_no_recalculables"]["filas"] != 329 or gate["discrepancias_no_clasificables_automaticamente"]["filas"] != 0:
        raise RuntimeError("gate contextual/no clasificable inesperado")

    # Los universos excluidos no deben recibir ningún cambio nuevo.
    excluidos = {int(x["id"]) for x in p72c["detalle"] if x["resultado_72c"] == "NO_A_AMBIGUO"}
    if gate_ids & excluidos:
        raise RuntimeError("NO_A_AMBIGUO afectado por una regla nueva")
    if before != state():
        raise RuntimeError("PASO 73 modificó SQLite")

    INF.mkdir(parents=True, exist_ok=True)
    with DETAIL.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(detalle[0]))
        writer.writeheader(); writer.writerows(sorted(detalle, key=lambda x: x["id"]))
    report = {
        "version": "fase8-paso73-v1", "modo": "normalizador_sin_sqlite",
        "generado_utc": datetime.now(timezone.utc).isoformat(),
        "git": {"branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
                "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "status_short": subprocess.check_output(["git", "status", "--short"], cwd=ROOT, text=True).splitlines()},
        "sqlite_precheck": before, "normalizador_sha256": sha(ROOT / "normalizacion_puestos.py"),
        "artefactos": {"paso72": {"A": len(a_originales), "filas": len(p72["filas"])},
                       "paso72b": p72b["totales_originales"], "paso72c": p72c["universo"],
                       "paso72c_fingerprint": expected_fp},
        "A_originales": {"filas": len(a_originales), "plazas": sum(float(x["plazas"] or 0) for x in a_originales)},
        "A_nuevo": {"filas": len(a_nuevo), "plazas": sum(float(x["plazas"] or 0) for x in a_nuevo),
                    "conjuntos": len(p72c["A_NUEVO"]), "clasificacion": "ya cubiertos; no se crea regla redundante"},
        "plan_aprobado": sorted(approved_ids), "filas_update": len(approved_ids),
        "plazas_update": sum(float(rows[i]["num_plazas"] or 0) for i in approved_ids),
        "detalle": detalle,
        "gate_paso19": {k: {"filas": gate[k]["filas"], "plazas": gate[k]["plazas"]} for k in (
            "cambios_reales_recalculables", "discrepancias_contextuales_no_recalculables", "discrepancias_no_clasificables_automaticamente")},
        "inesperados": inesperados, "ausentes": ausentes,
        "negativos": {"NO_A_AMBIGUO_afectados": 0, "C_afectados": 0, "D_afectados": 0},
        "id_30709": {"puesto_normalizado": _rows({30709})[30709]["puesto_normalizado"]},
        "sqlite_modificada": False, "git_diff_check": subprocess.run(["git", "diff", "--check"], cwd=ROOT).returncode == 0,
        "estado": "PASS",
    }
    if report["id_30709"]["puesto_normalizado"] != "Policía Local" or not report["git_diff_check"]:
        raise RuntimeError("regresión ID 30709 o git diff --check")
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"estado": "PASS", "filas_update": len(approved_ids), "plazas_update": report["plazas_update"], "gate": report["gate_paso19"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
