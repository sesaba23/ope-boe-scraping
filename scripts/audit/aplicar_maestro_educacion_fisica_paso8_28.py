"""Aplica la única fila pendiente de Maestro de Educación Física (FASE 8/PASO 28)."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import csv
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import base_datos

DB = ROOT / "datos/boe.db"
BACKUPS = ROOT / "backups/sqlite"
INFORMES = ROOT / "informes/normalizacion_puestos"
IDS = (11067, 99076)
CANON = "Maestro de Educación Física"
NOOP_ID = 11067
PENDIENTE_ID = 99076


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def estado(path=DB):
    path = Path(path)
    stat = path.stat()
    con = base_datos.conectar(path, readonly=True)
    try:
        meta = base_datos.leer_metadata(con)
        tablas = {x[0] for x in con.execute("select name from sqlite_master where type='table'")}
        contar = lambda t: con.execute(f"select count(*) from [{t}]").fetchone()[0] if t in tablas else None
        return {"sha256": sha(path), "tamano": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                "schema_version": meta.get("schema_version"), "data_version": meta.get("data_version"),
                "oposiciones": contar("oposiciones"),
                "plazas": con.execute("select coalesce(sum(num_plazas),0) from oposiciones").fetchone()[0],
                "publicaciones": contar("publicaciones"), "busquedas": contar("busquedas"),
                "cobertura": contar("cobertura"), "integrity_check": con.execute("pragma integrity_check").fetchone()[0],
                "foreign_key_check": [list(x) for x in con.execute("pragma foreign_key_check")],
                "wal_existe": path.with_name(path.name + "-wal").exists(),
                "shm_existe": path.with_name(path.name + "-shm").exists()}
    finally:
        con.close()


def filas_objetivo(con):
    filas = {}
    for oid in IDS:
        fila = con.execute("select oposicion_id, puesto, puesto_normalizado, num_plazas from oposiciones where oposicion_id=?", (oid,)).fetchone()
        if fila is None:
            raise RuntimeError(f"Falta el ID validado {oid}")
        filas[oid] = tuple(fila)
    return filas


def validar_precondiciones(filas):
    if filas[NOOP_ID][1:] != (CANON, CANON, 4):
        raise RuntimeError(f"La fila no-op {NOOP_ID} no coincide: {filas[NOOP_ID]!r}")
    if filas[PENDIENTE_ID][1:] != ("Maestro/a de Educación Física", "Maestro/a de Educación Física", 2):
        raise RuntimeError(f"La fila pendiente {PENDIENTE_ID} no coincide: {filas[PENDIENTE_ID]!r}")


def aplicar(ruta_bd=DB, directorio_backup=BACKUPS):
    ruta_bd = Path(ruta_bd).resolve()
    before = estado(ruta_bd)
    if before["integrity_check"] != "ok" or before["foreign_key_check"] or before["wal_existe"] or before["shm_existe"]:
        raise RuntimeError("La base no supera el precheck de integridad/WAL/SHM")
    lectura = base_datos.conectar(ruta_bd, readonly=True)
    try:
        filas_antes = filas_objetivo(lectura)
        if (filas_antes[NOOP_ID][1:] == (CANON, CANON, 4)
                and filas_antes[PENDIENTE_ID][2:] == (CANON, 2)):
            return {"before": before, "after": before, "filas_antes": {str(k): list(v) for k, v in filas_antes.items()},
                    "cambios": [], "rowcount": 0, "plazas": 0, "data_version_before": before["data_version"],
                    "data_version_after": before["data_version"], "aplicada": False,
                    "generado_utc": datetime.now(timezone.utc).isoformat()}
        validar_precondiciones(filas_antes)
        version_antes = int(before["data_version"])
        if version_antes != 48:
            raise RuntimeError(f"data_version inesperada: {version_antes}")
    finally:
        lectura.close()
    backup = base_datos.crear_backup(ruta_bd, directorio_backup)
    backup = Path(backup)
    backup_state = estado(backup)
    if any(backup_state[k] != before[k] for k in ("schema_version", "data_version", "oposiciones", "plazas", "publicaciones", "busquedas", "cobertura")):
        raise RuntimeError("El backup no representa exactamente el estado pre-aplicación")
    backup_con = base_datos.conectar(backup, readonly=True)
    try:
        if filas_objetivo(backup_con) != filas_antes:
            raise RuntimeError("Las filas objetivo del backup no coinciden")
    finally:
        backup_con.close()
    conexion = base_datos.conectar(ruta_bd)
    try:
        with base_datos.transaccion(conexion):
            if base_datos.leer_metadata(conexion).get("data_version") != str(version_antes):
                raise RuntimeError("data_version cambió entre precheck y transacción")
            filas_tx = filas_objetivo(conexion)
            validar_precondiciones(filas_tx)
            resultado = conexion.execute(
                "UPDATE oposiciones SET puesto_normalizado=? WHERE oposicion_id=? AND puesto=? AND puesto_normalizado=?",
                (CANON, PENDIENTE_ID, "Maestro/a de Educación Física", "Maestro/a de Educación Física"),
            )
            if resultado.rowcount != 1:
                raise RuntimeError(f"Rowcount inesperado: {resultado.rowcount}")
            base_datos.guardar_metadata(conexion, data_version=version_antes + 1)
            if base_datos.integrity_check(conexion) != ["ok"] or base_datos.foreign_key_check(conexion):
                raise RuntimeError("La base no supera las validaciones internas")
    finally:
        conexion.close()
    after = estado(ruta_bd)
    return {"before": before, "backup": {"ruta": str(backup), **backup_state}, "after": after,
            "filas_antes": {str(k): list(v) for k, v in filas_antes.items()},
            "cambios": [{"oposicion_id": PENDIENTE_ID, "anterior": "Maestro/a de Educación Física", "nuevo": CANON, "plazas": 2}],
            "rowcount": 1, "plazas": 2, "data_version_before": str(version_antes),
            "data_version_after": after["data_version"], "aplicada": True,
            "generado_utc": datetime.now(timezone.utc).isoformat()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bd", type=Path, default=DB)
    parser.add_argument("--directorio-backup", type=Path, default=BACKUPS)
    args = parser.parse_args()
    informe = aplicar(args.bd, args.directorio_backup)
    INFORMES.mkdir(parents=True, exist_ok=True)
    (INFORMES / "fase8_paso28_aplicacion_maestro_educacion_fisica.json").write_text(
        json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (INFORMES / "fase8_paso28_aplicacion_maestro_educacion_fisica_detalle.csv").open("w", newline="", encoding="utf-8") as salida:
        writer = csv.DictWriter(salida, fieldnames=["oposicion_id", "anterior", "nuevo", "plazas"])
        writer.writeheader()
        writer.writerows(informe["cambios"])
    print(json.dumps(informe, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
