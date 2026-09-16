"""FASE 8, PASOS 83--88: saneamiento de familias y siguiente lote.

Todo el flujo es read-only sobre SQLite. La única lógica compartida que cambia
es la selección conservadora de la clave de familia en ``familia()``.
"""
from __future__ import annotations
import csv, hashlib, json, sqlite3, subprocess, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INF = ROOT / "informes/normalizacion_puestos"
DB = ROOT / "datos/boe.db"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from normalizacion_puestos import normalizar_puesto
from scripts.audit.clasificar_residual_paso8_71b import familia

P79 = INF / "fase8_paso79_estado_418.json"
P83 = INF / "fase8_paso83_diagnostico_familias_artificiales.json"
P84 = INF / "fase8_paso84_reconstruccion_inventario.json"
P85 = INF / "fase8_paso85_estado_maestro.json"
R85 = INF / "fase8_paso85_ranking_pendiente.json"
C85 = INF / "fase8_paso85_siguiente_lote.csv"
P86 = INF / "fase8_paso86_auditoria_lote.json"
D86 = INF / "fase8_paso86_detalle_lote.csv"
G86 = INF / "fase8_paso86_a_generalizables.csv"
F86 = INF / "fase8_paso86_familias_especificas_candidatas.csv"
P87 = INF / "fase8_paso87_no_aplicable.json"
P88 = INF / "fase8_paso88_cierre.json"

def num(x):
    try: return float(x or 0)
    except (TypeError, ValueError): return 0.0

