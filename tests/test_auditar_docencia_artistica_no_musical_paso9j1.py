import sqlite3
from pathlib import Path

from scripts.audit.auditar_docencia_artistica_no_musical_paso9j1 import (
    auditar,
    clasificar_denominacion,
)


def test_reconoce_especialidad_y_no_la_reduce_a_profesor():
    resultado = clasificar_denominacion("Profesor de Pintura")
    assert resultado["familia"] == "Profesor de Pintura"
    assert resultado["seguridad"] == "SEGURA_CON_ESPECIALIDAD"


def test_profesional_artistico_sin_docencia_es_excluido():
    assert clasificar_denominacion("Pintor municipal")["estado"] == "EXCLUIDA"
    assert clasificar_denominacion("Monitor de Teatro")["estado"] == "EXCLUIDA"


def test_docencia_y_funcion_no_docente_es_dudosa():
    resultado = clasificar_denominacion("Profesorado de monitor/a de Danza")
    assert resultado["estado"] == "DUDOSA"
    assert resultado["seguridad"] == "DUDOSA"


def test_auditoria_reconciliada_y_read_only():
    base = Path("datos/boe.db")
    mtime = base.stat().st_mtime_ns
    informe = auditar()
    assert informe["universo_total"]["filas"] == informe["reconciliacion_filas"]["universo"]
    assert informe["reconciliacion_filas"]["universo"] == informe["reconciliacion_filas"]["suma_estados"]
    assert informe["estado_inicial"] == informe["estado_final"]
    assert base.stat().st_mtime_ns == mtime
    with sqlite3.connect(base) as con:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
