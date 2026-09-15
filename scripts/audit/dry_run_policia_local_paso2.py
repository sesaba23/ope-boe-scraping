"""Dry-run read-only de las reglas productivas de Policía Local de Fase 7."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from normalizacion_puestos import (
    CATEGORIAS_POLICIA_LOCAL,
    EXCLUSIONES_POLICIA_LOCAL,
    normalizar_puesto,
)


def _estado(ruta):
    stat = ruta.stat()
    with sqlite3.connect(f"file:{ruta}?mode=ro", uri=True) as con:
        metadata = dict(con.execute("SELECT clave, valor FROM metadata WHERE clave IN ('schema_version', 'data_version')"))
        total, plazas = con.execute("SELECT COUNT(*), COALESCE(SUM(num_plazas), 0) FROM oposiciones").fetchone()
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
    return {"sha256": hashlib.sha256(ruta.read_bytes()).hexdigest(), "tamano": stat.st_size,
            "mtime_ns": stat.st_mtime_ns, "schema_version": int(metadata["schema_version"]),
            "data_version": int(metadata["data_version"]), "oposiciones": total, "plazas": plazas,
            "integrity_check": integrity, "foreign_key_check": fk,
            "wal_existe": ruta.with_name(ruta.name + "-wal").exists(), "shm_existe": ruta.with_name(ruta.name + "-shm").exists()}


def ejecutar(ruta_bd="datos/boe.db", ruta_auditoria="informes/normalizacion_puestos/fase7_policia_local_auditoria.json"):
    ruta = Path(ruta_bd).resolve(); estado_inicial = _estado(ruta)
    auditoria = json.loads(Path(ruta_auditoria).read_text(encoding="utf-8"))
    por_puesto = {fila["puesto"]: fila for fila in auditoria["variantes"]}
    esperadas = auditoria["dry_run"]["filas_que_cambiarian_seguras_textuales"]
    cambios = defaultdict(list); por_categoria = Counter(); no_cambian_seguras = []
    with sqlite3.connect(f"file:{ruta}?mode=ro", uri=True) as con:
        con.row_factory = sqlite3.Row
        filas = con.execute("SELECT oposicion_id, puesto, puesto_normalizado FROM oposiciones").fetchall()
    for fila in filas:
        actual = fila["puesto_normalizado"]; propuesto = normalizar_puesto(fila["puesto"])
        previo = por_puesto.get(fila["puesto"])
        clase = previo["clasificacion"] if previo else "FUERA_UNIVERSO"
        categoria = previo["categoria_detectada"] if previo else None
        if actual != propuesto:
            cambios[clase].append({"oposicion_id": fila["oposicion_id"], "puesto": fila["puesto"], "puesto_normalizado_actual": actual, "propuesto": propuesto, "categoria": categoria})
            if clase == "SEGURA_TEXTUAL":
                por_categoria[categoria or "Sin categoría"] += 1
        elif clase == "SEGURA_TEXTUAL" and actual != previo["normalizacion_propuesta"]:
            no_cambian_seguras.append({"oposicion_id": fila["oposicion_id"], "puesto": fila["puesto"], "actual": actual, "esperado": previo["normalizacion_propuesta"], "categoria": categoria})
    seguro = cambios["SEGURA_TEXTUAL"]
    divergencias = no_cambian_seguras + [x for x in seguro if x["propuesto"] != por_puesto[x["puesto"]]["normalizacion_propuesta"]]
    estado_final = _estado(ruta)
    return {
        "version": "fase7-paso2-dry-run-v1", "generado_utc": datetime.now(timezone.utc).isoformat(),
        "sqlite_inicial": estado_inicial, "sqlite_final": estado_final,
        "reglas": {"canones": ["Policía Local"] + [f"{nombre} de Policía Local" for nombre, _ in CATEGORIAS_POLICIA_LOCAL if nombre != "Agente"],
                   "exclusiones": EXCLUSIONES_POLICIA_LOCAL.pattern, "guardia_urbana": "sin normalizar", "policia_aislado": "sin normalizar"},
        "filas_examinadas": len(filas), "cambios": {clave: len(valor) for clave, valor in cambios.items()},
        "cambios_por_categoria_segura": dict(por_categoria), "seguras_previstas_paso1": esperadas,
        "seguras_que_cambian": len(seguro), "seguras_que_no_cambian": len(no_cambian_seguras),
        "dudosas_que_cambian": len(cambios["DUDOSA"]), "contextuales_que_cambian": len(cambios["SEGURA_CONTEXTUAL"]), "excluidas_que_cambian": len(cambios["EXCLUIDA"]),
        "fuera_universo_que_cambian": len(cambios["FUERA_UNIVERSO"]), "denominaciones_afectadas": len({x["puesto"] for grupo in cambios.values() for x in grupo}),
        "divergencias": divergencias[:100], "idempotencia_fallos": [x for grupo in cambios.values() for x in grupo if normalizar_puesto(x["propuesto"]) != x["propuesto"]][:100],
        "ejemplos": {clave: valor[:10] for clave, valor in cambios.items()},
        "conclusion": "apto" if not divergencias and not cambios["DUDOSA"] and not cambios["EXCLUIDA"] else "requiere_revision",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bd", default="datos/boe.db")
    parser.add_argument("--auditoria", default="informes/normalizacion_puestos/fase7_policia_local_auditoria.json")
    parser.add_argument("--salida", default="informes/normalizacion_puestos/fase7_policia_local_paso2_dry_run.json")
    args = parser.parse_args(argv); informe = ejecutar(args.bd, args.auditoria)
    salida = Path(args.salida); salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: informe[k] for k in ("filas_examinadas", "seguras_previstas_paso1", "seguras_que_cambian", "seguras_que_no_cambian", "dudosas_que_cambian", "contextuales_que_cambian", "excluidas_que_cambian", "fuera_universo_que_cambian", "conclusion")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
