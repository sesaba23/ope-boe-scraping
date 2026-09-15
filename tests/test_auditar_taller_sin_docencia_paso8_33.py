import hashlib
from pathlib import Path

from scripts.audit.auditar_taller_sin_docencia_paso8_33 import auditar


def test_universo_y_reconciliacion_paso20_read_only():
    db = Path("datos/boe.db")
    antes = hashlib.sha256(db.read_bytes()).hexdigest()
    r = auditar()
    assert hashlib.sha256(db.read_bytes()).hexdigest() == antes
    assert r["universo"]["filas"] == 8
    assert r["universo"]["plazas"] == 10
    assert r["reconciliacion_paso20"]["faltantes"] == []
    assert r["reconciliacion_paso20"]["inesperados"] == []
    assert r["sqlite_modificada"] is False


def test_no_hay_conjuntos_a_y_se_preservan_funciones():
    r = auditar()
    assert r["conjuntos_A"] == []
    assert r["clasificacion_A"]["filas"] == 0
    assert r["clasificacion_C"]["filas"] + r["clasificacion_D"]["filas"] == 8
    assert r["clasificacion_D"]["filas"] == 1
    assert r["frontera_paso32"]


def test_gate_y_normalizador_inmutables():
    r = auditar()
    assert r["normalizador_modificado"] is False
    assert r["gate_paso19"]["cambios_reales_recalculables"] == 0
    assert r["gate_paso19"]["discrepancias_contextuales_no_recalculables"] == 329
    assert r["gate_paso19"]["discrepancias_no_clasificables_automaticamente"] == 0
    assert r["git_diff_check"] is True
