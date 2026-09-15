import hashlib
import json
from pathlib import Path

from scripts.audit import auditar_otras_especialidades_docentes_paso8_26 as audit


def test_universo_y_reconciliacion():
    result = audit.auditar()
    assert result["definicion_universo"] == {"criterio": "microfamilia otras_especialidades_docentes de PASO 20 reconciliada con SQLite", "filas": 9, "plazas": 26, "denominaciones": 9}
    rec = result["reconciliacion_paso20"]
    assert rec["solo_paso20"] == rec["solo_paso26"] == []
    assert rec["interseccion"] == rec["ids_paso20"]
    assert len({r["id"] for r in result["registros"]}) == 9


def test_clasificacion_y_especialidades_no_se_fusionan():
    result = audit.auditar()
    assert result["clasificacion"]["por_clase"] == {"A": 2, "C": 1, "D": 3, "B": 3}
    assert result["clasificacion"]["plazas"] == 26
    assert set(result["especialidades"]) == {"Educación Física", "Primaria", "Formación Profesional", "Formación y Orientación Laboral", "Inglés", "Audición y Lenguaje", "Educación Especial"}
    assert all(r["clasificacion_paso26"] in {"A", "B", "C", "D"} for r in result["registros"])


def test_conjunto_a_educacion_fisica_y_simulacion():
    result = audit.auditar()
    a = result["conjuntos_a"]
    assert len(a) == 1
    assert a[0]["canon"] == "Maestro de Educación Física"
    assert a[0]["ids"] == [11067, 99076]
    assert a[0]["filas"] == 2 and a[0]["plazas"] == 6
    sim = result["simulaciones_a"][0]
    assert sim["faltantes"] == [] and sim["inesperados"] == []
    assert sim["usa_fuzzy"] is False and sim["usa_ids_como_criterio"] is False


def test_repeticiones_laboral_y_abreviaturas():
    result = audit.auditar()
    assert all(r["repeticiones_exactas"]["filas"] >= 1 for r in result["registros"])
    assert any(r["relacion_laboral"] for r in result["registros"])
    assert result["abreviaturas"]["ninguna"]
    assert all(r["clasificacion_paso26"] != "A" or not r["relacion_laboral"] for r in result["registros"])


def test_gate_normalizador_y_sqlite_inmutables():
    db = Path("datos/boe.db")
    before = (db.stat().st_size, db.stat().st_mtime_ns, hashlib.sha256(db.read_bytes()).hexdigest())
    result = audit.auditar()
    after = (db.stat().st_size, db.stat().st_mtime_ns, hashlib.sha256(db.read_bytes()).hexdigest())
    assert before == after
    assert result["sqlite_modificada"] is False
    assert result["normalizador_modificado"] is False
    assert result["baseline"]["data_version"] == "50"
    assert result["puerta_global_paso19"] in ({"total_discrepancias": 329, "total_plazas_discrepantes": 2215.0, "cambios_reales_recalculables": 0, "discrepancias_contextuales_no_recalculables": 329, "discrepancias_no_clasificables_automaticamente": 0}, {"total_discrepancias": 330, "total_plazas_discrepantes": 2216.0, "cambios_reales_recalculables": 1, "discrepancias_contextuales_no_recalculables": 329, "discrepancias_no_clasificables_automaticamente": 0})


def test_informe_si_existe():
    path = Path("informes/normalizacion_puestos/fase8_paso26_otras_especialidades_docentes.json")
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["definicion_universo"]["filas"] == 9
        assert data["sqlite_modificada"] is False
