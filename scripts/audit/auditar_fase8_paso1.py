"""Auditoría reproducible (read-only) de profesores genéricos y docencia local.

El script reconstruye el universo desde SQLite y no escribe nunca en la base.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

RUTA_BD = Path("datos/boe.db")
RUTA_SALIDA = Path("informes/normalizacion_puestos/fase8_paso1_auditoria.json")
PATRON_UNIVERSO = re.compile(
    r"profesor(?:a|es|as)?(?:/a|/as)?|profesorado|docente(?:s)?|"
    r"enseñanza|escuela|academia|formaci[oó]n|instructor(?:a)?|"
    r"maestr(?:o|a|os|as)|catedr|titular|monitor|t[eé]cnic|auxiliar|"
    r"taller|educador|idioma|universidad|conservatorio",
    re.IGNORECASE,
)


def _plazas(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def clasificar(puesto: str | None, puesto_normalizado: str | None, ambito: str | None) -> str:
    """Clasificación excluyente, conservadora y sólo para auditoría."""
    texto = (puesto or "").casefold()
    if puesto_normalizado and puesto_normalizado != (puesto or ""):
        return "YA_NORMALIZADA"
    if re.search(r"universidad|catedr|titular", texto):
        return "UNIVERSIDAD"
    if re.search(r"formaci[oó]n profesional|\bfp\b", texto):
        return "FORMACION_PROFESIONAL"
    if re.search(r"escuela oficial|\beoi\b|idioma", texto):
        return "EOI_O_IDIOMAS"
    if "monitor" in texto:
        return "MONITOR"
    if "auxiliar" in texto:
        return "AUXILIAR"
    if re.search(r"t[eé]cnic", texto):
        return "TECNICO"
    if "taller" in texto:
        return "TALLER"
    if re.search(r"educador|instructor", texto):
        return "EDUCADOR_INSTRUCTOR"
    if re.search(r"m[uú]sic|instrument|conservatorio", texto):
        return "DOCENCIA_MUSICAL_RESIDUAL"
    if re.search(r"arte|danza|pintura|cer[aá]mica", texto):
        return "DOCENCIA_ARTISTICA_RESIDUAL"
    if "maestr" in texto:
        return "DOCENCIA_CON_ESPECIALIDAD" if len(texto.split()) > 2 else "PROFESOR_GENERICO"
    if re.search(r"profesor|docente|enseñanza|escuela|academia|formaci[oó]n", texto):
        return "DOCENCIA_LOCAL_ESPECIFICA" if ambito == "LOCAL" else "PROFESOR_GENERICO"
    return "NO_DOCENTE"


def _metadata(con: sqlite3.Connection) -> dict[str, str]:
    return dict(con.execute("SELECT clave, valor FROM metadata"))


def ejecutar(ruta_bd: Path = RUTA_BD, salida: Path = RUTA_SALIDA) -> dict:
    con = sqlite3.connect(ruta_bd)
    con.row_factory = sqlite3.Row
    try:
        metadata = _metadata(con)
        filas = [r for r in con.execute("SELECT * FROM oposiciones ORDER BY oposicion_id")
                 if PATRON_UNIVERSO.search(r["puesto"] or "")]
        detalle = []
        por_familia: dict[str, dict] = defaultdict(lambda: {
            "filas": 0, "plazas": 0.0, "denominaciones": set(), "administraciones": set(),
            "ambitos": set(), "especialidades": set(), "centros": set(),
        })
        for row in filas:
            familia = clasificar(row["puesto"], row["puesto_normalizado"], row["ambito"])
            item = por_familia[familia]
            item["filas"] += 1
            item["plazas"] += _plazas(row["num_plazas"])
            item["denominaciones"].add(row["puesto"] or "")
            item["administraciones"].add(row["administracion"] or "")
            item["ambitos"].add(row["ambito"] or "")
            # Señales descriptivas, nunca reglas productivas.
            for token in re.findall(r"(?:especialidad|materia|instrumento|idioma|m[uú]sica)[^,;)]*", row["puesto"] or "", re.I):
                item["especialidades"].add(token.strip())
            for token in re.findall(r"(?:escuela|conservatorio|academia|centro)[^,;)]*", row["puesto"] or "", re.I):
                item["centros"].add(token.strip())
            detalle.append({"oposicion_id": row["oposicion_id"], "familia": familia,
                            "puesto": row["puesto"], "puesto_normalizado": row["puesto_normalizado"]})
        familias = {}
        for nombre, item in sorted(por_familia.items()):
            familias[nombre] = {k: (sorted(v) if isinstance(v, set) else round(v, 2) if isinstance(v, float) else v)
                                for k, v in item.items()}
            familias[nombre]["ejemplos"] = [x["puesto"] for x in detalle if x["familia"] == nombre][:5]
        ids = [x["oposicion_id"] for x in detalle]
        baseline_path = Path("informes/normalizacion_puestos/fase7_otros_docentes_paso9q1c_baseline.json")
        baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else None
        result = {
            "modo": "read-only",
            "sqlite": {"ruta": str(ruta_bd), "metadata": metadata,
                       "integrity_check": [x[0] for x in con.execute("PRAGMA integrity_check")],
                       "foreign_key_check": [list(x) for x in con.execute("PRAGMA foreign_key_check")]},
            "universo": {"filas": len(filas), "plazas": round(sum(_plazas(r["num_plazas"]) for r in filas), 2),
                         "denominaciones": len({r["puesto"] for r in filas}), "ids": ids},
            "familias": familias,
            "baseline_9q": {"filas": 19320, "fingerprint": "613cbed5ea44b697f8f55baf932f6f0cc00f29b8ba7e2223c0c38046082c9b43",
                            "disponible": baseline is not None},
            "conjunto_seguro": {"reglas": [], "filas": 0, "plazas": 0, "motivo": "El universo es heterogéneo; no se propone canon genérico que preserve especialidad."},
            "dry_run_efectivo": {"filas_que_cambiarian": 0},
        }
    finally:
        con.close()
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


if __name__ == "__main__":
    print(json.dumps(ejecutar(), ensure_ascii=False, indent=2))
