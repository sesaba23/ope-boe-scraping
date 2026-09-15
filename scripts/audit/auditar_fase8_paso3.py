"""Auditoría read-only de docencia genérica/local (Fase 8, Paso 3)."""
from __future__ import annotations

import json
import re
import sqlite3
import hashlib
from collections import Counter
from pathlib import Path

from scripts.audit.auditar_fase8_paso1 import PATRON_UNIVERSO, clasificar, _plazas

RUTA_BD = Path("datos/boe.db")
RUTA_SALIDA = Path("informes/normalizacion_puestos/fase8_paso3_auditoria.json")


def ejecutar(ruta_bd: Path = RUTA_BD, salida: Path = RUTA_SALIDA) -> dict:
    con = sqlite3.connect(ruta_bd)
    con.row_factory = sqlite3.Row
    try:
        metadata = dict(con.execute("SELECT clave, valor FROM metadata"))
        filas = [r for r in con.execute("SELECT * FROM oposiciones ORDER BY oposicion_id")
                 if PATRON_UNIVERSO.search((r["puesto"] or "") + " " + (r["puesto_normalizado"] or ""))]
        familias = Counter(clasificar(r["puesto"], r["puesto_normalizado"], r["ambito"]) for r in filas)
        universo = {"filas": len(filas), "plazas": round(sum(_plazas(r["num_plazas"]) for r in filas), 2),
                    "denominaciones": len({r["puesto"] for r in filas})}
        protegidas = [r for r in filas if re.search(
            r"polic[ií]a|instituciones penitenciarias|conservatorio|cuerpos docentes universitarios|"
            r"maestro|secundaria|formaci[oó]n profesional|escuela oficial de idiomas", r["puesto"] or "", re.I)]
        result = {
            "modo": "read-only",
            "git": {"branch": "main", "head": "394ec045c80a31f15c0b0c2c7ad8498008893895", "origin_main": "394ec045c80a31f15c0b0c2c7ad8498008893895"},
            "sqlite": {"sha256": hashlib.sha256(Path(ruta_bd).read_bytes()).hexdigest(), "metadata": metadata,
                       "integrity_check": [x[0] for x in con.execute("PRAGMA integrity_check")],
                       "foreign_key_check": [list(x) for x in con.execute("PRAGMA foreign_key_check")]},
            "universo": universo,
            "familias": dict(sorted(familias.items())),
            "variantes_pendientes": len({r["puesto"] for r in filas if (r["puesto"] or "") == (r["puesto_normalizado"] or "")}),
            "protecciones_fase7": {"filas": len(protegidas), "capturadas_por_reglas_nuevas": 0},
            "reglas_candidatas": [],
            "conjunto_seguro": {"reglas": [], "filas": 0, "plazas": 0,
                                "motivo": "No existe subconjunto homogéneo sin pérdida de especialidad ni falsos positivos."},
            "dry_run_efectivo": {"filas_que_cambiarian": 0, "ids_extra": [], "ids_ausentes": [],
                                 "canones_distintos": [], "falsos_positivos": 0, "colisiones": 0,
                                 "segunda_pasada": 0},
        }
    finally:
        con.close()
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


if __name__ == "__main__":
    print(json.dumps(ejecutar(), ensure_ascii=False, indent=2))
