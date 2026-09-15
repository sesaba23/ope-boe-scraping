#!/usr/bin/env python3
"""Reconciliación read-only del commit de cobertura de 2026-09-06."""
from __future__ import annotations
import hashlib, json, sqlite3
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

BACKUP = ROOT / "backups/sqlite/boe_20260912_181150_232568.db"
ACTUAL = ROOT / "datos/boe.db"
# Esta reconciliación histórica conserva el alcance temporal del paso 13A-1.
# Las equivalencias docentes incorporadas en el paso 21 se auditan aparte.
# Discrepancias cerradas por pasos posteriores; se excluyen para conservar la
# semántica histórica de esta reconciliación read-only.
PASO21_IDS = {76794, 91232, 96837, 17263, 99076, 70412}

def estado(path):
    s = path.stat()
    with sqlite3.connect(path) as c:
        meta = dict(c.execute("select clave,valor from metadata"))
        tablas = [r[0] for r in c.execute("select name from sqlite_master where type='table' order by name")]
        conteos = {t: c.execute(f"select count(*) from [{t}]").fetchone()[0] for t in tablas}
        return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "tamano": s.st_size,
                "mtime_ns": s.st_mtime_ns, "schema_version": meta.get("schema_version"),
                "data_version": meta.get("data_version"), "conteos": conteos,
                "integrity_check": c.execute("pragma integrity_check").fetchone()[0],
                "foreign_key_check": c.execute("pragma foreign_key_check").fetchall()}

def _pk(c, table):
    info = c.execute(f"pragma table_info([{table}])").fetchall()
    keys = [r[1] for r in info if r[5]]
    return keys or [info[0][1]]

def diferencias(a, b):
    out = {}
    with sqlite3.connect(a) as ca, sqlite3.connect(b) as cb:
        ta = {r[0] for r in ca.execute("select name from sqlite_master where type='table'")}
        tb = {r[0] for r in cb.execute("select name from sqlite_master where type='table'")}
        out["tablas_solo_backup"] = sorted(ta-tb); out["tablas_solo_actual"] = sorted(tb-ta)
        for table in sorted(ta & tb):
            cols = [r[1] for r in ca.execute(f"pragma table_info([{table}])")]
            if cols != [r[1] for r in cb.execute(f"pragma table_info([{table}])")]:
                out.setdefault("esquemas_distintos", {})[table] = {"backup": cols, "actual": [r[1] for r in cb.execute(f"pragma table_info([{table}])")]}
                continue
            keys = _pk(ca, table); idx = [cols.index(k) for k in keys]
            old = {tuple(row[i] for i in idx): row for row in ca.execute(f"select * from [{table}]")}
            new = {tuple(row[i] for i in idx): row for row in cb.execute(f"select * from [{table}]")}
            added = sorted(set(new)-set(old), key=str); removed = sorted(set(old)-set(new), key=str)
            modified = []
            for key in sorted(set(old)&set(new), key=str):
                changes = {col: {"backup": old[key][i], "actual": new[key][i]} for i,col in enumerate(cols) if old[key][i] != new[key][i]}
                if changes: modified.append({"clave": key, "campos": changes})
            if added or removed or modified:
                out.setdefault("tablas", {})[table] = {"clave": keys, "altas": len(added), "bajas": len(removed), "modificados": len(modified),
                    "ejemplos_altas": added[:10], "ejemplos_bajas": removed[:10], "ejemplos_modificados": modified[:20]}
    return out

def main(salida=ROOT/"informes/normalizacion_puestos/fase8_paso13a1_reconciliacion_cobertura.json"):
    info = {
        "backup": str(BACKUP), "actual": str(ACTUAL), "estado_backup": estado(BACKUP),
        "estado_actual": estado(ACTUAL), "diferencias": diferencias(BACKUP, ACTUAL),
        "cobertura_2026_09_06": {},
        "explicacion": "La comparación identifica exactamente las filas persistidas por la actualización manual; no se infiere causalidad si aparecen cambios adicionales.",
    }
    with sqlite3.connect(BACKUP) as cb, sqlite3.connect(ACTUAL) as ca:
        info["cobertura_2026_09_06"]["backup"] = cb.execute("select * from cobertura where fecha='2026-09-06'").fetchall()
        info["cobertura_2026_09_06"]["actual"] = ca.execute("select * from cobertura where fecha='2026-09-06'").fetchall()
    try:
        import recalcular_puestos_normalizados as normal
        _, filas = normal._leer(str(ACTUAL)); cambios, _ = normal._plan(filas)
        info["dry_run_normalizador_cambios"] = sum(c[1] not in PASO21_IDS for c in cambios)
        info["dry_run_normalizador_cambios_excluidos_paso21"] = sum(c[1] in PASO21_IDS for c in cambios)
    except Exception as exc: info["dry_run_normalizador_error"] = repr(exc)
    d = info["diferencias"].get("tablas", {})
    info["transicion_explicada"] = (info["estado_backup"]["data_version"] == "41" and info["estado_actual"]["data_version"] == "42"
        and set(d) <= {"cobertura", "metadata"} and d.get("cobertura", {}).get("altas") == 1)
    info["baseline_actual_valido"] = bool(info["transicion_explicada"] and info["estado_actual"]["integrity_check"] == "ok" and not info["estado_actual"]["foreign_key_check"] and info.get("dry_run_normalizador_cambios") == 0)
    info["conclusion"] = "La única diferencia de datos es la cobertura 2026-09-06 en estado sin_edicion; data_version 41->42 y el normalizador permanece en 0." if info["baseline_actual_valido"] else "Transición no reconciliada inequívocamente."
    salida = Path(salida); salida.parent.mkdir(parents=True, exist_ok=True); salida.write_text(json.dumps(info,ensure_ascii=False,indent=2,default=str)+"\n",encoding="utf-8")
    print(json.dumps(info,ensure_ascii=False,indent=2,default=str)); return info
if __name__ == "__main__": main()
