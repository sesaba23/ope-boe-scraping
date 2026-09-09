"""Auditoría read-only de familias de puestos para futura normalización segura."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import time

from normalizacion_puestos import clasificar_familia_puesto


CANONES = {"policia_local": "Policía Local", "auxiliar_administrativo": "Auxiliar Administrativo", "administrativo": "Administrativo"}


def clasificar_puesto(puesto):
    """Alias de auditoría para la clasificación productiva compartida."""
    return clasificar_familia_puesto(puesto)


def _filas(con):
    cursor = con.execute("SELECT oposicion_id, puesto, puesto_normalizado FROM oposiciones")
    return [dict(zip(("oposicion_id", "puesto", "puesto_normalizado"), fila)) for fila in cursor]


def auditar(ruta_bd="datos/boe.db", *, limite_variantes=100, limite_ejemplos=10):
    """Audita en una única lectura de oposiciones mediante SQLite mode=ro."""
    inicio = time.perf_counter(); ruta = Path(ruta_bd).resolve()
    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        filas = _filas(con)
    finally:
        con.close()
    familias = {nombre: {"filas": 0, "denominaciones": set(), "clases": Counter(), "correctas": 0, "modificables": 0, "variantes": Counter(), "ejemplos": defaultdict(list)} for nombre in CANONES}
    por_original = defaultdict(Counter)
    vacios = Counter()
    for fila in filas:
        actual = fila["puesto_normalizado"]
        vacios["null" if actual is None else "vacio" if not str(actual).strip() else "informado"] += 1
        por_original[fila["puesto"]][actual] += 1
        familia, clase, propuesto, motivo = clasificar_puesto(fila["puesto"])
        if not familia:
            continue
        destino = familias[familia]; destino["filas"] += 1; destino["denominaciones"].add(fila["puesto"])
        destino["clases"][clase] += 1; destino["variantes"][(fila["puesto"], actual, clase, propuesto, motivo)] += 1
        if clase == "alta_confianza":
            if actual == propuesto:
                destino["correctas"] += 1
            else:
                destino["modificables"] += 1
        if len(destino["ejemplos"][clase]) < limite_ejemplos:
            destino["ejemplos"][clase].append({"oposicion_id": fila["oposicion_id"], "puesto": fila["puesto"], "puesto_normalizado_actual": actual, "propuesto": propuesto, "motivo": motivo})
    salida = {}
    for nombre, datos in familias.items():
        salida[nombre] = {
            "canon_propuesto": CANONES[nombre], "convocatorias": datos["filas"],
            "denominaciones_originales_distintas": len(datos["denominaciones"]), "clasificacion": dict(datos["clases"]),
            "ya_correctamente_normalizadas": datos["correctas"], "potencialmente_modificables": datos["modificables"],
            "variantes_frecuentes": [
                {"puesto": k[0], "puesto_normalizado_actual": k[1], "clasificacion": k[2], "propuesto": k[3], "motivo": k[4], "registros": n}
                for k, n in datos["variantes"].most_common(limite_variantes)
            ], "ejemplos": dict(datos["ejemplos"]),
        }
    inconsistentes = [{"puesto": puesto, "normalizaciones_actuales": {str(k): n for k, n in valores.items()}, "registros": sum(valores.values())}
                       for puesto, valores in por_original.items() if len(valores) > 1]
    return {"version": "fase4-paso1-v1", "generado_utc": datetime.now(timezone.utc).isoformat(), "base_datos": str(ruta),
            "total_oposiciones": len(filas), "puesto_normalizado": dict(vacios), "familias": salida,
            "inconsistencias_mismo_puesto": sorted(inconsistentes, key=lambda x: -x["registros"]),
            "potencialmente_modificables_total": sum(x["potencialmente_modificables"] for x in salida.values()),
            "rendimiento_segundos": round(time.perf_counter()-inicio, 3)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bd", "--base-datos", dest="ruta_bd", default="datos/boe.db")
    parser.add_argument("--salida", default="informes/normalizacion_puestos_auditoria.json")
    args = parser.parse_args(argv)
    informe = auditar(args.ruta_bd); salida = Path(args.salida); salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"total_oposiciones": informe["total_oposiciones"], "familias": {k: v["clasificacion"] for k, v in informe["familias"].items()}, "rendimiento_segundos": informe["rendimiento_segundos"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
