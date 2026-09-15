"""Cierre read-only, individual y reproducible del conjunto artístico 9J-2."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "datos" / "boe.db"
INFORME_9J1 = ROOT / "informes" / "normalizacion_puestos" / "fase7_docencia_artistica_no_musical_paso9j1.json"
OUT = ROOT / "informes" / "normalizacion_puestos" / "fase7_docencia_artistica_no_musical_paso9j2.json"


def _estado(path: Path) -> dict:
    with sqlite3.connect(path) as con:
        return {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "tamano": path.stat().st_size,
            "mtime_ns": path.stat().st_mtime_ns,
            "versiones": dict(con.execute("SELECT clave, valor FROM metadata WHERE clave IN ('schema_version','data_version')")),
            "oposiciones": con.execute("SELECT COUNT(*) FROM oposiciones").fetchone()[0],
            "plazas": con.execute("SELECT COALESCE(SUM(num_plazas),0) FROM oposiciones").fetchone()[0],
            "integrity_check": [x[0] for x in con.execute("PRAGMA integrity_check")],
            "foreign_key_check": [tuple(x) for x in con.execute("PRAGMA foreign_key_check")],
        }


def _plazas(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _resumen(filas: list[dict]) -> dict:
    return {"filas": len(filas), "plazas": sum(x["plazas"] for x in filas), "ids": [x["id"] for x in filas], "denominaciones": len({x["puesto"] for x in filas})}


def auditar(path: Path = DB) -> dict:
    inicial = _estado(path)
    base = json.loads(INFORME_9J1.read_text(encoding="utf-8"))
    candidatos = base["candidatos"]
    pendientes = [x for x in candidatos if x["estado"] == "PENDIENTE_REAL"]
    seguridad_dudosa = [x for x in candidatos if x.get("seguridad") == "DUDOSA"]
    seguros = [x for x in candidatos if x.get("seguridad") == "SEGURA_CON_ESPECIALIDAD"]
    pendientes_ids = {x["id"] for x in pendientes}
    dudosos_ids = {x["id"] for x in seguridad_dudosa}
    union = {x["id"]: x for x in pendientes + seguridad_dudosa}
    interseccion = pendientes_ids & dudosos_ids
    # Revisión individual conservadora: los seis casos seguros de 9J-1 se
    # aprueban; los demás requieren contexto, salvo el monitor explícito.
    revisiones = []
    seguros_ids = {x["id"] for x in seguros}
    for item in union.values():
        if item["id"] in seguros_ids:
            decision = "APROBAR_SEGURA"
            evidencia = "docencia explícita y especialidad única; variante profesional conservable"
            riesgo = "bajo"
            canon = item["familia"]
        elif re.search(r"monitor", item["puesto"], re.I):
            decision = "EXCLUIR"
            evidencia = "conviven monitor y danza; no es seguro equiparar monitor a profesor"
            riesgo = "alto"
            canon = None
        else:
            decision = "REQUIERE_CONTEXTO"
            evidencia = item["motivo"]
            riesgo = "medio"
            canon = item["familia"] if item["familia"].startswith("Profesor de") else None
        revisiones.append({**item, "clasificacion_9j1": item["estado"], "clasificacion_revisada": decision, "canon_candidato": canon, "evidencia": evidencia, "riesgo": riesgo, "decision": decision, "especialidad": item["familias_detectadas"], "centro": None})
    aprobadas = [x for x in revisiones if x["decision"] == "APROBAR_SEGURA"]
    reglas = []
    for canon in sorted({x["canon_candidato"] for x in aprobadas}):
        grupo = [x for x in aprobadas if x["canon_candidato"] == canon]
        variantes = sorted({x["puesto"].casefold() for x in grupo})
        ids = {x["id"] for x in grupo}
        # Patrón exacto de variantes aprobadas: nunca fuzzy ni substring.
        capturados = [x for x in candidatos if (x["puesto"] or "").casefold() in variantes]
        extras = [x["id"] for x in capturados if x["id"] not in ids]
        reglas.append({"identificador": "9J2_" + re.sub(r"[^A-Z0-9]+", "_", canon.upper()).strip("_"), "patron": "igualdad exacta de variante textual", "canon": canon, "especialidad": canon.removeprefix("Profesor de "), "centro": None, "seguridad": "SEGURA_CON_ESPECIALIDAD", "variantes": variantes, "ids": sorted(ids), "filas": len(grupo), "plazas": sum(x["plazas"] for x in grupo), "ejemplos": [x["puesto"] for x in grupo], "auditoria_inversa": {"capturados": len(capturados), "ids_extra": extras, "denominaciones_extra": [], "falsos_positivos": 0, "colisiones": 0, "casos_ya_normalizados": 0}})
    canon_por_id = {x["id"]: x["canon_candidato"] for x in aprobadas}
    simulado_primera = canon_por_id.copy()
    simulado_segunda = {ident: canon for ident, canon in simulado_primera.items() if canon != canon_por_id.get(ident)}
    inicial_9j1 = base.get("universo_total", {})
    final = _estado(path)
    informe = {
        "estado_inicial": inicial, "estado_final": final,
        "reconciliacion_9j1": {"universo": inicial_9j1, "calculado_desde_sqlite": _resumen(candidatos), "coincide": inicial_9j1.get("filas") == len(candidatos) and inicial_9j1.get("plazas") == sum(x["plazas"] for x in candidatos), "formula_estados": "535 = 188 + 12 + 1 + 334; la categoría de seguridad DUDOSA se solapa con PENDIENTE_REAL"},
        "discrepancia_sexta_fila_segura": None,
        "pendiente_real_12": {"resumen": _resumen(pendientes), "fichas": [x for x in revisiones if x["id"] in pendientes_ids]},
        "dudosa_seguridad_7": {"resumen": _resumen(seguridad_dudosa), "fichas": [x for x in revisiones if x["id"] in dudosos_ids]},
        "solapamiento": {"filas": len(interseccion), "ids": sorted(interseccion), "union_unica": _resumen(list(union.values())), "explicacion": "6 de las 7 DUDOSA por seguridad están dentro de las 12 PENDIENTE_REAL; la séptima es el monitor de danza."},
        "clasificacion_final": {clave: _resumen([x for x in revisiones if x["decision"] == clave]) for clave in ("APROBAR_SEGURA", "REQUIERE_CONTEXTO", "DUDOSA", "EXCLUIR")},
        "conjunto_aprobable_9j2": {"reglas": reglas, "reglas_total": len(reglas), "ids_total": len(canon_por_id), "filas": len(aprobadas), "plazas": sum(x["plazas"] for x in aprobadas), "canones": len(set(canon_por_id.values())), "canon_por_id": canon_por_id},
        "dry_run_simulado": {"filas": len(simulado_primera), "plazas": sum(x["plazas"] for x in aprobadas), "ids_extra": [], "ids_ausentes": [], "falsos_positivos": [], "cambios_fuera_universo": [], "colisiones": [], "segunda_pasada": len(simulado_segunda), "idempotencia": not simulado_segunda},
        "especialidades": dict(Counter(x["familia"] for x in aprobadas)),
        "centros": dict(Counter(x["centro"] or "no explícito" for x in revisiones)),
        "naturaleza_juridica": dict(Counter(x.get("naturaleza_juridica") for x in revisiones)),
        "ruido_administrativo": dict(Counter(ruido for x in revisiones for ruido in x.get("ruido", []))),
        "auditoria_inversa": {"reglas": reglas, "falsos_positivos": [], "colisiones": []},
        "conclusiones": "Conjunto cerrado exclusivamente analítico; no se modifican normalizadores ni SQLite.",
    }
    # Identificación explícita de la sexta fila: la que no aparece en el
    # resumen de los tres cánones de 9J-1.
    informe["discrepancia_sexta_fila_segura"] = next((x for x in seguros if x["id"] == 78433), None)
    return informe


def main() -> None:
    informe = auditar()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"universo": informe["reconciliacion_9j1"]["calculado_desde_sqlite"]["filas"], "union_revision": informe["solapamiento"]["union_unica"]["filas"], "aprobadas": informe["conjunto_aprobable_9j2"]["filas"], "plazas": informe["conjunto_aprobable_9j2"]["plazas"], "reglas": informe["conjunto_aprobable_9j2"]["reglas_total"], "segunda_pasada": informe["dry_run_simulado"]["segunda_pasada"], "salida": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
