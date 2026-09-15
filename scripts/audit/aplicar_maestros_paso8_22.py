"""Aplica, con una única transacción protegida, los cuatro cambios A validados."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import base_datos
from normalizacion_puestos import normalizar_puesto

DB = ROOT / "datos/boe.db"
BACKUPS = ROOT / "backups/sqlite"
IDS = (76794, 91232, 96837, 17263)
PLAN = {
    76794: ("Maestro/maestra en educación infantil", "Maestro de Educación Infantil"),
    91232: ("Maestro-a de Educación Infantil", "Maestro de Educación Infantil"),
    96837: ("Maestro o Maestra de Educación Infantil", "Maestro de Educación Infantil"),
    17263: ("funcionarios docentes para el Cuerpo de Maestros", "Maestros"),
}


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


def validar_plan(con):
    filas = {}
    for oid in IDS:
        fila = con.execute("select oposicion_id, puesto, puesto_normalizado, num_plazas from oposiciones where oposicion_id=?", (oid,)).fetchone()
        if fila is None:
            raise RuntimeError(f"Falta el ID validado {oid}")
        original, canon = PLAN[oid]
        if fila[1] != original:
            raise RuntimeError(f"El texto original cambió para {oid}")
        if fila[2] != original:
            raise RuntimeError(f"El canon anterior cambió para {oid}: {fila[2]!r}")
        if normalizar_puesto(fila[1]) != canon:
            raise RuntimeError(f"El normalizador no propone el canon esperado para {oid}")
        filas[oid] = tuple(fila)
    return filas


def aplicar(ruta_bd=DB, directorio_backup=BACKUPS):
    ruta_bd = Path(ruta_bd).resolve()
    before = estado(ruta_bd)
    if before["integrity_check"] != "ok" or before["foreign_key_check"] or before["wal_existe"] or before["shm_existe"]:
        raise RuntimeError("La base no supera el precheck de integridad/WAL/SHM")
    if before["data_version"] is None:
        raise RuntimeError("Falta data_version")
    lectura = base_datos.conectar(ruta_bd, readonly=True)
    try:
        filas_antes = validar_plan(lectura)
        version_antes = int(base_datos.leer_metadata(lectura)["data_version"])
    finally:
        lectura.close()
    if version_antes != 47:
        raise RuntimeError(f"data_version inesperada: {version_antes}")
    backup = base_datos.crear_backup(ruta_bd, directorio_backup)
    backup = Path(backup)
    backup_state = estado(backup)
    if (backup_state["integrity_check"] != "ok" or backup_state["foreign_key_check"]
            or any(backup_state[k] != before[k] for k in ("schema_version", "data_version", "oposiciones", "plazas", "publicaciones", "busquedas", "cobertura"))):
        raise RuntimeError("El backup no representa exactamente el estado pre-aplicación")
    backup_con = base_datos.conectar(backup, readonly=True)
    try:
        if validar_plan(backup_con) != filas_antes:
            raise RuntimeError("Las cuatro filas del backup no coinciden con el precheck")
    finally:
        backup_con.close()
    cambios = []
    conexion = base_datos.conectar(ruta_bd)
    try:
        with base_datos.transaccion(conexion):
            metadata_tx = base_datos.leer_metadata(conexion)
            if metadata_tx.get("schema_version") != before["schema_version"]:
                raise RuntimeError("schema_version cambió entre precheck y transacción")
            if metadata_tx.get("data_version") != str(version_antes):
                raise RuntimeError("data_version cambió entre precheck y transacción")
            validar_plan(conexion)
            for oid in IDS:
                original, canon = PLAN[oid]
                resultado = conexion.execute(
                    "UPDATE oposiciones SET puesto_normalizado=? WHERE oposicion_id=? AND puesto=? AND puesto_normalizado=?",
                    (canon, oid, original, original),
                )
                if resultado.rowcount != 1:
                    raise RuntimeError(f"Rowcount inesperado para {oid}: {resultado.rowcount}")
                cambios.append({"oposicion_id": oid, "puesto": original, "anterior": original,
                                "nuevo": canon, "plazas": filas_antes[oid][3]})
            if len(cambios) != 4 or sum(float(x["plazas"] or 0) for x in cambios) != 746:
                raise RuntimeError("El rowcount o las plazas no coinciden con el conjunto validado")
            base_datos.guardar_metadata(conexion, data_version=version_antes + 1)
            if base_datos.leer_metadata(conexion).get("schema_version") != before["schema_version"]:
                raise RuntimeError("schema_version modificada")
            if base_datos.leer_metadata(conexion).get("data_version") != str(version_antes + 1):
                raise RuntimeError("data_version no incrementada exactamente una vez")
            if base_datos.integrity_check(conexion) != ["ok"] or base_datos.foreign_key_check(conexion):
                raise RuntimeError("La base no supera las validaciones internas")
    finally:
        conexion.close()
    after = estado(ruta_bd)
    return {"before": before, "backup": {"ruta": str(backup), **backup_state},
            "after": after, "filas_antes": {str(k): list(v) for k, v in filas_antes.items()},
            "cambios": cambios, "rowcount": len(cambios), "plazas": sum(float(x["plazas"] or 0) for x in cambios),
            "data_version_before": str(version_antes), "data_version_after": after["data_version"],
            "aplicada": True, "generado_utc": datetime.now(timezone.utc).isoformat()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bd", type=Path, default=DB)
    parser.add_argument("--directorio-backup", type=Path, default=BACKUPS)
    args = parser.parse_args()
    print(json.dumps(aplicar(args.bd, args.directorio_backup), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
