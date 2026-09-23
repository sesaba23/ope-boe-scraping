import hashlib
import sqlite3
from pathlib import Path

from normalizacion_puestos import normalizar_puesto
from scripts.audit import auditar_regla_maestro_educacion_fisica_paso8_27 as audit


def test_variantes_validadas_y_negativas():
    assert normalizar_puesto("Maestro de Educación Física") == "Maestro de Educación Física"
    assert normalizar_puesto("Maestro/a de Educación Física") == "Maestro de Educación Física"
    for text in (
        "Maestro/a Educación Física", "Maestra de Educación Física",
        "Maestro Educación Física", "Maestro Especialista en Educación Física",
        "Maestro/a Especialista en Educación Física", "Maestro/a de Primaria",
        "Maestro/a de Inglés", "Maestro/a de Formación Profesional",
        "Maestro/a de Formación y Orientación Laboral",
        "Maestro/a Especialista de Audición y Lenguaje", "Maestro Audición y Lenguaje",
        "Maestro de Educación Especial",
    ):
        assert normalizar_puesto(text) == text


def test_revalidacion_universo_y_no_op():
    result = audit.auditar()
    assert result["variantes_exactas"]["filas"] == 2
    assert result["variantes_exactas"]["plazas"] == 6
    assert result["dry_run"]["no_op_ya_canonico"] == [11067, 99076]
    assert result["dry_run"]["obtenidos"] == [11067, 99076]
    assert result["dry_run"]["faltantes"] == []
    assert result["dry_run"]["filas_cubiertas_por_regla"] == 2
    assert result["dry_run"]["plazas_recalculables"] == 0


def test_regla_independiente_y_gate_real():
    result = audit.auditar()
    assert result["regla_implementada"]["independiente_de_ids_contexto_y_plazas"] is True
    assert result["dry_run"]["inesperados"] == []
    assert result["puerta_global_paso19"] == {
        "total_discrepancias": 329, "total_plazas_discrepantes": 2215.0,
        "cambios_reales_recalculables": 0, "plazas_recalculables": 0,
        "discrepancias_contextuales_no_recalculables": 329, "plazas_contextuales": 2215.0,
        "discrepancias_no_clasificables_automaticamente": 0,
    }


def test_sqlite_y_normalizador_intactos():
    db = Path("datos/boe.db")
    before = (db.stat().st_size, db.stat().st_mtime_ns, hashlib.sha256(db.read_bytes()).hexdigest())
    result = audit.auditar()
    after = (db.stat().st_size, db.stat().st_mtime_ns, hashlib.sha256(db.read_bytes()).hexdigest())
    assert before == after
    assert result["sqlite_modificada"] is False
    with sqlite3.connect(db) as conexion:
        metadata = dict(conexion.execute("SELECT clave, valor FROM metadata WHERE clave IN ('schema_version', 'data_version')"))
    assert result["sqlite_precheck"]["schema_version"] == metadata["schema_version"]
    assert result["sqlite_precheck"]["data_version"] == metadata["data_version"]
    assert result["normalizador_modificado"] is False
