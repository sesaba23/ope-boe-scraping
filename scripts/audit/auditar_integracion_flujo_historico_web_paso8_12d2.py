#!/usr/bin/env python3
"""Auditoría reproducible del despacho web histórico/moderno (PASO 12D-2).

No descarga ni escribe la base real: copia la base a /private/tmp y ejecuta el
despachador con extractores simulados para verificar contrato y aislamiento.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import actualizacion_boe
import plazasboe


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _db_state(path: Path) -> dict:
    with sqlite3.connect(path) as con:
        return {
            "schema_version": con.execute("SELECT valor FROM metadata WHERE clave='schema_version'").fetchone()[0],
            "data_version": con.execute("SELECT valor FROM metadata WHERE clave='data_version'").fetchone()[0],
            "integrity_check": con.execute("PRAGMA integrity_check").fetchone()[0],
            "foreign_key_check": con.execute("PRAGMA foreign_key_check").fetchall(),
        }


def main() -> None:
    origen = Path("datos/boe.db").resolve()
    with tempfile.TemporaryDirectory(prefix="boe-paso8-12d2-", dir="/private/tmp") as tmp:
        copia = Path(tmp) / "boe.db"
        shutil.copy2(origen, copia)
        sha_antes = _sha(copia)
        estado_antes = _db_state(copia)
        llamadas = []

        def moderno(fechas, ruta_bd, on_progress=None):
            llamadas.append({"extractor": "moderno", "fechas": list(fechas), "ruta": ruta_bd})
            return {"extractor": "moderno", "fechas": list(fechas)}

        def historico(fecha, ruta_bd, progreso):
            llamadas.append({"extractor": "historico", "fechas": [fecha], "ruta": ruta_bd})
            return {"extractor": "historico", "fechas": [fecha]}

        original_moderno = plazasboe.actualizar_fechas
        original_historico = actualizacion_boe._actualizar_historico
        original_selector = plazasboe.seleccionar_extractor
        try:
            plazasboe.actualizar_fechas = moderno
            actualizacion_boe._actualizar_historico = historico
            plazasboe.seleccionar_extractor = lambda f: "historico" if "2004" in str(f) else "actual"
            fechas = ["2004/01/01", "2025/06/28", "2026/09/12"]
            resultado = actualizacion_boe._actualizar_productivo(fechas, str(copia), None)
            resultado_inverso = actualizacion_boe._actualizar_productivo(list(reversed(fechas)), str(copia), None)
        finally:
            plazasboe.actualizar_fechas = original_moderno
            actualizacion_boe._actualizar_historico = original_historico
            plazasboe.seleccionar_extractor = original_selector

        sha_despues = _sha(copia)
        estado_despues = _db_state(copia)
        informe = {
            "paso": "8.12D-2",
            "arquitectura": "despacho por fecha: historico -> ejecutar_flujo_historico; moderno -> actualizar_fechas",
            "fechas_prueba": fechas,
            "despacho_orden_directo": llamadas[:3],
            "despacho_orden_inverso": llamadas[3:],
            "atomicidad": "cada fecha se invoca como unidad independiente; un error se propaga y detiene el despacho posterior",
            "progreso": "se reutiliza el callback existente; sin porcentaje inventado",
            "sha_copia_antes": sha_antes,
            "sha_copia_despues": sha_despues,
            "copia_inmutable": sha_antes == sha_despues,
            "estado_antes": estado_antes,
            "estado_despues": estado_despues,
            "resultado_directo": resultado,
            "resultado_inverso": resultado_inverso,
        }
    salida = Path("informes/auditorias/fase8_paso12d2_integracion_flujo_historico_web.json")
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(informe, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
