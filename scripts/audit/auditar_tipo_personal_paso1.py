"""Auditoría read-only del clasificador experimental tipo_personal v1."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tipo_personal import CATEGORIAS, clasificar_tipo_personal

PERIODOS = (
    ("2004-2010", 2004, 2010),
    ("2011-2015", 2011, 2015),
    ("2016-2020", 2016, 2020),
    ("2021-2026", 2021, 2026),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_state(path: Path) -> dict[str, object]:
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as con:
        metadata = dict(con.execute("SELECT clave, valor FROM metadata"))
        return {
            "sha256": sha256(path),
            "schema_version": metadata.get("schema_version"),
            "data_version": metadata.get("data_version"),
            "integrity_check": con.execute("PRAGMA integrity_check").fetchone()[0],
            "foreign_key_check": [list(row) for row in con.execute("PRAGMA foreign_key_check")],
        }


def _periodo(fecha: str) -> str:
    year = int((fecha or "0000")[:4])
    for nombre, inicio, fin in PERIODOS:
        if inicio <= year <= fin:
            return nombre
    return "fuera_de_periodo"


def _señales(resultado: dict[str, object]) -> list[str]:
    return list(resultado["reglas_aplicadas"])


def auditar(ruta_bd: str | Path = "datos/boe.db", salida: str | Path | None = None) -> dict[str, object]:
    db = Path(ruta_bd)
    antes = _read_state(db)
    with sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True) as con:
        con.row_factory = sqlite3.Row
        oposiciones = [dict(row) for row in con.execute("SELECT * FROM oposiciones ORDER BY oposicion_id")]
        publicaciones = {row["publicacion_id"]: dict(row) for row in con.execute("SELECT * FROM publicaciones")}

    resultados = []
    categorias = Counter()
    confianza = Counter()
    reglas = Counter()
    periodos = defaultdict(Counter)
    conflictos = Counter()
    muestras = defaultdict(list)
    for row in oposiciones:
        resultado = clasificar_tipo_personal(row, publicaciones.get(row["publicacion_id"]))
        resultado = {
            **resultado,
            "oposicion_id": row["oposicion_id"],
            "fecha_boe": row["fecha_boe"],
            "puesto": row["puesto"],
            "administracion": row["administracion"],
            "ambito": row["ambito"],
            "tipo_entidad": row["tipo_entidad"],
        }
        resultados.append(resultado)
        categorias[resultado["categoria"]] += 1
        confianza[resultado["confianza"]] += 1
        for regla in _señales(resultado):
            reglas[regla] += 1
        periodos[_periodo(row["fecha_boe"])][resultado["categoria"]] += 1
        if resultado["categoria"] != "No determinado" and len(muestras[resultado["categoria"]]) < 30:
            muestras[resultado["categoria"]].append(resultado)

        familias = set(resultado["familias_detectadas"])
        if len(familias) > 1:
            conflictos[" + ".join(sorted(familias)) + " -> " + resultado["categoria"]] += 1

    despues = _read_state(db)
    if antes["sha256"] != despues["sha256"]:
        raise RuntimeError("SQLite cambió durante la auditoría")
    total = len(oposiciones)
    report = {
        "version": "tipo-personal-v1-auditoria",
        "modo": "read-only",
        "total_oposiciones": total,
        "categorias": {c: {"registros": categorias[c], "porcentaje": round(categorias[c] * 100 / total, 4)} for c in CATEGORIAS},
        "confianza": dict(confianza),
        "reglas": dict(reglas),
        "periodos": {p: {c: {"registros": counts[c], "porcentaje": round(counts[c] * 100 / sum(counts.values()), 4)} for c in CATEGORIAS} for p, counts in periodos.items()},
        "solapamientos": dict(conflictos),
        "muestras": {c: muestras[c] for c in CATEGORIAS if muestras[c]},
        "muestras_revision": {
            c: [r for r in resultados if r["categoria"] == c][:50 if c == "No determinado" else 30]
            for c in CATEGORIAS if any(r["categoria"] == c for r in resultados)
        },
        "muestras_confianza_media": [r for r in resultados if r["confianza"] == "media"][:50],
        "estado_sqlite_antes": antes,
        "estado_sqlite_despues": despues,
    }
    if salida:
        Path(salida).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="datos/boe.db")
    parser.add_argument("--salida")
    args = parser.parse_args()
    print(json.dumps(auditar(args.db, args.salida), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
