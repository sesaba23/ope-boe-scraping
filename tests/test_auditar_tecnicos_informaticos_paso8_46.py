import hashlib
from pathlib import Path

from scripts.audit.auditar_tecnicos_informaticos_paso8_46 import auditar


def test_paso46_reconstruye_el_universo_sin_escribir_sqlite():
    db = Path('datos/boe.db')
    antes = hashlib.sha256(db.read_bytes()).hexdigest()
    resultado = auditar()
    assert resultado['universo_reconstruido']['filas'] == 500
    assert resultado['universo_reconstruido']['plazas'] == 645
    assert resultado['reconciliacion_paso39']['faltantes'] == []
    assert hashlib.sha256(db.read_bytes()).hexdigest() == antes


def test_paso46_simula_conjuntos_cerrados_sin_colisiones():
    resultado = auditar()
    assert resultado['clasificacion_A']['filas'] == 149
    assert len(resultado['conjuntos_A']) == 5
    assert all(not x['faltantes'] and not x['inesperados'] and not x['colisiones'] for x in resultado['simulaciones_A'])
