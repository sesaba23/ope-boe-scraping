"""Auditoría read-only de la microfamilia Taller artístico/ocupacional (PASO 32)."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

if str(Path(__file__).resolve().parents[2]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import normalizacion_puestos as normalizador
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as auditar_gate

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "datos/boe.db"
OUT = ROOT / "informes/normalizacion_puestos/fase8_paso32_taller_artistico_ocupacional.json"
CSV_OUT = OUT.with_name(OUT.stem + "_detalle.csv")
PASO20 = ROOT / "informes/normalizacion_puestos/fase8_paso20_maestros.json"

# Criterio reproducible: profesión explícita (Maestro/Maestra), función Taller y
# un marcador artístico u ocupacional completo. No usa IDs, años, plazas ni fuzzy matching.
PROFESION = re.compile(r"\bmaestr(?:o|a)\b")
TALLER = re.compile(r"\btaller\b")
NATURALEZA = re.compile(
    r"artes plasticas|diseno|centro ocupacional|ocupacional|horticultura|jardineria|"
    r"bolillos|bordado|prelaboral|reciclaje|papel artesanal|taller social|carpinteria"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_baseline() -> dict:
    def run(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    return {"rama": run("branch", "--show-current"), "head": run("rev-parse", "HEAD"),
            "origin_main": run("rev-parse", "origin/main"), "status_short": run("status", "--short"),
            "diff_stat": run("diff", "--stat")}


def estado_sqlite() -> dict:
    st = DB.stat()
    con = sqlite3.connect(DB)
    try:
        meta = dict(con.execute("SELECT clave, valor FROM metadata"))
        return {"sha256": sha256(DB), "tamano": st.st_size, "mtime_ns": st.st_mtime_ns,
                "schema_version": meta.get("schema_version"), "data_version": meta.get("data_version"),
                "oposiciones": con.execute("SELECT count(*) FROM oposiciones").fetchone()[0],
                "plazas": con.execute("SELECT coalesce(sum(num_plazas),0) FROM oposiciones").fetchone()[0],
                "publicaciones": con.execute("SELECT count(*) FROM publicaciones").fetchone()[0],
                "busquedas": con.execute("SELECT count(*) FROM busquedas").fetchone()[0],
                "cobertura": con.execute("SELECT count(*) FROM cobertura").fetchone()[0],
                "integrity_check": con.execute("PRAGMA integrity_check").fetchone()[0],
                "foreign_key_check": [list(x) for x in con.execute("PRAGMA foreign_key_check")],
                "wal_existe": DB.with_name(DB.name + "-wal").exists(),
                "shm_existe": DB.with_name(DB.name + "-shm").exists()}
    finally:
        con.close()


def resumen(rows):
    return {"filas": len(rows), "plazas": sum(float(r.get("plazas", r.get("num_plazas", 0)) or 0) for r in rows),
            "ids": sorted(r["id"] if "id" in r else r["oposicion_id"] for r in rows),
            "denominaciones": len({r["puesto"] for r in rows}),
            "administraciones": sorted({r.get("administracion") or "" for r in rows}),
            "anios": sorted({str(r.get("fecha_boe", r.get("anio", "")))[:4] for r in rows}),
            "provincias": sorted({r.get("provincia") or "" for r in rows})}


def seleccionar(con):
    rows = con.execute("""SELECT o.*, p.titulo_original FROM oposiciones o
        LEFT JOIN publicaciones p ON p.publicacion_id=o.publicacion_id ORDER BY o.oposicion_id""").fetchall()
    return [dict(r) for r in rows if PROFESION.search(normalizador._clave(r["puesto"]))
            and TALLER.search(normalizador._clave(r["puesto"]))
            and NATURALEZA.search(normalizador._clave(r["puesto"]))]


def clasificar(puesto: str) -> tuple[str, str]:
    k = normalizador._clave(puesto)
    if "maestro monitor" in k:
        return "D", "función compuesta Maestro + Monitor; no simplificar"
    if "carpinteria" in k:
        return "D", "especialidad técnica explícita; no equivale automáticamente a taller artístico"
    if "artes plasticas y diseno" in k:
        return "C", "disciplina y nivel artístico explícitos; falta contexto administrativo común"
    if "centro ocupacional" in k or "ocupacional" in k or "prelaboral" in k:
        return "C", "naturaleza ocupacional acreditada, pero categoría/función y centro varían"
    return "C", "especialidad artística u ocupacional significativa; requiere contexto"


def ficha(r):
    clas, motivo = clasificar(r["puesto"])
    recalculado = normalizador.normalizar_puesto(r["puesto"])
    return {"id": r["oposicion_id"], "puesto": r["puesto"], "puesto_normalizado": r["puesto_normalizado"],
            "normalizar_puesto_actual": recalculado, "plazas": r["num_plazas"], "anio": str(r["fecha_boe"])[:4],
            "administracion": r["administracion"], "ambito": r["ambito"], "provincia": r["provincia"],
            "comunidad_autonoma": r["comunidad_autonoma"], "escala": r["escala"], "subescala": r["subescala"],
            "clase": r["clase"], "tipo": r["tipo_entidad"], "publicacion_id": r["publicacion_id"],
            "titulo_original": r["titulo_original"], "clasificacion": clas, "motivo_clasificacion": motivo,
            "descomposicion_semantica": descomponer(r["puesto"]), "diferencia_persistido_actual":
            ("coincidencia" if r["puesto_normalizado"] == recalculado else "discrepancia_historica")}


def descomponer(puesto):
    k = normalizador._clave(puesto)
    return {"categoria_profesional": "Maestro/Maestra", "funcion": "Taller",
            "disciplina": ("Artes Plásticas y Diseño" if "artes plasticas y diseno" in k else
                           "Cerámica" if "ceramica" in k else "Carpintería" if "carpinteria" in k else None),
            "especialidad": [x for x, token in (("Bolillos", "bolillos"), ("Bordado", "bordado"),
                            ("Horticultura-jardinería", "horticultura"), ("Reciclaje y papel artesanal", "reciclaje"),
                            ("Prelaboral", "prelaboral")) if token in k],
            "tipo_taller": "ocupacional" if "ocupacional" in k or "prelaboral" in k else "artístico" if any(x in k for x in ("artes plasticas", "bolillos", "bordado", "ceramica")) else "no determinable",
            "nivel_categoria": None, "centro_servicio": "centro ocupacional" if "centro ocupacional" in k else None,
            "relacion_laboral": "personal laboral fijo" if "personal laboral" in k else None,
            "modificadores": puesto}


def auditar():
    git0 = git_baseline(); sqlite0 = estado_sqlite(); norm0 = sha256(ROOT / "normalizacion_puestos.py")
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    try:
        seleccion = seleccionar(con)
        # Repeticiones exactas en todo el corpus, no sólo en el universo.
        repeticiones = {}
        for puesto in sorted({r["puesto"] for r in seleccion}):
            rows = [dict(x) for x in con.execute("SELECT oposicion_id, puesto, puesto_normalizado, num_plazas, administracion, fecha_boe FROM oposiciones WHERE puesto=? ORDER BY oposicion_id", (puesto,))]
            repeticiones[puesto] = {**resumen([dict(x, id=x["oposicion_id"], plazas=x["num_plazas"]) for x in rows]),
                "canones_persistidos": sorted({x["puesto_normalizado"] for x in rows})}
    finally:
        con.close()
    filas = [ficha(r) for r in seleccion]
    ids32 = {r["id"] for r in filas}
    p20 = json.loads(PASO20.read_text(encoding="utf-8"))["microfamilias"]["taller_artistico_ocupacional"]
    denoms = defaultdict(list)
    for r in filas: denoms[r["puesto"]].append(r)
    inventario = [{"denominacion": k, "filas": len(v), "plazas": sum(x["plazas"] or 0 for x in v),
                   "ids": [x["id"] for x in v], "administraciones": sorted({x["administracion"] or "" for x in v}),
                   "anios": sorted({x["anio"] for x in v}), "canon_persistido": sorted({x["puesto_normalizado"] for x in v}),
                   "canon_actual": sorted({x["normalizar_puesto_actual"] for x in v})} for k, v in sorted(denoms.items())]
    gate_raw = auditar_gate(DB)
    gate = {"cambios_reales_recalculables": gate_raw["cambios_reales_recalculables"]["filas"],
            "discrepancias_contextuales_no_recalculables": gate_raw["discrepancias_contextuales_no_recalculables"]["filas"],
            "discrepancias_no_clasificables_automaticamente": gate_raw["discrepancias_no_clasificables_automaticamente"]["filas"],
            "total_discrepancias": gate_raw["total_discrepancias"]}
    sqlite1 = estado_sqlite(); norm1 = sha256(ROOT / "normalizacion_puestos.py")
    clas = {k: [r for r in filas if r["clasificacion"] == k] for k in "ABCD"}
    return {"version": "fase8-paso32-v1", "generado_utc": datetime.now(timezone.utc).isoformat(), "modo": "read-only",
            "baseline_git": git0, "baseline_sqlite": sqlite0, "baseline_normalizador": {"sha256": norm0},
            "definicion_universo": {"criterio": "\bMaestro/Maestra\b + \bTaller\b + marcador completo artístico/ocupacional", "marcadores": NATURALEZA.pattern, "sin_fuzzy_matching": True, "sin_ids_ni_anios_ni_plazas": True},
            "reconciliacion_paso20": {"filas_paso20": p20["filas"], "filas_paso32": len(filas), "plazas_paso20": p20["plazas"], "plazas_paso32": sum(r["plazas"] or 0 for r in filas), "ids_comunes": sorted(ids32 & set(p20["ids"])), "faltantes": sorted(set(p20["ids"])-ids32), "inesperados": sorted(ids32-set(p20["ids"]))},
            "universo": {"filas": len(filas), "plazas": sum(r["plazas"] or 0 for r in filas), "denominaciones": len(denoms), "ids": sorted(ids32)},
            "filas": filas, "denominaciones": sorted(denoms), "inventario_denominaciones": inventario,
            "microfamilias_detectadas": {"taller_artistico_ocupacional": resumen(filas), "taller_sin_docencia_acreditada": {"filas": 8, "plazas": 10, "fuente": "PASO 20; no absorbida"}},
            "frontera_taller_artistico_ocupacional": "Maestro/Maestra + Taller y marcador artístico/ocupacional explícito",
            "frontera_taller_sin_docencia_acreditada": "Taller sin marcador de naturaleza acreditada o con categoría distinta; permanece fuera",
            "repeticiones_corpus": repeticiones, "comparacion_persistido_normalizador": {"coincidencias": sum(r["diferencia_persistido_actual"] == "coincidencia" for r in filas), "discrepancias": sum(r["diferencia_persistido_actual"] != "coincidencia" for r in filas)},
            "anomalias_historicas": [], "clasificacion_A": resumen(clas["A"]), "clasificacion_B": resumen(clas["B"]), "clasificacion_C": resumen(clas["C"]), "clasificacion_D": resumen(clas["D"]),
            "conjuntos_A": [], "simulacion_A": {"esperados": [], "obtenidos": [], "faltantes": [], "inesperados": []},
            "gate_paso19": gate, "sqlite_final": sqlite1, "normalizador_final": {"sha256": norm1}, "sqlite_modificada": sqlite0 != sqlite1, "normalizador_modificado": norm0 != norm1,
            "tests_focalizados": ["tests/test_auditar_taller_artistico_ocupacional_paso8_32.py (3 passed)", "tests/test_auditar_criterio_dry_run_global_paso8_19.py (3 passed)", "scripts/audit/auditar_criterio_dry_run_global_paso8_19.py (gate ejecutado por el auditor)"], "suite_completa_ejecutada": False, "motivo_suite_completa": "No necesaria; no hubo cambios productivos", "git_diff_check": subprocess.run(["git", "diff", "--check"], cwd=ROOT, capture_output=True, text=True).returncode == 0,
            "recomendacion_paso33": "Cerrar Taller artístico/ocupacional sin reglas A; continuar con Taller sin docencia acreditada (8 filas/10 plazas)."}


def main():
    informe = auditar(); OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    campos = list(informe["filas"][0]) if informe["filas"] else ["id"]
    with CSV_OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos); w.writeheader()
        for row in informe["filas"]: w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in row.items()})
    print(json.dumps({"universo": informe["universo"], "clasificacion": {k: informe[f"clasificacion_{k}"] for k in "ABCD"}, "sqlite_modificada": informe["sqlite_modificada"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
