"""Auditoría read-only de puestos docentes (Fase 7, paso 9)."""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "datos" / "boe.db"
OUT = ROOT / "informes" / "normalizacion_puestos" / "fase7_funcionarios_docentes_paso9.json"

PATRONES = {
    "universidad": r"\buniversidad\b|profesor(?:es)? titular(?:es)?|catedr[aá]tic",
    "maestros": r"\bmaestr(?:o|a|os|as)\b",
    "secundaria": r"enseñanza secundaria|secundaria",
    "fp": r"formaci[oó]n profesional|profesor(?:es)? t[eé]cnic",
    "eoi": r"escuela(?:s)? oficial(?:es)? de idiomas|\bEOI\b",
    "artistica": r"m[uú]sica|danza|artes pl[aá]sticas|conservatorio|teatro",
    "docente": r"\bdocent(?:e|es)\b|profesor(?:a|es|as)?|educador(?:a|es|as)?|monitor(?:a|es|as)?",
}


def familia(texto: str) -> str:
    t = (texto or "").casefold()
    for nombre, patron in PATRONES.items():
        if re.search(patron, t, re.I):
            return nombre
    return "otros"


def main() -> None:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """SELECT puesto, puesto_normalizado, administracion, ambito, tipo_entidad,
           escala, subescala, clase, sistema, turno, num_plazas, fecha_boe,
           oposicion_id, publicacion_id
           FROM oposiciones WHERE puesto IS NOT NULL"""
    ).fetchall()
    con.close()
    seleccionadas = [r for r in rows if familia(r["puesto"]) != "otros"]
    familias = Counter(familia(r["puesto"]) for r in seleccionadas)
    plazas_familias = Counter()
    ranking = Counter()
    variantes = defaultdict(Counter)
    ambitos = Counter()
    entidades = Counter()
    ejemplos = defaultdict(list)
    falsos = []
    sufijos = Counter()
    for r in seleccionadas:
        f = familia(r["puesto"])
        n = int(r["num_plazas"] or 0)
        plazas_familias[f] += n
        ranking[r["puesto"]] += n
        variantes[f][r["puesto"]] += 1
        ambitos[r["ambito"] or "NULL"] += 1
        entidades[r["tipo_entidad"] or "NULL"] += 1
        if len(ejemplos[f]) < 5:
            ejemplos[f].append(dict(r))
        if re.search(r"maestro de obras|monitor|auxiliar|t[eé]cnico(?! docente)", r["puesto"] or "", re.I):
            falsos.append(dict(r))
        for etiqueta, patron in (("plantilla", r"\bplantilla\b"), ("acceso", r"acceso libre"),
                                 ("oep", r"\boep\b"), ("funcionario", r"personal funcionario"),
                                 ("concurso", r"concurso[- ]oposici[oó]n|concurso")):
            if re.search(patron, r["puesto"] or "", re.I):
                sufijos[etiqueta] += 1
    ranking_rows = [{"denominacion": k, "filas": sum(1 for r in seleccionadas if r["puesto"] == k), "plazas": v}
                    for k, v in ranking.most_common()]
    propuesta = []
    for f, count in familias.most_common():
        propuesta.append({"familia": f, "canon_propuesto": {
            "universidad": "Catedráticos de Universidad / Profesores Titulares de Universidad",
            "maestros": "Maestros", "secundaria": "Profesores de Enseñanza Secundaria",
            "fp": "Profesores de Formación Profesional", "eoi": "Profesores de Escuelas Oficiales de Idiomas",
            "artistica": "Docencia artística específica", "docente": "Docencia no especificada",
        }.get(f, "Sin normalización"), "filas": count, "plazas": plazas_familias[f],
        "confianza": "DUDOSA", "tipo_regla": "PROPUESTA_NO_PRODUCTIVA"})
    informe = {"total_filas_auditadas": len(seleccionadas),
               "total_plazas": sum(int(r["num_plazas"] or 0) for r in seleccionadas),
               "denominaciones_distintas": len(ranking_rows),
               "distribucion_familias": dict(familias), "plazas_por_familia": dict(plazas_familias),
               "distribucion_ambito": dict(ambitos), "distribucion_tipo_entidad": dict(entidades),
               "ranking_denominaciones": ranking_rows, "variantes_por_familia": {k: dict(v) for k, v in variantes.items()},
               "propuestas_canones": propuesta, "sufijos_administrativos": dict(sufijos),
               "falsos_positivos_candidatos": falsos[:100], "ejemplos": dict(ejemplos),
               "precedencia_propuesta": ["exclusiones", "universidad específica", "cuerpos docentes", "docencia artística", "docencia local", "genérico"],
               "nota": "Auditoría read-only; no modifica normalizadores ni SQLite."}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"filas": len(seleccionadas), "plazas": informe["total_plazas"], "familias": dict(familias), "salida": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
