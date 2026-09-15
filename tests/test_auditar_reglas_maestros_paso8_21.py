import hashlib
import json
import sqlite3
from pathlib import Path

from normalizacion_puestos import normalizar_puesto
from scripts.audit import auditar_reglas_maestros_paso8_21 as audit


def test_variantes_a1_y_a2_y_negativos():
    for texto in audit.EXPECTED.values():
        assert normalizar_puesto(texto[0]) == texto[1]
    for texto in (
        "Maestro/a de Educación Infantil de la plantilla de personal laboral fijo",
        "Maestro/a Educación Infantil de la plantilla de personal laboral fijo",
        "Maestro/a de Escuela Infantil", "Maestro/a de la plantilla de personal laboral fijo",
        "Maestro de Taller", "Maestro de Música",
        "funcionarios docentes en los cuerpos de maestros 250",
    ):
        assert normalizar_puesto(texto) != ("Maestros" if "cuerpos de maestros" in texto else "Maestro de Educación Infantil")


def test_auditoria_real_ids_plazas_gate_y_sqlite_inmutable():
    db = Path("datos/boe.db")
    before = (db.stat().st_size, db.stat().st_mtime_ns, hashlib.sha256(db.read_bytes()).hexdigest())
    result = audit.auditar(db)
    assert result["sqlite_modificada"] is False
    assert result["dry_run_especifico"]["esperados"] == [17263, 76794, 91232, 96837]
    # El mismo auditor se ejecuta antes de la aplicación (4 pendientes) y
    # después de ella (ninguno pendiente); ambos estados son válidos.
    assert result["dry_run_especifico"]["obtenidos"] in ([], [17263, 76794, 91232, 96837])
    assert result["dry_run_especifico"]["faltantes"] == [x for x in result["dry_run_especifico"]["esperados"] if x not in result["dry_run_especifico"]["obtenidos"]]
    assert result["dry_run_especifico"]["inesperados"] == []
    gate = result["gate_global_paso19"]
    if result["dry_run_especifico"]["obtenidos"]:
        assert gate["total_discrepancias"] == 333
        assert gate["cambios_reales_recalculables"]["filas"] == 4
        assert gate["cambios_reales_recalculables"]["plazas"] == 746
        assert gate["cambios_reales_recalculables"]["ids"] == [17263, 76794, 91232, 96837]
    else:
        assert gate["total_discrepancias"] in (329, 330)
        assert gate["cambios_reales_recalculables"]["filas"] in (0, 1)
    assert gate["discrepancias_contextuales_no_recalculables"]["filas"] == 329
    assert gate["discrepancias_no_clasificables_automaticamente"]["filas"] == 0
    assert (db.stat().st_size, db.stat().st_mtime_ns, hashlib.sha256(db.read_bytes()).hexdigest()) == before


def test_reglas_no_dependeran_de_ids_ni_plazas():
    codigo = Path("normalizacion_puestos.py").read_text(encoding="utf-8")
    assert "oposicion_id" not in codigo
    assert "76794" not in codigo and "91232" not in codigo and "96837" not in codigo and "17263" not in codigo
    assert "num_plazas" not in codigo


def test_informe_reproducible_si_ya_generado():
    informe = Path("informes/normalizacion_puestos/fase8_paso21_reglas_maestros.json")
    if informe.exists():
        data = json.loads(informe.read_text(encoding="utf-8"))
        assert data["sqlite_modificada"] is False
        assert data["dry_run_especifico"]["inesperados"] == []
