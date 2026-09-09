"""Valida en lectura el efecto del motor productivo de normalización de puestos."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from normalizacion_puestos import _clave, clasificar_familia_puesto, normalizar_puesto


def ejecutar_dry_run(ruta_bd="datos/boe.db", *, limite=20):
    inicio = time.perf_counter(); ruta = Path(ruta_bd).resolve()
    sha = hashlib.sha256(ruta.read_bytes()).hexdigest()
    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        metadata = dict(con.execute("SELECT clave,valor FROM metadata"))
        filas = con.execute("SELECT oposicion_id,puesto,puesto_normalizado FROM oposiciones").fetchall()
    finally:
        con.close()
    cambios = Counter(); cruces = Counter(); ejemplos = defaultdict(list); variantes = Counter(); causas_fuera = Counter(); idempotencia = 0
    for oid, puesto, actual in filas:
        familia, clase, canon, motivo = clasificar_familia_puesto(puesto)
        nuevo = normalizar_puesto(puesto)
        if normalizar_puesto(nuevo) != nuevo:
            idempotencia += 1
        cambio = nuevo != actual
        if familia and clase == "alta_confianza":
            cruce = "auditoria_segura_y_motor_cambia" if cambio else "ya_correcto" if actual == canon else "auditoria_segura_y_motor_no_cambia"
        elif cambio:
            cruce = "auditoria_no_segura_y_motor_cambia"
        else:
            cruce = "sin_cambio_fuera_objetivo"
        cruces[cruce] += 1
        if cambio:
            grupo = familia if familia and clase == "alta_confianza" else "fuera_objetivo"
            cambios[grupo] += 1
            if grupo == "fuera_objetivo":
                causa = (
                    "exclusion_titulacion_fase2_preservada"
                    if "ingeniera/o tecnic" in _clave(puesto or "")
                    else "estabilizacion_genero_preexistente"
                )
                causas_fuera[causa] += 1
            variantes[(grupo, puesto, actual, nuevo)] += 1
            if len(ejemplos[grupo]) < limite:
                ejemplos[grupo].append({"oposicion_id": oid, "puesto": puesto, "anterior": actual, "propuesto": nuevo, "motivo": motivo})
    return {
        "version": "fase4-paso2-v1", "generado_utc": datetime.now(timezone.utc).isoformat(), "dry_run": True,
        "base_datos": str(ruta), "sha256": sha, "schema_version": metadata.get("schema_version"), "data_version": metadata.get("data_version"),
        "total_analizado": len(filas), "cambios_totales": sum(cambios.values()), "cambios_por_familia": dict(cambios),
        "cambios_fuera_objetivo": cambios["fuera_objetivo"], "validacion_cruzada": {
            clave: cruces[clave] for clave in (
                "auditoria_segura_y_motor_cambia", "auditoria_segura_y_motor_no_cambia",
                "auditoria_no_segura_y_motor_cambia", "ya_correcto", "sin_cambio_fuera_objetivo",
            )},
        "idempotencia_fallos": idempotencia,
        "cambios_fuera_objetivo_por_causa": dict(causas_fuera),
        "variantes_frecuentes": [{"familia": k[0], "puesto": k[1], "anterior": k[2], "propuesto": k[3], "registros": n} for k, n in variantes.most_common(100)],
        "ejemplos": dict(ejemplos), "rendimiento_segundos": round(time.perf_counter()-inicio, 3),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bd", "--base-datos", dest="ruta_bd", default="datos/boe.db")
    parser.add_argument("--salida", default="informes/normalizacion_puestos_dry_run.json")
    args = parser.parse_args(argv)
    informe = ejecutar_dry_run(args.ruta_bd)
    salida = Path(args.salida); salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: informe[k] for k in ("total_analizado", "cambios_totales", "cambios_por_familia", "cambios_fuera_objetivo", "validacion_cruzada", "idempotencia_fallos", "rendimiento_segundos")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
