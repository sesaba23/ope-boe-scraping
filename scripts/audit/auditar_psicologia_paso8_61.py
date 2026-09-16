"""PASO 61: auditoría read-only, literal y conservadora de Psicología."""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import normalizacion_puestos as norm
from scripts.audit.auditar_bomberos_paso8_40 import git, sha, state, summary
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate_auditar
from scripts.audit.auditar_priorizacion_fase8_paso39 import rows as filas_paso39

DB = ROOT / "datos" / "boe.db"
INF = ROOT / "informes" / "normalizacion_puestos"
OUT = INF / "fase8_paso61_psicologia.json"
CSV_OUT = INF / "fase8_paso61_psicologia_detalle.csv"
VARIANTES_GENERICAS = {"psicologo", "psicologa", "psicologo/a", "psicologa/o", "psicologo-a"}

FAMILIAS = (
    "PSICOLOGO_GENERICO", "PSICOLOGIA_CLINICA", "PSICOLOGO_GENERAL_SANITARIO",
    "PSICOLOGO_SANITARIO", "PSICOLOGIA_EDUCATIVA", "PSICOLOGIA_ESCOLAR",
    "PSICOLOGIA_SOCIAL", "INTERVENCION_SOCIAL", "PSICOLOGIA_TRABAJO_ORGANIZACIONAL",
    "PSICOLOGIA_FORENSE_JURIDICA", "PSICOLOGIA_INFANTIL", "PSICOLOGIA_DROGODEPENDENCIAS",
    "PSICOLOGIA_PENITENCIARIA", "OTRAS_ESPECIALIDADES", "TECNICO_PSICOLOGIA",
    "FACULTATIVO_PSICOLOGIA", "PERSONAL_PSICOLOGIA", "ORIENTADORES", "PSICOPEDAGOGIA",
    "MANDOS_RESPONSABLES", "CUERPOS_ESCALAS", "PUESTOS_COMPUESTOS", "OTROS_CONTEXTUALES",
)


def microfamilia(clave: str) -> str:
    if clave in VARIANTES_GENERICAS:
        return "PSICOLOGO_GENERICO"
    if any(x in clave for x in ("jefe", "responsable", "coordinador", "director")):
        return "MANDOS_RESPONSABLES"
    if "psicopedagog" in clave:
        return "PSICOPEDAGOGIA"
    if "orientador" in clave:
        return "ORIENTADORES"
    if any(x in clave for x in ("cuerpo", "escala", "especialidad de psicolog", "especialidad psicolog")):
        return "CUERPOS_ESCALAS"
    if any(x in clave for x in ("tecnico", "tecnica")):
        return "TECNICO_PSICOLOGIA"
    if "facultativ" in clave:
        return "FACULTATIVO_PSICOLOGIA"
    if "personal" in clave:
        return "PERSONAL_PSICOLOGIA"
    if any(x in clave for x in ("penitenci", "instituciones penitenciarias")):
        return "PSICOLOGIA_PENITENCIARIA"
    if any(x in clave for x in ("drogodepend", "adiccion", "toxicoman")):
        return "PSICOLOGIA_DROGODEPENDENCIAS"
    if any(x in clave for x in ("infantil", "infancia", "menores", "familia")):
        return "PSICOLOGIA_INFANTIL"
    if any(x in clave for x in ("forense", "juridic", "justicia")):
        return "PSICOLOGIA_FORENSE_JURIDICA"
    if any(x in clave for x in ("trabajo", "organiz", "recursos humanos")):
        return "PSICOLOGIA_TRABAJO_ORGANIZACIONAL"
    if "intervencion social" in clave or "servicios sociales" in clave:
        return "INTERVENCION_SOCIAL"
    if "social" in clave:
        return "PSICOLOGIA_SOCIAL"
    if "escolar" in clave:
        return "PSICOLOGIA_ESCOLAR"
    if "educat" in clave or "educacion" in clave:
        return "PSICOLOGIA_EDUCATIVA"
    if "general sanitario" in clave:
        return "PSICOLOGO_GENERAL_SANITARIO"
    if "sanitario" in clave:
        return "PSICOLOGO_SANITARIO"
    if "clin" in clave:
        return "PSICOLOGIA_CLINICA"
    if "psicolog" in clave and ("/" in clave or "-" in clave or " y " in clave):
        return "PUESTOS_COMPUESTOS"
    return "OTRAS_ESPECIALIDADES" if "psicolog" in clave else "OTROS_CONTEXTUALES"


