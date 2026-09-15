"""Audita la aplicación 9H-6 sin realizar escrituras sobre SQLite."""

import hashlib
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from recalcular_puestos_normalizados import recalcular

DB = ROOT / "datos" / "boe.db"
INFORME_9H5 = ROOT / "informes" / "normalizacion_puestos" / "fase7_docencia_musical_paso9h5_dry_run.json"
OUT = ROOT / "informes" / "normalizacion_puestos" / "fase7_docencia_musical_paso9h6_aplicacion.json"


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _estado(path):
    path = Path(path)
    with sqlite3.connect(path) as con:
        return {
            "ruta": str(path), "sha256": _sha256(path), "tamano": path.stat().st_size,
            "mtime_ns": path.stat().st_mtime_ns,
            "versiones": dict(con.execute(
                "SELECT clave, valor FROM metadata WHERE clave IN ('schema_version', 'data_version')"
            )),
            "oposiciones_y_plazas": dict(zip(
                ("oposiciones", "plazas"),
                con.execute("SELECT COUNT(*), COALESCE(SUM(num_plazas), 0) FROM oposiciones").fetchone(),
            )),
            "integrity_check": [x[0] for x in con.execute("PRAGMA integrity_check")],
            "foreign_key_check": [tuple(x) for x in con.execute("PRAGMA foreign_key_check")],
            "wal_existe": path.with_name(path.name + "-wal").exists(),
            "shm_existe": path.with_name(path.name + "-shm").exists(),
        }


def _filas_por_id(path):
    with sqlite3.connect(path) as con:
        con.row_factory = sqlite3.Row
        return {
            fila["oposicion_id"]: dict(fila)
            for fila in con.execute("SELECT * FROM oposiciones")
        }


def _regresiones():
    with sqlite3.connect(DB) as con:
        return {
            "policia_ids_nacionales": dict(con.execute(
                "SELECT oposicion_id, puesto_normalizado FROM oposiciones "
                "WHERE oposicion_id IN (24085, 24559, 25324)"
            )),
            "policia_pendientes": dict(con.execute(
                "SELECT oposicion_id, puesto_normalizado FROM oposiciones "
                "WHERE oposicion_id IN (27123, 27694, 28254, 29606)"
            )),
            "ayudantes": dict(con.execute(
                "SELECT oposicion_id, puesto_normalizado FROM oposiciones "
                "WHERE oposicion_id IN (2630, 5354, 7859, 12660)"
            )),
        }


def main(backup):
    previo = json.loads(INFORME_9H5.read_text(encoding="utf-8"))
    esperado = {fila["id"]: fila["canon_propuesto"] for fila in previo["auditoria_inversa"]}
    anterior, final = _filas_por_id(backup), _filas_por_id(DB)
    diferencias = {}
    for ident in anterior:
        campos = [campo for campo in anterior[ident] if anterior[ident][campo] != final[ident][campo]]
        if campos:
            diferencias[ident] = campos
    ids_modificados = set(diferencias)
    plazas = sum(int(final[ident]["num_plazas"] or 0) for ident in ids_modificados)
    frecuencia_final = Counter(final[ident]["puesto_normalizado"] for ident in ids_modificados)
    frecuencia_esperada = Counter(esperado.values())
    ejemplos = {}
    for etiqueta in ("Piano", "Guitarra", "Violín", "Viola", "Violonchelo", "Contrabajo", "Flauta", "Clarinete", "Saxofón", "Trompeta", "Trombón", "Percusión", "Canto", "Lenguaje Musical"):
        canon = next((x for x in frecuencia_final if x.endswith(f"- {etiqueta}")), None)
        if canon:
            ejemplos[etiqueta] = canon
    cinco = {ident: final[ident]["puesto_normalizado"] for ident in (48453, 85283, 85329, 89573, 94128)}
    informe = {
        "sqlite_inicial_backup": _estado(backup), "sqlite_final": _estado(DB),
        "esperados": len(esperado), "ids_modificados": len(ids_modificados),
        "ids_extra": sorted(ids_modificados - set(esperado)),
        "ids_ausentes": sorted(set(esperado) - ids_modificados),
        "plazas_modificadas": plazas,
        "canones_distintos": [
            {"id": ident, "esperado": esperado[ident], "final": final[ident]["puesto_normalizado"]}
            for ident in sorted(set(esperado) & ids_modificados)
            if esperado[ident] != final[ident]["puesto_normalizado"]
        ],
        "campos_diferentes": {str(ident): campos for ident, campos in diferencias.items()},
        "canones_distintos_total": len(frecuencia_final),
        "frecuencia_canones": [
            {"canon": canon, "filas": cantidad,
             "plazas": sum(int(final[i]["num_plazas"] or 0) for i in ids_modificados if final[i]["puesto_normalizado"] == canon)}
            for canon, cantidad in sorted(frecuencia_final.items())
        ],
        "frecuencias_coinciden": frecuencia_final == frecuencia_esperada,
        "especialidades_representativas": ejemplos,
        "cinco_ids_9h4b": cinco,
        "regresiones": _regresiones(),
        "segundo_dry_run": recalcular(dry_run=True),
    }
    informe["correcta"] = (
        informe["ids_modificados"] == 1363 and informe["plazas_modificadas"] == 1884
        and not informe["ids_extra"] and not informe["ids_ausentes"]
        and not informe["canones_distintos"] and informe["canones_distintos_total"] == 72
        and informe["frecuencias_coinciden"]
        and all(campos == ["puesto_normalizado"] for campos in diferencias.values())
        and all(canon == "Profesor de Música" for canon in cinco.values())
        and informe["segundo_dry_run"]["filas_que_cambiarian"] == 0
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "correcta": informe["correcta"], "filas": informe["ids_modificados"],
        "plazas": informe["plazas_modificadas"], "canones": informe["canones_distintos_total"],
        "segundo_dry_run": informe["segundo_dry_run"]["filas_que_cambiarian"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1])
