"""Aplicación transaccional e idempotente de la corrección de Fotocomposición."""
from __future__ import annotations
import argparse, csv, hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import base_datos
from normalizacion_puestos import normalizar_puesto

DB = ROOT / "datos/boe.db"
BACKUPS = ROOT / "backups/sqlite"
INFORMES = ROOT / "informes/normalizacion_puestos"
OLD = "Profesor de Música - Composición"

def estado(path):
    path = Path(path); stat = path.stat(); con = base_datos.conectar(path, readonly=True)
    try:
        meta = base_datos.leer_metadata(con)
        return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "tamano": stat.st_size, "mtime_ns": stat.st_mtime_ns, "schema_version": meta.get("schema_version"), "data_version": meta.get("data_version"), "oposiciones": con.execute("select count(*) from oposiciones").fetchone()[0], "plazas": con.execute("select coalesce(sum(num_plazas),0) from oposiciones").fetchone()[0], "publicaciones": con.execute("select count(*) from publicaciones").fetchone()[0], "busquedas": con.execute("select count(*) from busquedas").fetchone()[0], "cobertura": con.execute("select count(*) from cobertura").fetchone()[0], "integrity_check": con.execute("pragma integrity_check").fetchone()[0], "foreign_key_check": [list(x) for x in con.execute("pragma foreign_key_check")]}
    finally:
        con.close()

def plan(con):
    filas = con.execute("select oposicion_id,puesto,puesto_normalizado,num_plazas from oposiciones where lower(puesto) like '%fotocompos%'").fetchall()
    return [tuple(fila) for fila in filas if fila[2] == OLD and normalizar_puesto(fila[1]) != fila[2]]

def aplicar(ruta=DB, directorio_backup=BACKUPS):
    before = estado(ruta); con = base_datos.conectar(ruta, readonly=True)
    try:
        cambios = plan(con); version = int(base_datos.leer_metadata(con)["data_version"])
    finally:
        con.close()
    if not cambios:
        return {"aplicada": False, "rowcount": 0, "plazas": 0, "before": before, "after": before, "data_version_before": before["data_version"], "data_version_after": before["data_version"]}
    backup = Path(base_datos.crear_backup(ruta, directorio_backup)); backup_state = estado(backup)
    for clave in ("schema_version", "data_version", "oposiciones", "plazas", "publicaciones", "busquedas", "cobertura"):
        if backup_state[clave] != before[clave]: raise RuntimeError("backup inconsistente")
    con = base_datos.conectar(ruta)
    try:
        with base_datos.transaccion(con):
            if base_datos.leer_metadata(con).get("data_version") != str(version): raise RuntimeError("data_version cambió")
            for oid, puesto, previo, _ in cambios:
                resultado = con.execute("update oposiciones set puesto_normalizado=? where oposicion_id=? and puesto=? and puesto_normalizado=?", (puesto, oid, puesto, previo))
                if resultado.rowcount != 1: raise RuntimeError("rowcount inesperado")
            base_datos.guardar_metadata(con, data_version=version + 1)
            if base_datos.integrity_check(con) != ["ok"] or base_datos.foreign_key_check(con): raise RuntimeError("integridad fallida")
    finally:
        con.close()
    after = estado(ruta)
    detalle = [{"oposicion_id": x[0], "puesto": x[1], "anterior": x[2], "nuevo": x[1], "plazas": x[3]} for x in cambios]
    return {"aplicada": True, "rowcount": len(detalle), "plazas": sum(float(x["plazas"] or 0) for x in detalle), "before": before, "backup": {"ruta": str(backup), **backup_state}, "after": after, "cambios": detalle, "data_version_before": str(version), "data_version_after": after["data_version"], "generado_utc": datetime.now(timezone.utc).isoformat()}

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--bd", type=Path, default=DB); parser.add_argument("--directorio-backup", type=Path, default=BACKUPS); args = parser.parse_args()
    resultado = aplicar(args.bd, args.directorio_backup); INFORMES.mkdir(parents=True, exist_ok=True); (INFORMES / "fase8_paso31_aplicacion_fotocomposicion.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (INFORMES / "fase8_paso31_aplicacion_fotocomposicion_detalle.csv").open("w", newline="", encoding="utf-8") as salida:
        writer = csv.DictWriter(salida, fieldnames=["oposicion_id", "puesto", "anterior", "nuevo", "plazas"]); writer.writeheader(); writer.writerows(resultado.get("cambios", []))
    print(json.dumps(resultado, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