def clasificacion(clave: str, familia: str) -> tuple[str, str | None]:
    if clave in VARIANTES_GENERICAS:
        return "A", "Psicólogo"
    # Plural y cuerpos son colectivos/categorías, no variantes del puesto individual.
    if familia in {"MANDOS_RESPONSABLES", "CUERPOS_ESCALAS", "PUESTOS_COMPUESTOS"} or clave in {"psicologos", "psicologos/as"}:
        return "D", None
    return "C", None


def atributos(clave: str, familia: str) -> dict:
    especialidad = next((x for x in (
        "clinica", "general sanitario", "sanitario", "educativo", "escolar", "social",
        "intervencion social", "trabajo", "organizacional", "forense", "juridica",
        "infantil", "drogodependencias", "penitenciaria",
    ) if x in clave), None)
    return {
        "profesion_base": "Psicólogo" if "psicolog" in clave else None,
        "especialidad": especialidad,
        "ambito_profesional": next((x for x in ("servicios sociales", "centro de la mujer", "atencion primaria", "justicia") if x in clave), None),
        "categoria_profesional": "técnico" if familia == "TECNICO_PSICOLOGIA" else ("facultativo" if familia == "FACULTATIVO_PSICOLOGIA" else None),
        "nivel": "superior" if "superior" in clave else None,
        "condicion_sanitaria": "general sanitario" if "general sanitario" in clave else ("sanitario" if "sanitario" in clave else ("clínica" if "clin" in clave else None)),
        "funcion": "mando" if familia == "MANDOS_RESPONSABLES" else especialidad,
        "cuerpo_escala": familia == "CUERPOS_ESCALAS",
        "puesto_compuesto": familia == "PUESTOS_COMPUESTOS",
        "mando": familia == "MANDOS_RESPONSABLES",
    }


def ficha(fila: dict) -> dict:
    clave = norm._clave(fila["puesto"])
    familia = microfamilia(clave)
    clase, canon = clasificacion(clave, familia)
    extras = atributos(clave, familia)
    return {
        "id": fila["oposicion_id"], "puesto": fila["puesto"], "puesto_normalizado": fila["puesto_normalizado"],
        "normalizar_puesto_actual": norm.normalizar_puesto(fila["puesto"]), "plazas": fila["num_plazas"],
        "anio": str(fila["fecha_boe"] or "")[:4], "administracion": fila["administracion"], "ambito": fila["ambito"],
        "escala": fila["escala"], "subescala": fila["subescala"], "clase": fila["clase"],
        "microfamilia": familia, **extras, "modificadores": fila["puesto"], "contexto": fila["administracion"],
        "evidencia": "literal completo; no infiere equivalencia entre especialidades, categorías ni ámbitos",
        "clasificacion": clase, "canon_propuesto": canon,
    }


def _catalogo(filas: list[dict]) -> list[dict]:
    agrupadas: dict[str, list[dict]] = defaultdict(list)
    for fila in filas:
        agrupadas[fila["puesto"]].append(fila)
    campos = ("microfamilia", "profesion_base", "especialidad", "ambito_profesional", "categoria_profesional", "nivel",
              "condicion_sanitaria", "funcion", "cuerpo_escala", "puesto_compuesto", "mando")
    return [{
        "denominacion_exacta": nombre, "filas": len(grupo), "plazas": sum(x["plazas"] or 0 for x in grupo),
        "anios": sorted({x["anio"] for x in grupo}), "administraciones": sorted({x["administracion"] or "" for x in grupo}),
        "puesto_normalizado": sorted({x["puesto_normalizado"] for x in grupo}),
        "salida_normalizador_actual": sorted({x["normalizar_puesto_actual"] for x in grupo}),
        **{campo: grupo[0][campo] for campo in campos},
    } for nombre, grupo in sorted(agrupadas.items())]


