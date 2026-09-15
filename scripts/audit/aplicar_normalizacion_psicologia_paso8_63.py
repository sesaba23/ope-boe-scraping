"""PASOS 62-63: pre-gate y aplicación transaccional de Psicólogo/a genérico."""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from normalizacion_puestos import _clave, normalizar_puesto
from scripts.audit.auditar_bomberos_paso8_40 import state
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate_auditar

DB = ROOT / "datos" / "boe.db"
INF = ROOT / "informes" / "normalizacion_puestos"
BACKUPS = ROOT / "backups" / "sqlite"
OUT62 = INF / "fase8_paso62_reglas_psicologia.json"
OUT63 = INF / "fase8_paso63_aplicacion_psicologia.json"
CANON = "Psicólogo"
VARIANTES = {"psicologo", "psicologa", "psicologo/a", "psicologa/o", "psicologo-a"}


def sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def plan() -> list[dict]:
    """Plan dinámico: el normalizador decide; el filtro SQL sólo acelera."""
    conexion = sqlite3.connect(DB)
    conexion.row_factory = sqlite3.Row
    try:
        filas = []
        for fila in conexion.execute(
            "select oposicion_id, puesto, puesto_normalizado, num_plazas from oposiciones "
            "where lower(puesto) like '%psic%'"
        ):
            clave = _clave(fila["puesto"])
            nuevo = normalizar_puesto(fila["puesto"])
            if nuevo == CANON and clave in VARIANTES and nuevo != fila["puesto_normalizado"]:
                filas.append({
                    "id": fila["oposicion_id"], "puesto": fila["puesto"],
                    "puesto_normalizado_anterior": fila["puesto_normalizado"],
                    "puesto_normalizado_nuevo": nuevo, "plazas": fila["num_plazas"],
                    "conjunto_A": "PSICOLOGO_GENERICO", "canon": CANON,
                })
        return filas
    finally:
        conexion.close()


def _resumen_gate(gate: dict) -> dict:
    return {clave: {"filas": gate[clave]["filas"], "plazas": gate[clave]["plazas"]} for clave in (
        "cambios_reales_recalculables", "discrepancias_contextuales_no_recalculables",
        "discrepancias_no_clasificables_automaticamente",
    )}


def precheck() -> None:
    gate = gate_auditar(DB)
    filas = plan()
    esperado = gate["cambios_reales_recalculables"]["filas"]
    if len(filas) != esperado:
        raise RuntimeError(f"plan {len(filas)} distinto de gate pre-SQLite {esperado}")
    resultado = {
        "version": "fase8-paso62-v1", "modo": "normalizador_sin_sqlite",
        "reglas_implementadas": {CANON: sorted(VARIANTES)},
        "cobertura_logica_A_global_filas": 476, "cobertura_logica_A_global_plazas": 830,
        "filas_que_requieren_update": len(filas), "plazas_que_requieren_update": sum(f["plazas"] or 0 for f in filas),
        "gate_pre_sqlite": _resumen_gate(gate), "sqlite_antes": state(),
        "fronteras": {"especialidades": "preservadas por coincidencia completa", "sanitario": "preservado", "tecnico_facultativo": "preservados", "orientacion_psicopedagogia": "preservadas", "cuerpos_mandos_compuestos": "preservados"},
    }
    OUT62.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"filas_update": len(filas), "gate": resultado["gate_pre_sqlite"]}, ensure_ascii=False))


def aplicar() -> dict:
    if not OUT62.exists():
        raise RuntimeError("falta el precheck PASO 62")
    pre = json.loads(OUT62.read_text(encoding="utf-8"))
    antes, filas = state(), plan()
    esperado = pre["filas_que_requieren_update"]
    if len(filas) != esperado:
        raise RuntimeError(f"plan dinámico {len(filas)} distinto del precheck {esperado}")
    if any(_clave(f["puesto"]) not in VARIANTES or f["canon"] != CANON for f in filas):
        raise RuntimeError("el plan contiene una fila fuera del conjunto A")
    BACKUPS.mkdir(parents=True, exist_ok=True)
    copia = BACKUPS / f"boe_paso63_psicologia_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}.db"
    shutil.copy2(DB, copia)
    if sha(copia) != antes["sha256"]:
        raise RuntimeError("la copia no coincide con el origen")
    comprobacion = sqlite3.connect(copia)
    try:
        if comprobacion.execute("pragma integrity_check").fetchone()[0] != "ok" or list(comprobacion.execute("pragma foreign_key_check")):
            raise RuntimeError("backup ilegible o con claves externas inválidas")
    finally:
        comprobacion.close()
    conexion = sqlite3.connect(DB)
    mutaciones = 0
    try:
        conexion.execute("BEGIN IMMEDIATE")
        for fila in filas:
            mutaciones += conexion.execute(
                "update oposiciones set puesto_normalizado=? where oposicion_id=? and puesto_normalizado=?",
                (fila["puesto_normalizado_nuevo"], fila["id"], fila["puesto_normalizado_anterior"]),
            ).rowcount
        if mutaciones != len(filas):
            conexion.rollback()
            raise RuntimeError("rowcount distinto del plan")
        if conexion.execute("pragma integrity_check").fetchone()[0] != "ok" or list(conexion.execute("pragma foreign_key_check")):
            conexion.rollback()
            raise RuntimeError("validación SQLite pre-commit fallida")
        conexion.execute("update metadata set valor=? where clave='data_version'", (str(int(antes["data_version"]) + 1),))
        conexion.commit()
    finally:
        conexion.close()
    despues = state()
    return {
        "antes": antes,
        "backup": {"ruta": str(copia), "sha256": sha(copia), "tamano": copia.stat().st_size, "data_version": antes["data_version"], "integrity_check": "ok", "foreign_key_check": []},
        "plan": filas, "mutaciones": mutaciones, "plazas_mutadas": sum(f["plazas"] or 0 for f in filas), "despues": despues,
    }


def ejecutar() -> None:
    primera = aplicar()
    segunda = plan()
    resultado = {
        "version": "fase8-paso63-v1", "generado_utc": datetime.now(timezone.utc).isoformat(),
        "primera_ejecucion": primera,
        "segunda_ejecucion": {"mutaciones": len(segunda), "data_version": state()["data_version"]},
        "gate_final": None,
    }
    if segunda:
        raise RuntimeError("la segunda ejecución no fue idempotente")
    OUT63.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"mutaciones": primera["mutaciones"], "segunda": len(segunda), "data_version": primera["despues"]["data_version"]}, ensure_ascii=False))


def finalizar() -> None:
    resultado = json.loads(OUT63.read_text(encoding="utf-8"))
    resultado["gate_final"] = _resumen_gate(gate_auditar(DB))
    OUT63.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(resultado["gate_final"], ensure_ascii=False))


if __name__ == "__main__":
    if "--precheck" in sys.argv:
        precheck()
    elif "--finalizar" in sys.argv:
        finalizar()
    else:
        ejecutar()
