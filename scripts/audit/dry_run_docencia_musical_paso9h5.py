"""Dry-run reproducible de las reglas musicales aprobadas en 9H-4 y 9H-4B.

No escribe SQLite; solo regenera un informe JSON de auditoría.
"""

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from normalizacion_contextual_puestos import normalizar_puesto_efectivo

DB = ROOT / "datos" / "boe.db"
APROBADO = ROOT / "informes" / "normalizacion_puestos" / "fase7_docencia_musical_paso9h4.json"
REVISION = ROOT / "informes" / "normalizacion_puestos" / "fase7_docencia_musical_paso9h4b.json"
OUT = ROOT / "informes" / "normalizacion_puestos" / "fase7_docencia_musical_paso9h5_dry_run.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _estado_sqlite(con: sqlite3.Connection) -> dict:
    return {
        "sha256": _sha256(DB),
        "tamano": DB.stat().st_size,
        "mtime_ns": DB.stat().st_mtime_ns,
        "versiones": dict(con.execute(
            "SELECT clave, valor FROM metadata "
            "WHERE clave IN ('schema_version', 'data_version')"
        )),
        "oposiciones_y_plazas": dict(zip(
            ("oposiciones", "plazas"),
            con.execute("SELECT COUNT(*), COALESCE(SUM(num_plazas), 0) FROM oposiciones").fetchone(),
        )),
        "integrity_check": [x[0] for x in con.execute("PRAGMA integrity_check")],
        "foreign_key_check": [tuple(x) for x in con.execute("PRAGMA foreign_key_check")],
        "wal_existe": DB.with_name(f"{DB.name}-wal").exists(),
        "shm_existe": DB.with_name(f"{DB.name}-shm").exists(),
    }


def _esperados() -> dict[int, str]:
    esperado = {
        fila["id"]: fila["canon"]
        for fila in json.loads(APROBADO.read_text(encoding="utf-8"))["cambios"]
    }
    for fila in json.loads(REVISION.read_text(encoding="utf-8"))["cinco_ids"]:
        esperado[fila["id"]] = fila["canon_productivo"]
    return esperado


def _normalizado(row: sqlite3.Row) -> str | None:
    return normalizar_puesto_efectivo(
        row["puesto"], administracion=row["administracion"], ambito=row["ambito"],
        tipo_entidad=row["tipo_entidad"], escala=row["escala"],
        subescala=row["subescala"], sistema=row["sistema"],
        municipio=row["municipio"], provincia=row["provincia"],
    ).normalizado


def _auditoria_inversa(rows: list[sqlite3.Row], obtenidos: dict[int, str]) -> list[dict]:
    salida = []
    for row in rows:
        canon = obtenidos.get(row["oposicion_id"])
        if canon is None:
            continue
        salida.append({
            "id": row["oposicion_id"], "puesto": row["puesto"],
            "puesto_normalizado_actual": row["puesto_normalizado"],
            "canon_propuesto": canon,
            "especialidad": canon.partition(" - ")[2] or None,
            "centro": "Conservatorio" if canon.startswith("Profesor de Conservatorio") else (
                "Escuela de Música" if canon.startswith("Profesor de Escuela de Música") else None
            ),
            "ambito": row["ambito"], "tipo_entidad": row["tipo_entidad"],
            "administracion": row["administracion"], "plazas": row["num_plazas"],
        })
    return salida


def _regresiones(con: sqlite3.Connection) -> dict:
    return {
        "policia": dict(con.execute(
            "SELECT puesto_normalizado, COUNT(*) FROM oposiciones "
            "WHERE puesto_normalizado IN ('Policía Local', 'Policía Nacional') "
            "GROUP BY puesto_normalizado"
        )),
        "nacionales": dict(con.execute(
            "SELECT oposicion_id, puesto_normalizado FROM oposiciones "
            "WHERE oposicion_id IN (24085, 24559, 25324)"
        )),
        "ayudantes_instituciones_penitenciarias": dict(con.execute(
            "SELECT oposicion_id, puesto_normalizado FROM oposiciones "
            "WHERE oposicion_id IN (2630, 5354, 7859, 12660)"
        )),
    }


def main() -> None:
    esperado = _esperados()
    with sqlite3.connect(DB) as con:
        con.row_factory = sqlite3.Row
        estado_inicial = _estado_sqlite(con)
        rows = con.execute("SELECT * FROM oposiciones").fetchall()
        obtenido, plazas = {}, 0
        for row in rows:
            canon = _normalizado(row)
            if canon != row["puesto_normalizado"]:
                obtenido[row["oposicion_id"]] = canon
                plazas += int(row["num_plazas"] or 0)
        extras = sorted(set(obtenido) - set(esperado))
        ausentes = sorted(set(esperado) - set(obtenido))
        distintos = [
            {"id": ident, "esperado": esperado[ident], "obtenido": obtenido[ident]}
            for ident in sorted(set(obtenido) & set(esperado))
            if esperado[ident] != obtenido[ident]
        ]
        auditoria = _auditoria_inversa(rows, obtenido)
        regresiones = _regresiones(con)
        estado_final = _estado_sqlite(con)

    revision_ids = [x["id"] for x in json.loads(REVISION.read_text(encoding="utf-8"))["cinco_ids"]]
    idempotencia = all(
        _normalizado(row) == obtenido[row["oposicion_id"]]
        for row in rows if row["oposicion_id"] in obtenido
    )
    correcta = (
        len(obtenido) == 1363 and plazas == 1884 and not extras and not ausentes
        and not distintos and idempotencia and estado_inicial == estado_final
    )
    informe = {
        "estado_sqlite_inicial": estado_inicial,
        "estado_sqlite_final": estado_final,
        "esperados": len(esperado), "plazas_esperadas": 1884,
        "obtenidos": len(obtenido), "plazas": plazas,
        "ids_extra": extras, "ids_ausentes": ausentes, "canones_distintos": distintos,
        "cinco_ids_9h4b": {ident: obtenido.get(ident) for ident in revision_ids},
        "idempotencia": idempotencia, "auditoria_inversa": auditoria,
        "regresiones": regresiones, "correcta": correcta,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: informe[key] for key in (
        "esperados", "plazas_esperadas", "obtenidos", "plazas", "ids_extra",
        "ids_ausentes", "canones_distintos", "idempotencia", "correcta",
    )}, ensure_ascii=False))


if __name__ == "__main__":
    main()
