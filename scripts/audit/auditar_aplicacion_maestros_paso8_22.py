"""Audita, en modo sólo lectura, la aplicación de los cuatro cambios A."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from normalizacion_puestos import normalizar_puesto
from scripts.audit import aplicar_maestros_paso8_22 as aplicador
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as auditar_global

DB = aplicador.DB
OUT = ROOT / "informes/normalizacion_puestos/fase8_paso22_aplicacion_maestros.json"
CSV_OUT = ROOT / "informes/normalizacion_puestos/fase8_paso22_aplicacion_maestros_detalle.csv"


def filas(ruta):
    con = sqlite3.connect(f"file:{Path(ruta).resolve()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return {row["oposicion_id"]: dict(row) for row in con.execute(
            "SELECT oposicion_id, puesto, puesto_normalizado, num_plazas FROM oposiciones "
            "WHERE oposicion_id IN (76794,91232,96837,17263)"
        )}
    finally:
        con.close()


def auditar(ruta_bd=DB, ruta_backup=None):
    ruta_bd = Path(ruta_bd)
    actual = aplicador.estado(ruta_bd)
    backup = aplicador.estado(ruta_backup) if ruta_backup else None
    actuales = filas(ruta_bd)
    antes = filas(ruta_backup) if ruta_backup else {}
    detalles = []
    for oid in aplicador.IDS:
        row = actuales[oid]
        expected = aplicador.PLAN[oid][1]
        detalles.append({
            "oposicion_id": oid, "puesto": row["puesto"],
            "canon_antes": antes.get(oid, {}).get("puesto_normalizado"),
            "canon_despues": row["puesto_normalizado"], "canon_esperado": expected,
            "plazas": row["num_plazas"], "normalizador_actual": normalizar_puesto(row["puesto"]),
            "aplicado": row["puesto_normalizado"] == expected,
        })
    especifico_pendiente = [d["oposicion_id"] for d in detalles if not d["aplicado"]]
    global_post = auditar_global(ruta_bd)
    if ruta_backup:
        if backup["sha256"] != aplicador.sha(ruta_backup):
            raise RuntimeError("Hash de backup inconsistente")
        if actual["schema_version"] != backup["schema_version"]:
            raise RuntimeError("schema_version cambió")
        if actual["data_version"] != str(int(backup["data_version"]) + 1):
            raise RuntimeError("data_version no incrementada exactamente una vez")
        for oid in aplicador.IDS:
            if antes[oid]["puesto"] != actuales[oid]["puesto"]:
                raise RuntimeError(f"Se modificó puesto para {oid}")
            if antes[oid]["num_plazas"] != actuales[oid]["num_plazas"]:
                raise RuntimeError(f"Se modificaron plazas para {oid}")
    informe = {
        "version": "fase8-paso22-v1", "generado_utc": datetime.now(timezone.utc).isoformat(),
        "modo": "read-only", "sqlite_final": actual, "backup_preaplicacion": backup,
        "backup_verificado": bool(backup and backup["integrity_check"] == "ok" and not backup["foreign_key_check"]),
        "contrato": {"ids": list(aplicador.IDS), "rowcount": 4, "plazas": 746,
                     "data_version": "47 -> 48", "cambios_fuera_de_puesto_normalizado": ["metadata.updated_at"]},
        "aplicacion": {"rowcount": sum(d["aplicado"] for d in detalles),
                       "plazas": sum(float(d["plazas"] or 0) for d in detalles if d["aplicado"]),
                       "dry_run_especifico_pendiente": especifico_pendiente, "detalles": detalles},
        "puerta_global_post": {
            "total_discrepancias": global_post["total_discrepancias"],
            "total_plazas_discrepantes": global_post["total_plazas_discrepantes"],
            "cambios_reales_recalculables": global_post["cambios_reales_recalculables"]["filas"],
            "discrepancias_contextuales_no_recalculables": global_post["discrepancias_contextuales_no_recalculables"]["filas"],
            "discrepancias_no_clasificables_automaticamente": global_post["discrepancias_no_clasificables_automaticamente"]["filas"],
        },
        "sin_duplicados": len(set(aplicador.IDS)) == 4,
    }
    return informe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bd", type=Path, default=DB)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--salida", type=Path, default=OUT)
    parser.add_argument("--csv", type=Path, default=CSV_OUT)
    args = parser.parse_args()
    informe = auditar(args.bd, args.backup)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with args.csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(informe["aplicacion"]["detalles"][0]))
        writer.writeheader(); writer.writerows(informe["aplicacion"]["detalles"])
    print(json.dumps(informe["puerta_global_post"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
