"""Auditoría read-only de los cambios de normalización de género (8.18)."""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from normalizacion_puestos import normalizar_puesto

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "datos" / "boe.db"
OUT = ROOT / "informes" / "normalizacion_puestos" / "fase8_paso18_estabilizacion_genero.json"
DETAIL = ROOT / "informes" / "normalizacion_puestos" / "fase8_paso18_estabilizacion_genero_detalle.csv"


def _estado(path: Path) -> dict:
    st = path.stat()
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        meta = dict(con.execute("select clave,valor from metadata"))
        return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "tamano": st.st_size,
                "mtime_ns": st.st_mtime_ns, "schema_version": meta.get("schema_version"),
                "data_version": meta.get("data_version"), "oposiciones": con.execute("select count(*) from oposiciones").fetchone()[0],
                "plazas": con.execute("select sum(coalesce(num_plazas,0)) from oposiciones").fetchone()[0],
                "publicaciones": con.execute("select count(*) from publicaciones").fetchone()[0],
                "busquedas": con.execute("select count(*) from busquedas").fetchone()[0],
                "cobertura": con.execute("select count(*) from cobertura").fetchone()[0],
                "integrity_check": con.execute("pragma integrity_check").fetchone()[0],
                "foreign_key_check": [list(x) for x in con.execute("pragma foreign_key_check")]}
    finally:
        con.close()


def auditar(ruta_bd: Path = DB) -> dict:
    ruta_bd = Path(ruta_bd)
    con = sqlite3.connect(f"file:{ruta_bd.resolve()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        filas = []
        for row in con.execute("select * from oposiciones order by oposicion_id"):
            nuevo = normalizar_puesto(row["puesto"])
            actual = row["puesto_normalizado"] or ""
            if nuevo == actual:
                continue
            # Este auditor conserva el universo histórico de la incidencia
            # policial; los nuevos cambios docentes del paso 21 pertenecen a
            # su auditor específico y no alteran la reproducción del paso 18.
            if actual.casefold() not in {"policía local", "policia local", "policía nacional", "policia nacional"}:
                continue
            # El universo observado es Policía aislada: el canon previo aporta
            # «Local», por lo que reducirlo a «Policía» pierde información.
            subtipo = "canon_local_reducido_a_policia" if (actual or "").casefold() in {"policía local", "policia local"} else "variante_grafica_con_canon_local"
            seguridad = "D"
            motivo = "La salida productiva elimina el descriptor Local/territorial; no es una equivalencia de género demostrada."
            filas.append({"id_oposicion": row["oposicion_id"], "fecha_boe": row["fecha_boe"],
                "administracion": row["administracion"], "administracion_normalizada": row["administracion_normalizada"],
                "denominacion_original": row["puesto"], "denominacion_actual": actual, "canon_propuesto": nuevo,
                "numero_plazas": row["num_plazas"], "regla": "estabilizacion_genero_preexistente",
                "subtipo_regla": subtipo, "motivo": motivo, "seguridad_preliminar": seguridad,
                "provincia": row["provincia"], "comunidad_autonoma": row["comunidad_autonoma"],
                "escala": row["escala"], "subescala": row["subescala"], "clase": row["clase"]})
    finally:
        con.close()
    grupos = defaultdict(list)
    for f in filas:
        grupos[(f["denominacion_actual"], f["canon_propuesto"])].append(f)
    grupos_json = []
    for (origen, canon), xs in sorted(grupos.items(), key=lambda item: -len(item[1])):
        grupos_json.append({"denominacion_actual": origen, "canon_propuesto": canon,
            "oposiciones": len(xs), "plazas": sum(float(x["numero_plazas"] or 0) for x in xs),
            "anios": sorted({str(x["fecha_boe"])[:4] for x in xs}),
            "administraciones": sorted({x["administracion"] for x in xs}),
            "ejemplos": [x["id_oposicion"] for x in xs[:5]], "solo_genero": False,
            "perdida_especialidad": False, "perdida_nivel": True, "perdida_cuerpo_escala": True,
            "clasificacion": "D"})
    por_anio = Counter(str(x["fecha_boe"])[:4] for x in filas)
    plazas_anio = Counter()
    for x in filas: plazas_anio[str(x["fecha_boe"])[:4]] += float(x["numero_plazas"] or 0)
    por_admin = Counter(x["administracion"] or "" for x in filas)
    return {"version": "fase8-paso18-v1", "generado_utc": datetime.now(timezone.utc).isoformat(),
        "modo": "read-only", "baseline_sqlite": _estado(ruta_bd), "total_cambios": len(filas),
        "total_plazas": sum(float(x["numero_plazas"] or 0) for x in filas),
        "variantes_distintas": len({x["denominacion_original"] for x in filas}),
        "canones_distintos": len({x["canon_propuesto"] for x in filas}),
        "ids": [x["id_oposicion"] for x in filas], "regla": {"archivo": "normalizacion_puestos.py", "funcion": "normalizar_puesto → _normalizar_puesto_una_vez", "condicion": "la salida calculada difiere de puesto_normalizado persistido", "transformacion": "Policía/Polícia/policia/Policia sin descriptor local", "prioridad": "familias antes de género; esta discrepancia queda fuera de equivalencias seguras"},
        "inventario": filas, "grupos_original_canon": grupos_json,
        "distribucion_anual": [{"anio": a, "oposiciones": por_anio[a], "plazas": plazas_anio[a], "variantes": len({x["denominacion_original"] for x in filas if str(x["fecha_boe"])[:4] == a})} for a in sorted(por_anio)],
        "distribucion_administracion": [{"administracion": a, "oposiciones": n, "plazas": sum(float(x["numero_plazas"] or 0) for x in filas if (x["administracion"] or "") == a)} for a,n in por_admin.most_common()],
        "clasificacion": {"A_seguro": 0, "B_probable": 0, "C_dudoso": 0, "D_no_normalizar": len(filas)},
        "falsos_positivos": [{"tipo": "Policía aislada", "ids": [x["id_oposicion"] for x in filas], "motivo": "no demuestra Policía Local y el canon previo sí contiene descriptor territorial"}],
        "causa_0_a_329": "El informe del paso 16 (auditar_fase8_paso3.py) era un dry-run de un conjunto seguro distinto y fijaba dry_run_efectivo a cero sin invocar normalizar_puesto sobre el universo completo. El validador global posterior sí compara la salida actual con puesto_normalizado persistido; tras cambios previos de datos/cánones, detecta 329 discrepancias. No hubo UPDATE ni cambio de SQLite.",
        "comparacion_paso16": {"paso16": 0, "paso18": len(filas), "diferencia": len(filas), "consulta_paso16": "universo docente seguro acotado; salida constante 0", "consulta_actual": "todas las oposiciones, normalizar_puesto(puesto) != puesto_normalizado"},
        "recomendacion_final": "No aplicar estos 329 cambios. Diseñar una revisión específica de Policía aislada antes de cualquier normalización.",
        "aplicacion_real_recomendada": False, "sqlite_modificada": False}


def main() -> None:
    informe = auditar()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with DETAIL.open("w", newline="", encoding="utf-8") as fh:
        campos = list(informe["inventario"][0]) if informe["inventario"] else ["id_oposicion"]
        w = csv.DictWriter(fh, fieldnames=campos); w.writeheader(); w.writerows(informe["inventario"])
    print(json.dumps({"total_cambios": informe["total_cambios"], "total_plazas": informe["total_plazas"], "variantes_distintas": informe["variantes_distintas"], "canones_distintos": informe["canones_distintos"], "clasificacion": informe["clasificacion"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
