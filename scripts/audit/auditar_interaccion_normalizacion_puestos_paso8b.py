"""Auditoría read-only de la composición textual y contextual de puestos."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from normalizacion_contextual_puestos import normalizar_puesto_contextual
from normalizacion_puestos import normalizar_puesto


def _estado(ruta):
    stat = ruta.stat()
    with sqlite3.connect(f"file:{ruta}?mode=ro", uri=True) as con:
        metadata = dict(con.execute("SELECT clave, valor FROM metadata"))
        oposiciones, plazas = con.execute(
            "SELECT COUNT(*), COALESCE(SUM(num_plazas), 0) FROM oposiciones"
        ).fetchone()
        return {
            "sha256": hashlib.sha256(ruta.read_bytes()).hexdigest(),
            "tamano": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "schema_version": metadata["schema_version"],
            "data_version": metadata["data_version"],
            "oposiciones": oposiciones,
            "plazas": plazas,
            "integrity_check": con.execute("PRAGMA integrity_check").fetchall(),
            "foreign_key_check": con.execute("PRAGMA foreign_key_check").fetchall(),
            "wal_existe": ruta.with_name(ruta.name + "-wal").exists(),
            "shm_existe": ruta.with_name(ruta.name + "-shm").exists(),
        }


def _contextual(fila):
    return normalizar_puesto_contextual(
        fila["puesto"], administracion=fila["administracion"], ambito=fila["ambito"],
        tipo_entidad=fila["tipo_entidad"], escala=fila["escala"],
        subescala=fila["subescala"], sistema=fila["sistema"],
        municipio=fila["municipio"], provincia=fila["provincia"],
    )


def ejecutar(ruta_bd="datos/boe.db", informe_paso6="informes/normalizacion_puestos/fase7_policia_contextual_paso6_aplicacion.json"):
    """Compone ambas capas sin escribir y compara contra el estado persistido."""
    ruta = Path(ruta_bd).resolve()
    inicial = _estado(ruta)
    with sqlite3.connect(f"file:{ruta}?mode=ro", uri=True) as con:
        con.row_factory = sqlite3.Row
        filas = con.execute("SELECT * FROM oposiciones ORDER BY oposicion_id").fetchall()

    diferencias_textuales = []
    diferencias_compuestas = []
    contextuales = []
    for fila in filas:
        textual = normalizar_puesto(fila["puesto"])
        resultado = _contextual(fila)
        entrada = {
            "oposicion_id": fila["oposicion_id"], "puesto": fila["puesto"],
            "puesto_normalizado_actual": fila["puesto_normalizado"], "textual": textual,
            "compuesto": resultado.normalizado, "regla_contextual": resultado.regla,
            "ambito": fila["ambito"], "administracion": fila["administracion"],
            "municipio": fila["municipio"], "provincia": fila["provincia"],
            "plazas": fila["num_plazas"],
        }
        if textual != fila["puesto_normalizado"]:
            diferencias_textuales.append(entrada)
        if resultado.normalizado != fila["puesto_normalizado"]:
            diferencias_compuestas.append(entrada)
        if resultado.regla:
            contextuales.append(entrada)

    previos = set()
    ruta_paso6 = Path(informe_paso6)
    if ruta_paso6.is_file():
        paso6 = json.loads(ruta_paso6.read_text(encoding="utf-8"))
        previos = {x["oposicion_id"] for x in paso6["aplicacion"]["propuestas"]}
    ids_contextuales = {x["oposicion_id"] for x in contextuales}
    filas_por_id = {fila["oposicion_id"]: fila for fila in filas}
    segunda_pasada = [
        x["oposicion_id"] for x in contextuales
        if _contextual(filas_por_id[x["oposicion_id"]]).normalizado != x["compuesto"]
    ]
    final = _estado(ruta)
    return {
        "generado_utc": datetime.now(timezone.utc).isoformat(),
        "sqlite_inicial": inicial, "sqlite_final": final,
        "diferencias_textuales": diferencias_textuales,
        "diferencias_compuestas": diferencias_compuestas,
        "contextuales_reconstruibles": contextuales,
        "resumen": {
            "textuales": len(diferencias_textuales),
            "contextuales": len(contextuales),
            "compuestas_pendientes": len(diferencias_compuestas),
            "textuales_por_destino": dict(Counter(x["textual"] for x in diferencias_textuales)),
            "contextuales_por_regla": dict(Counter(x["regla_contextual"] for x in contextuales)),
            "ids_contextuales_paso6_coinciden": ids_contextuales == previos if previos else None,
            "ids_contextuales_solo_actuales": sorted(ids_contextuales - previos),
            "ids_contextuales_ausentes": sorted(previos - ids_contextuales),
            "segunda_pasada_distinta": segunda_pasada,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bd", default="datos/boe.db")
    parser.add_argument("--informe-paso6", default="informes/normalizacion_puestos/fase7_policia_contextual_paso6_aplicacion.json")
    parser.add_argument("--salida", default="informes/normalizacion_puestos/fase7_interaccion_textual_contextual_paso8b.json")
    args = parser.parse_args(argv)
    informe = ejecutar(args.bd, args.informe_paso6)
    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(informe["resumen"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