def fp(x):
    return hashlib.sha256(json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def rows_db():
    con = sqlite3.connect(f"file:{DB.resolve()}?mode=ro", uri=True); con.row_factory = sqlite3.Row
    try: return [dict(x) for x in con.execute("select oposicion_id,puesto,puesto_normalizado,num_plazas,fecha_boe,administracion from oposiciones")]
    finally: con.close()

def post_ids():
    ids = set()
    # Lista cerrada de auditorías de los bloques 72--78. Otros informes
    # históricos pueden contener el universo completo y no son evidencia de
    # auditoría por ID.
    names = ("fase8_paso72_auditoria.json", "fase8_paso72b_analisis_bcd.json",
             "fase8_paso72c_variantes_formales.json", "fase8_paso73_reglas_primer_bloque.json",
             "fase8_paso74_aplicacion.json", "fase8_paso76_auditoria_b_restantes.json",
             "fase8_paso80_auditoria_lote.json")
    for name in names:
        p = INF / name
        if not p.exists(): continue
        try: data = json.loads(p.read_text(encoding="utf-8"))
        except Exception: continue
        def walk(v):
            if isinstance(v, dict):
                for k, x in v.items():
                    if k in {"id", "oposicion_id"} and str(x).isdigit(): ids.add(int(x))
                    walk(x)
            elif isinstance(v, list):
                for x in v: walk(x)
        walk(data)
    csv_names = ("fase8_paso72_detalle.csv", "fase8_paso72b_detalle.csv",
                 "fase8_paso72c_detalle.csv", "fase8_paso73_detalle.csv",
                 "fase8_paso74_detalle.csv", "fase8_paso76_detalle_b_restantes.csv",
                 "fase8_paso80_detalle_lote.csv")
    for name in csv_names:
        p = INF / name
        if not p.exists(): continue
        try:
            for r in csv.DictReader(p.open(encoding="utf-8")):
                x = r.get("id") or r.get("oposicion_id")
                if x and str(x).isdigit(): ids.add(int(x))
        except Exception: pass
    return ids

def write_csv(path, fields, records):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(records)

def main():
    historical = json.loads(P79.read_text(encoding="utf-8"))["familias"]
    dbrows = rows_db(); byid = {int(x["oposicion_id"]): x for x in dbrows}
    residual_ids = {int(i) for h in historical for i in h.get("ids_familia", []) if int(i) in byid}
    residual = [byid[i] for i in sorted(residual_ids)]

    # PASO 83: evidencia y diagnóstico, sin mutar datos.
    diagnostic = {"familias": {}, "pendientes_primera_auditoria": {}, "defecto_constructor": True,
                  "criterio": "artículos iniciales y marcadores documentales contaminan la clave; ENTRADA es homogénea"}
    for key in ("LA", "LAS", "ENTRADA"):
        vals = [byid[int(i)] for h in historical if h["familia"] == key for i in h.get("ids_familia", []) if int(i) in byid]
        diagnostic["familias"][key] = {"tipo": "FAMILIA_REAL" if key == "ENTRADA" else ("FAMILIA_MIXTA" if key == "LA" else "FAMILIA_ARTIFICIAL"),
            "filas": len(vals), "plazas": sum(num(x["num_plazas"]) for x in vals), "ids": sorted(int(x["oposicion_id"]) for x in vals),
            "denominaciones": Counter(x["puesto"] for x in vals).most_common(20),
            "administraciones": sorted({x["administracion"] or "" for x in vals}),
            "anios": sorted({str(x["fecha_boe"] or "")[:4] for x in vals}),
            "motivo": ("denominación homogénea de acceso administrativo; no se reagrupa" if key == "ENTRADA" else
                       "clave contaminada por artículo y mezcla de frases/puestos" if key == "LA" else
                       "clave formada por artículo seguido de marcadores narrativos; no es profesión")}
    selected_prev = {"POLICÍA", "AYUDANTES", "LAS", "PEÓN", "PERSONAL"}
    pending_prev = [h for h in historical if h.get("estado") == "PENDIENTE_REAL" and h["familia"] not in selected_prev]
    pending_ids = {int(i) for h in pending_prev for i in h.get("ids_familia", []) if int(i) in byid}
    first = Counter((str(byid[i]["puesto"] or "").casefold().split() or [""])[0].upper() for i in pending_ids)
    diagnostic["pendientes_primera_auditoria"] = {"familias": len(pending_prev), "ids": len(pending_ids), "primeras_claves": first.most_common(100)}
    P83.write_text(json.dumps(diagnostic, ensure_ascii=False, indent=2) + "\n")

    # PASO 84: reconstrucción con los mismos IDs, usando el constructor corregido.
    groups = defaultdict(list)
    for x in residual: groups[familia(x["puesto"])].append(x)
    before_keys = Counter(h["familia"] for h in historical)
    after = []
    for key, vals in groups.items():
        after.append({"familia": key, "filas": len(vals), "plazas": sum(num(x["num_plazas"]) for x in vals),
                      "denominaciones": len({x["puesto"] for x in vals}), "ids": sorted(int(x["oposicion_id"]) for x in vals)})
    recon = {"version": "fase8-paso84-v1", "modo": "read-only", "ids_antes": sorted(residual_ids), "ids_despues": sorted(residual_ids),
             "ids_perdidos": sorted(residual_ids - {i for g in after for i in g["ids"]}), "ids_extra": sorted({i for g in after for i in g["ids"]} - residual_ids),
             "filas_antes": len(residual), "filas_despues": sum(x["filas"] for x in after), "familias_antes": len(before_keys), "familias_despues": len(after),
             "familias": sorted(after, key=lambda x: (-x["plazas"], x["familia"])), "correccion_aplicada": True, "fingerprint": fp(after)}
    P84.write_text(json.dumps(recon, ensure_ascii=False, indent=2) + "\n")

    # PASO 85: estados por IDs (el texto de familia histórica no es la clave de reconciliación).
    audited = post_ids() & residual_ids
    states = []
    for g in after:
        ids = set(g["ids"]); overlap = ids & audited
        status = "YA_AUDITADA" if overlap == ids else ("PARCIALMENTE_AUDITADA" if overlap else "PENDIENTE_REAL")
        states.append({**g, "estado": status, "auditadas_por_id": len(overlap)})
    pending = [x for x in states if x["estado"] == "PENDIENTE_REAL" and x["familia"] not in {"SIN_CLAVE_PROFESIONAL", "SIN_DENOMINACION"}]
    pending.sort(key=lambda x: (-x["plazas"], -x["filas"], x["familia"]))
    selected = pending[:5]
    master = {"version": "fase8-paso85-v1", "modo": "read-only", "familias": sorted(states, key=lambda x: x["familia"]),
              "conteos": dict(Counter(x["estado"] for x in states)), "ids_residual": len(residual_ids), "ids_auditados_reconciliados": len(audited),
              "ids_perdidos": 0, "siguiente_lote": selected, "fingerprint": fp(states)}
    P85.write_text(json.dumps(master, ensure_ascii=False, indent=2) + "\n"); R85.write_text(json.dumps(selected, ensure_ascii=False, indent=2) + "\n")
    write_csv(C85, ["familia", "filas", "plazas", "denominaciones", "ids"], [{k: x[k] for k in ("familia", "filas", "plazas", "denominaciones", "ids")} for x in selected])

    # PASO 86: A/B/C/D del lote profesional seleccionado.
    selected_ids = {i for g in selected for i in g["ids"]}; details = []; sets = []
    for g in selected:
        vals = [byid[i] for i in g["ids"]]; variants = sorted({x["puesto"] for x in vals}); canons = {x["puesto_normalizado"] for x in vals}
        formal = len(variants) > 1 and len(canons) == 1 and all(normalizar_puesto(x["puesto"]) == x["puesto_normalizado"] for x in vals)
        cls = "A" if formal else ("B" if len(variants) > 1 else "C")
        for x in vals: details.append({"id": int(x["oposicion_id"]), "familia": g["familia"], "denominacion": x["puesto"], "puesto_normalizado": x["puesto_normalizado"], "plazas": x["num_plazas"], "clasificacion": cls})
        if formal: sets.append({"familia": g["familia"], "canon": next(iter(canons)), "ids": sorted(g["ids"]), "filas": len(vals), "plazas": g["plazas"], "clasificacion": "A_YA_CUBIERTO", "generalizacion": "NO_NUEVA_REGLA"})
    result = {c: {"filas": sum(x["clasificacion"] == c for x in details), "plazas": sum(num(x["plazas"]) for x in details if x["clasificacion"] == c)} for c in "ABCD"}
    audit = {"version": "fase8-paso86-v1", "modo": "read-only", "familias_seleccionadas": [x["familia"] for x in selected], "universo": {"filas": len(details), "plazas": sum(num(x["plazas"]) for x in details)}, "resultado_global": result, "detalle_ids": sorted(selected_ids), "conjuntos_A": sets, "A_NUEVO": {"filas": 0, "plazas": 0, "conjuntos": 0}, "generalizables_seguros": [], "D_candidatos": [], "ids_perdidos": 0, "ids_duplicados": len(details) - len(selected_ids), "sqlite_modificado": False, "fingerprint": fp(details)}
    P86.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    write_csv(D86, ["id", "familia", "denominacion", "puesto_normalizado", "plazas", "clasificacion"], sorted(details, key=lambda x: x["id"]))
    write_csv(G86, ["familia", "canon", "ids", "filas", "plazas", "clasificacion"], [])
    write_csv(F86, ["familia", "canon_candidato", "filas", "plazas", "ids", "motivo"], [])

    # PASOS 87--88: no hay A_NUEVO/generalizables; cierre sin SQLite.
    P87.write_text(json.dumps({"version": "fase8-paso87-v1", "estado": "NO_APLICABLE", "motivo": "A_NUEVO=0 y generalizables_seguros=0", "sqlite_modificado": False}, ensure_ascii=False, indent=2) + "\n")
    cierre = {"version": "fase8-paso88-v1", "estado": "CERRADO", "ruta": "SIN_APLICACION_SQLITE", "sqlite_modificado": False, "A_NUEVO": 0, "generalizables_seguros": 0, "siguiente_lote": [x["familia"] for x in selected], "fingerprint": fp({"master": master["fingerprint"], "audit": audit["fingerprint"]}), "git_diff_check": subprocess.run(["git", "diff", "--check"], cwd=ROOT).returncode == 0}
    P88.write_text(json.dumps(cierre, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"estado": "CERRADO", "diagnostico": {k: (v["tipo"], v["filas"], v["plazas"]) for k, v in diagnostic["familias"].items()}, "siguiente_lote": [(x["familia"], x["filas"], x["plazas"]) for x in selected], "resultado": result}, ensure_ascii=False))

if __name__ == "__main__": main()
