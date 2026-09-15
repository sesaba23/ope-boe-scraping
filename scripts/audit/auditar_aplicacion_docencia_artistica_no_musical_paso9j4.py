"""Auditoría regenerable de la aplicación artística 9J-4."""

import hashlib
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "datos" / "boe.db"
SPEC = ROOT / "informes" / "normalizacion_puestos" / "fase7_docencia_artistica_no_musical_paso9j2.json"
DRY = ROOT / "informes" / "normalizacion_puestos" / "fase7_docencia_artistica_no_musical_paso9j3_dry_run.json"
OUT = ROOT / "informes" / "normalizacion_puestos" / "fase7_docencia_artistica_no_musical_paso9j4_aplicacion.json"


def estado(path):
    path = Path(path)
    with sqlite3.connect(path) as con:
        return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "tamano": path.stat().st_size, "mtime_ns": path.stat().st_mtime_ns, "versiones": dict(con.execute("select clave,valor from metadata where clave in ('schema_version','data_version')")), "oposiciones": con.execute("select count(*) from oposiciones").fetchone()[0], "plazas": con.execute("select coalesce(sum(num_plazas),0) from oposiciones").fetchone()[0], "integrity_check": [x[0] for x in con.execute("pragma integrity_check")], "foreign_key_check": [tuple(x) for x in con.execute("pragma foreign_key_check")], "wal_shm": [str(x) for x in (path.with_name(path.name+'-wal'), path.with_name(path.name+'-shm')) if x.exists()]}


def filas(path):
    with sqlite3.connect(path) as con:
        con.row_factory = sqlite3.Row
        return {row["oposicion_id"]: dict(row) for row in con.execute("select * from oposiciones")}


def main(backup):
    esperado = {str(k): v for k, v in json.loads(SPEC.read_text(encoding="utf-8"))["conjunto_aprobable_9j2"]["canon_por_id"].items()}
    before, after = filas(backup), filas(DB)
    diffs = {}
    for ident, old in before.items():
        fields = [key for key in old if old[key] != after[ident][key]]
        if fields: diffs[str(ident)] = fields
    changed = {ident for ident in diffs}
    final_canons = {ident: after[int(ident)]["puesto_normalizado"] for ident in changed}
    second = json.loads(DRY.read_text(encoding="utf-8"))
    # El dry-run posterior expresa correctamente cero cambios; su comparación
    # contra el conjunto aprobado deja ausentes por diseño tras la aplicación.
    protected = {str(i): after[i]["puesto_normalizado"] for i in (4075,13383,58860,76416,95446,106790,72683)}
    informe = {"sqlite_inicial": estado(backup), "sqlite_final": estado(DB), "backup": {"ruta": str(backup), **estado(backup)}, "aplicacion": {"filas": len(changed), "plazas": sum(int(after[int(i)]["num_plazas"] or 0) for i in changed), "data_version": ["32", "33"]}, "ids_esperados": sorted(esperado, key=int), "ids_modificados": sorted(changed, key=int), "ids_extra": sorted(changed-set(esperado), key=int), "ids_ausentes": sorted(set(esperado)-changed, key=int), "canon_por_id": final_canons, "canones": dict(Counter(final_canons.values())), "campos_por_fila": diffs, "campos_ajenos": sorted({field for fields in diffs.values() for field in fields if field != "puesto_normalizado"}), "contextuales_protegidos": protected, "id_72683": protected["72683"], "segundo_dry_run": {"cambios": second["obtenidos"], "ids_ausentes_al_estabilizar": second["ids_ausentes"]}, "integridad_final": {"integrity_check": estado(DB)["integrity_check"], "foreign_key_check": estado(DB)["foreign_key_check"]}}
    informe["correcta"] = len(changed) == 6 and informe["aplicacion"]["plazas"] == 7 and not informe["ids_extra"] and not informe["ids_ausentes"] and not informe["campos_ajenos"] and all(final_canons[str(k)] == v for k, v in esperado.items()) and second["obtenidos"] == 0
    OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"correcta": informe["correcta"], "filas": len(changed), "plazas": informe["aplicacion"]["plazas"], "ids_extra": informe["ids_extra"], "ids_ausentes": informe["ids_ausentes"], "campos_ajenos": informe["campos_ajenos"], "segundo_dry_run": second["obtenidos"]}, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) != 2: raise SystemExit("uso: auditar_aplicacion... BACKUP")
    main(sys.argv[1])
