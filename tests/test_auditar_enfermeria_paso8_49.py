import hashlib
from pathlib import Path

from scripts.audit.auditar_enfermeria_paso8_49 import auditar


def test_paso49_reconstruye_enfermeria_sin_escribir_sqlite():
    db = Path('datos/boe.db')
    antes = hashlib.sha256(db.read_bytes()).hexdigest()
    resultado = auditar()
    assert resultado['universo_reconstruido']['filas'] == 425
    assert resultado['universo_reconstruido']['plazas'] == 3917
    assert resultado['reconciliacion_paso39']['faltantes'] == []
    assert hashlib.sha256(db.read_bytes()).hexdigest() == antes


def test_paso49_no_equipara_due_ats_ni_especialidades():
    resultado = auditar()
    assert resultado['comparacion_DUE_ATS_enfermero']['DUE'] == 'C'
    assert resultado['comparacion_DUE_ATS_enfermero']['ATS'] == 'C'
    assert resultado['simulaciones_A'][0]['faltantes'] == []
    assert resultado['simulaciones_A'][0]['inesperados'] == []
