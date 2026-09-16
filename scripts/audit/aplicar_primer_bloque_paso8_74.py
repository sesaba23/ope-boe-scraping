"""PASO 74: aplica exclusivamente el plan aprobado en PASO 73."""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit.auditar_bomberos_paso8_40 import state
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate_auditar

DB = ROOT / "datos" / "boe.db"
INF = ROOT / "informes" / "normalizacion_puestos"
BACKUPS = ROOT / "backups" / "sqlite"
P73 = INF / "fase8_paso73_reglas_primer_bloque.json"
OUT = INF / "fase8_paso74_aplicacion.json"
DETAIL = INF / "fase8_paso74_detalle.csv"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_backup(path: Path) -> None:
    con = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        if con.execute("pragma integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("backup integrity_check distinto de ok")
        if list(con.execute("pragma foreign_key_check")):
            raise RuntimeError("backup foreign_key_check no vacío")
    finally:
        con.close()


def _plan() -> list[dict]:
    report = json.loads(P73.read_text(encoding="utf-8"))
    ids = set(report["plan_aprobado"])
    con = sqlite3.connect(f"file:{DB.resolve()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = []
        for r in con.execute(
            "select oposicion_id, puesto, puesto_normalizado, num_plazas from oposiciones where oposicion_id in (%s)"
            % ",".join("?" for _ in ids), sorted(ids)
        ):
            d = dict(r); d["id"] = int(d.pop("oposicion_id")); d["puesto_normalizado_anterior"] = d.pop("puesto_normalizado")
            d["puesto_normalizado_nuevo"] = "Oficial"
            if d["puesto_normalizado_anterior"] != d["puesto_normalizado_nuevo"]:
                rows.append(d)
        return sorted(rows, key=lambda x: x["id"])
    finally:
        con.close()


def main() -> None:
    pre = json.loads(P73.read_text(encoding="utf-8"))
    before = state()
    if before["sha256"] != pre["sqlite_precheck"]["sha256"] or before["data_version"] != pre["sqlite_precheck"]["data_version"]:
        raise RuntimeError("SQLite cambió desde PASO 73")
    if before["integrity_check"] != "ok" or before["foreign_key_check"]:
        raise RuntimeError("SQLite no supera integridad/FK")
    plan = _plan()
    if [x["id"] for x in plan] != pre["plan_aprobado"]:
        raise RuntimeError("plan físico no coincide con PASO 73")
    if any(x["puesto_normalizado_nuevo"] != "Oficial" for x in plan):
        raise RuntimeError("canon nuevo inesperado")

    BACKUPS.mkdir(parents=True, exist_ok=True)
    backup = BACKUPS / f"boe_paso74_primer_bloque_fase8_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}.db"
    shutil.copy2(DB, backup)
    if sha(backup) != before["sha256"]:
        raise RuntimeError("SHA del backup no coincide con SQLite previa")
    _verify_backup(backup)

    con = sqlite3.connect(DB)
    mutaciones = 0
    try:
        con.execute("BEGIN IMMEDIATE")
        for item in plan:
            mutaciones += con.execute(
                "update oposiciones set puesto_normalizado=? where oposicion_id=? and puesto_normalizado=?",
                (item["puesto_normalizado_nuevo"], item["id"], item["puesto_normalizado_anterior"]),
            ).rowcount
        if mutaciones != len(plan):
            con.rollback(); raise RuntimeError("rowcount distinto del plan; rollback")
        if con.execute("pragma integrity_check").fetchone()[0] != "ok" or list(con.execute("pragma foreign_key_check")):
            con.rollback(); raise RuntimeError("integridad pre-commit fallida; rollback")
        con.execute("update metadata set valor=? where clave='data_version'", (str(int(before["data_version"]) + 1),))
        con.commit()
    finally:
        con.close()

    after = state()
    if after["data_version"] != str(int(before["data_version"]) + 1):
        raise RuntimeError("data_version no incrementó exactamente una vez")
    # Idempotencia física: el mismo plan no vuelve a encontrar filas pendientes.
    second = _plan()
    if second:
        raise RuntimeError("segunda ejecución no idempotente")
    gate = gate_auditar(DB)
    if (gate["cambios_reales_recalculables"]["filas"], gate["discrepancias_contextuales_no_recalculables"]["filas"], gate["discrepancias_no_clasificables_automaticamente"]["filas"]) != (0, 329, 0):
        raise RuntimeError("gate PASO 19 post-aplicación inesperado")
    if after["integrity_check"] != "ok" or after["foreign_key_check"] or after["wal_existe"] or after["shm_existe"]:
        raise RuntimeError("integridad o ficheros auxiliares post-aplicación inesperados")
    con = sqlite3.connect(f"file:{DB.resolve()}?mode=ro", uri=True); con.row_factory = sqlite3.Row
    try:
        id30709 = con.execute("select puesto_normalizado from oposiciones where oposicion_id=30709").fetchone()[0]
    finally: con.close()
    if id30709 != "Policía Local":
        raise RuntimeError("ID 30709 alterado")

    # El detalle es deliberadamente explícito para permitir reconciliación por ID.
    import csv
    with DETAIL.open("w", newline="", encoding="utf-8") as fh:
        fields = ["id", "puesto", "puesto_normalizado_anterior", "puesto_normalizado_nuevo", "num_plazas"]
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(plan)
    result = {
        "version": "fase8-paso74-v1", "generado_utc": datetime.now(timezone.utc).isoformat(),
        "primera_ejecucion": {"antes": before, "backup": {"ruta": str(backup), "sha256": sha(backup), "tamano": backup.stat().st_size, "integrity_check": "ok", "foreign_key_check": []},
                               "plan": plan, "mutaciones": mutaciones, "plazas_mutadas": sum(float(x["num_plazas"] or 0) for x in plan), "despues": after},
        "segunda_ejecucion": {"mutaciones": 0, "data_version": after["data_version"]},
        "gate_final": {k: {"filas": gate[k]["filas"], "plazas": gate[k]["plazas"]} for k in ("cambios_reales_recalculables", "discrepancias_contextuales_no_recalculables", "discrepancias_no_clasificables_automaticamente")},
        "id_30709": id30709, "sqlite_sha256_despues": after["sha256"],
        "git_diff_check": subprocess.run(["git", "diff", "--check"], cwd=ROOT).returncode == 0, "estado": "PASS",
    }
    if not result["git_diff_check"]:
        raise RuntimeError("git diff --check falló")
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"estado": "PASS", "mutaciones": mutaciones, "plazas": result["primera_ejecucion"]["plazas_mutadas"], "data_version": f"{before['data_version']}->{after['data_version']}", "gate": result["gate_final"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
