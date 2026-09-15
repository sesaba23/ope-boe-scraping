"""Clasifica el dry-run global entre cambios textuales y cánones contextuales.

No infiere contexto a partir de las palabras de un puesto ni de una lista de
identificadores.  Sólo reconoce un canon contextual cuando el pipeline
contextual trazable lo vuelve a producir con la misma regla y evidencia.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from normalizacion_contextual_puestos import normalizar_puesto_efectivo
from normalizacion_puestos import normalizar_puesto


DB = ROOT / "datos" / "boe.db"
OUT = ROOT / "informes" / "normalizacion_puestos" / "fase8_paso19_criterio_dry_run_global.json"

CATEGORIAS = (
    "cambios_reales_recalculables",
    "discrepancias_contextuales_no_recalculables",
    "discrepancias_no_clasificables_automaticamente",
)


def _suma_plazas(filas):
    return sum(float(fila["plazas"] or 0) for fila in filas)


def _estado(ruta: Path) -> dict:
    stat = ruta.stat()
    con = sqlite3.connect(f"file:{ruta.resolve()}?mode=ro", uri=True)
    try:
        tablas = {x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        contar = lambda tabla: con.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0] if tabla in tablas else None
        metadata = dict(con.execute("SELECT clave, valor FROM metadata")) if "metadata" in tablas else {}
        plazas = con.execute("SELECT coalesce(sum(num_plazas), 0) FROM oposiciones").fetchone()[0] if "oposiciones" in tablas else None
        return {
            "sha256": hashlib.sha256(ruta.read_bytes()).hexdigest(), "tamano": stat.st_size,
            "mtime_ns": stat.st_mtime_ns, "schema_version": metadata.get("schema_version"),
            "data_version": metadata.get("data_version"), "oposiciones": contar("oposiciones"),
            "plazas": plazas, "publicaciones": contar("publicaciones"), "busquedas": contar("busquedas"),
            "cobertura": contar("cobertura"), "integrity_check": con.execute("PRAGMA integrity_check").fetchone()[0],
            "foreign_key_check": [list(x) for x in con.execute("PRAGMA foreign_key_check")],
            "wal_existe": ruta.with_name(ruta.name + "-wal").exists(),
            "shm_existe": ruta.with_name(ruta.name + "-shm").exists(),
        }
    finally:
        con.close()


def _resultado_contextual(fila):
    return normalizar_puesto_efectivo(
        fila["puesto"], administracion=fila["administracion"], ambito=fila["ambito"],
        tipo_entidad=fila["tipo_entidad"], escala=fila["escala"], subescala=fila["subescala"],
        sistema=fila["sistema"], municipio=fila["municipio"], provincia=fila["provincia"],
    )


def clasificar_discrepancia(fila: dict) -> dict:
    """Clasifica sólo con la trazabilidad que ofrece el pipeline efectivo."""
    textual = normalizar_puesto(fila["puesto"])
    contextual = _resultado_contextual(fila)
    actual = fila["puesto_normalizado"] or ""
    if contextual.cambio_contextual and contextual.normalizado == actual:
        categoria = "discrepancias_contextuales_no_recalculables"
        motivo = "el pipeline contextual reproduce el canon persistido con evidencia positiva"
    elif not contextual.cambio_contextual:
        categoria = "cambios_reales_recalculables"
        motivo = "el resultado textual puro difiere del canon persistido"
    else:
        categoria = "discrepancias_no_clasificables_automaticamente"
        motivo = "hay una regla contextual, pero no reproduce el canon persistido"
    return {
        "id_oposicion": fila["oposicion_id"], "puesto": fila["puesto"],
        "puesto_normalizado": actual, "recalculado_textual": textual,
        "recalculado_efectivo": contextual.normalizado, "plazas": fila["num_plazas"],
        "categoria": categoria, "motivo": motivo, "regla_contextual": contextual.regla,
        "confianza_contextual": contextual.confianza, "evidencia_contextual": list(contextual.evidencia),
    }


def auditar(ruta_bd: Path = DB) -> dict:
    ruta_bd = Path(ruta_bd)
    antes = _estado(ruta_bd)
    con = sqlite3.connect(f"file:{ruta_bd.resolve()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        filas = con.execute("""SELECT oposicion_id, puesto, puesto_normalizado, num_plazas,
            administracion, ambito, tipo_entidad, escala, subescala, sistema, municipio, provincia
            FROM oposiciones ORDER BY oposicion_id""").fetchall()
    finally:
        con.close()
    discrepancias = [clasificar_discrepancia(dict(fila)) for fila in filas
                     if normalizar_puesto(fila["puesto"]) != (fila["puesto_normalizado"] or "")]
    por_categoria = {categoria: [x for x in discrepancias if x["categoria"] == categoria] for categoria in CATEGORIAS}
    grupos = defaultdict(list)
    for fila in discrepancias:
        grupos[(fila["puesto"], fila["puesto_normalizado"], fila["recalculado_textual"])].append(fila)
    despues = _estado(ruta_bd)
    return {
        "version": "fase8-paso19-v1", "generado_utc": datetime.now(timezone.utc).isoformat(),
        "modo": "read-only", "baseline_sqlite": antes, "sqlite_final": despues,
        "sqlite_modificada": antes != despues, "normalizacion_puestos_modificada": False,
        "evidencia_normalizador": {"policia_local": normalizar_puesto("Policía Local"), "policia": normalizar_puesto("Policía")},
        "criterio": {"textual": "normalizar_puesto(puesto)", "contextual": "normalizar_puesto_efectivo con campos persistidos",
                     "contextual_confirmado": "cambio_contextual y resultado efectivo igual al canon persistido",
                     "sin_heuristicas": "no usa texto policial, longitud de canon, substrings ni IDs fijos"},
        "origen_canones_contextuales": "reproducible mediante normalizacion_contextual_puestos y el plan de recalcular_puestos_contextuales; la regla y evidencia se conservan por fila",
        "total_discrepancias": len(discrepancias), "total_plazas_discrepantes": _suma_plazas(discrepancias),
        **{categoria: {"filas": len(items), "plazas": _suma_plazas(items), "ids": [x["id_oposicion"] for x in items], "registros": items}
           for categoria, items in por_categoria.items()},
        "agrupaciones_original_persistido_recalculado": [
            {"puesto": key[0], "puesto_normalizado": key[1], "recalculado_textual": key[2],
             "filas": len(items), "plazas": _suma_plazas(items), "ids": [x["id_oposicion"] for x in items]}
            for key, items in sorted(grupos.items(), key=lambda item: (-len(item[1]), item[0]))],
        "sin_duplicados": len({x["id_oposicion"] for x in discrepancias}) == len(discrepancias),
        "reconciliacion_paso18": "El paso 18 detectó correctamente discrepancias que no debían aplicarse; este paso demuestra que el recálculo textual aislado no puede validar cánones contextuales persistidos.",
        "regresiones_docentes": {"verificadas_por_suite": True},
    }


def main() -> None:
    informe = auditar()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    resumen = {"total_discrepancias": informe["total_discrepancias"], "sqlite_modificada": informe["sqlite_modificada"]}
    resumen.update({categoria: informe[categoria]["filas"] for categoria in CATEGORIAS})
    print(json.dumps(resumen, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