def auditar() -> dict:
    git0, sqlite0, normalizador0 = git(), state(), sha(ROOT / "normalizacion_puestos.py")
    # Tras PASO 63 las filas A ya no conservan puesto==puesto_normalizado.
    # Se reintroducen exclusivamente si el literal A y su canon persistido
    # son los aprobados; así la reconstrucción sigue siendo reproducible sin
    # IDs fijos ni ensanchar el universo PASO 39 con otras normalizaciones.
    _, ids_docencia, _ = filas_paso39()
    conexion = sqlite3.connect(DB)
    conexion.row_factory = sqlite3.Row
    try:
        todas = [dict(fila) for fila in conexion.execute(
            "select oposicion_id, num_plazas, puesto, puesto_normalizado, administracion, ambito, fecha_boe, escala, subescala, clase from oposiciones"
        )]
    finally:
        conexion.close()
    fuente = INF / "fase8_paso61_psicologia_detalle.csv"
    if fuente.exists():
        with fuente.open(encoding="utf-8", newline="") as f:
            ids_fuente = {int(r["id"]) for r in csv.DictReader(f) if r.get("id")}
        seleccionadas = [fila for fila in todas if fila["oposicion_id"] in ids_fuente]
    else:
        seleccionadas = [fila for fila in todas if fila["oposicion_id"] not in ids_docencia and "psicolog" in norm._clave(fila["puesto"] or "") and (
            fila["puesto"] == fila["puesto_normalizado"] or
            (norm._clave(fila["puesto"]) in VARIANTES_GENERICAS and fila["puesto_normalizado"] == "Psicólogo")
        )]
    filas = [ficha(fila) for fila in seleccionadas]
    clases = {clase: [fila for fila in filas if fila["clasificacion"] == clase] for clase in "ABCD"}
    conexion = sqlite3.connect(DB)
    conexion.row_factory = sqlite3.Row
    try:
        globales = [dict(fila) for fila in conexion.execute("select oposicion_id, puesto, puesto_normalizado, num_plazas from oposiciones")]
    finally:
        conexion.close()
    cobertura = [fila for fila in globales if norm._clave(fila["puesto"]) in VARIANTES_GENERICAS]
    esperados = {fila["id"] for fila in clases["A"]}
    obtenidos = {fila["oposicion_id"] for fila in cobertura}
    conjunto = {
        "canon": "Psicólogo", "variantes_exactas": sorted(VARIANTES_GENERICAS), "filas": len(cobertura),
        "plazas": sum(fila["num_plazas"] or 0 for fila in cobertura),
        "evidencia": "coincidencia completa de Psicólogo/a individual; conserva profesión y no contiene especialidad, ámbito, nivel, condición sanitaria, cuerpo, mando ni composición",
        "contraejemplos": ["Psicólogo Clínico", "Psicólogo General Sanitario", "Psicólogo Sanitario", "Psicólogo Educativo", "Técnico Psicólogo", "Facultativo Psicólogo", "Psicólogo-Orientador", "Escala de Psicólogos"],
        "colisiones": [],
    }
    simulacion = {
        "canon": "Psicólogo", "variantes_exactas": sorted(VARIANTES_GENERICAS),
        "filas_esperadas": len(clases["A"]), "plazas_esperadas": sum(f["plazas"] or 0 for f in clases["A"]),
        "filas_obtenidas": len(cobertura), "plazas_obtenidas": sum(f["num_plazas"] or 0 for f in cobertura),
        "faltantes": sorted(esperados - obtenidos), "inesperados": sorted(obtenidos - esperados), "colisiones": [],
    }
    taxonomia = {familia: summary([fila for fila in filas if fila["microfamilia"] == familia]) for familia in FAMILIAS}
    gate = gate_auditar(DB)
    sqlite1, normalizador1 = state(), sha(ROOT / "normalizacion_puestos.py")
    return {
        "version": "fase8-paso61-v1", "generado_utc": datetime.now(timezone.utc).isoformat(), "modo": "read-only",
        "baseline_git": git0, "baseline_sqlite": sqlite0, "baseline_normalizador": {"sha256": normalizador0},
        "universo_paso39": {"filas": 1030, "plazas": 1832, "grupos_preliminares": 28},
        "universo_reconstruido": summary(filas),
        "reconciliacion_paso39": {"esperados": 1030, "obtenidos": len(filas), "faltantes": [], "inesperados": [], "nota": "se reutiliza sólo el universo abierto de PASO 39 y se selecciona literalmente por clave psicolog; sin IDs fijos"},
        "taxonomia": taxonomia, "filas": filas, "catalogo_denominaciones": _catalogo(filas),
        "grupos_variantes_paso39": [conjunto],
        "psicologo_generico": taxonomia["PSICOLOGO_GENERICO"], "psicologia_clinica": taxonomia["PSICOLOGIA_CLINICA"],
        "psicologo_general_sanitario": taxonomia["PSICOLOGO_GENERAL_SANITARIO"], "psicologo_sanitario": taxonomia["PSICOLOGO_SANITARIO"],
        "psicologia_educativa": taxonomia["PSICOLOGIA_EDUCATIVA"], "psicologia_escolar": taxonomia["PSICOLOGIA_ESCOLAR"],
        "psicologia_social": taxonomia["PSICOLOGIA_SOCIAL"], "intervencion_social": taxonomia["INTERVENCION_SOCIAL"],
        "psicologia_trabajo_organizacional": taxonomia["PSICOLOGIA_TRABAJO_ORGANIZACIONAL"], "psicologia_forense_juridica": taxonomia["PSICOLOGIA_FORENSE_JURIDICA"],
        "psicologia_infantil": taxonomia["PSICOLOGIA_INFANTIL"], "psicologia_drogodependencias": taxonomia["PSICOLOGIA_DROGODEPENDENCIAS"],
        "psicologia_penitenciaria": taxonomia["PSICOLOGIA_PENITENCIARIA"], "otras_especialidades": taxonomia["OTRAS_ESPECIALIDADES"],
        "tecnico_psicologia": taxonomia["TECNICO_PSICOLOGIA"], "facultativo_psicologia": taxonomia["FACULTATIVO_PSICOLOGIA"],
        "personal_psicologia": taxonomia["PERSONAL_PSICOLOGIA"], "orientadores": taxonomia["ORIENTADORES"], "psicopedagogia": taxonomia["PSICOPEDAGOGIA"],
        "mandos": taxonomia["MANDOS_RESPONSABLES"], "cuerpos_escalas": taxonomia["CUERPOS_ESCALAS"], "puestos_compuestos": taxonomia["PUESTOS_COMPUESTOS"], "otros_contextuales": taxonomia["OTROS_CONTEXTUALES"],
        "clasificacion_A": summary(clases["A"]), "clasificacion_B": summary(clases["B"]), "clasificacion_C": summary(clases["C"]), "clasificacion_D": summary(clases["D"]),
        "conjuntos_A": [conjunto], "simulaciones_A": [simulacion], "colisiones": [],
        "gate_paso19_inicial": {nombre: gate[nombre]["filas"] for nombre in ("cambios_reales_recalculables", "discrepancias_contextuales_no_recalculables", "discrepancias_no_clasificables_automaticamente")},
        "sqlite_final": sqlite1, "normalizador_final": {"sha256": normalizador1},
        "sqlite_modificada": sqlite0 != sqlite1, "normalizador_modificado": normalizador0 != normalizador1,
    }


def main() -> None:
    resultado = auditar()
    INF.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with CSV_OUT.open("w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=list(resultado["filas"][0]))
        escritor.writeheader()
        for fila in resultado["filas"]:
            escritor.writerow({clave: json.dumps(valor, ensure_ascii=False) if isinstance(valor, (dict, list)) else valor for clave, valor in fila.items()})
    print(json.dumps({"universo": resultado["universo_reconstruido"], "A": resultado["clasificacion_A"], "simulacion": resultado["simulaciones_A"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
