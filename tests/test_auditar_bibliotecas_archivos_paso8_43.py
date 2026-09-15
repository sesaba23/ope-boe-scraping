import hashlib
from pathlib import Path

from scripts.audit.auditar_bibliotecas_archivos_paso8_43 import auditar


def test_paso43_reconstruye_el_universo_sin_escribir_sqlite():
    db = Path('datos/boe.db')
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    resultado = auditar()
    assert resultado['universo_reconstruido']['filas'] == 1977
    assert resultado['universo_reconstruido']['plazas'] == 3816
    assert resultado['reconciliacion_paso39']['faltantes'] == []
    assert resultado['reconciliacion_paso39']['inesperados'] == []
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    assert not resultado['sqlite_modificada']


def test_paso43_conjuntos_a_son_exactos_y_semanticamente_separados():
    resultado = auditar()
    assert resultado['clasificacion_A']['filas'] == 548
    assert {x['canon'] for x in resultado['conjuntos_A']} == {'Bibliotecario', 'Auxiliar de Biblioteca'}
    assert all(not x['faltantes'] and not x['inesperados'] and not x['colisiones'] for x in resultado['simulaciones_A'])
    assert resultado['taxonomia']['ARCHIVERO']['filas'] > 0
    assert resultado['taxonomia']['ESCALA_CUERPO']['filas'] > 0


def test_paso43_gate_no_crea_no_clasificables():
    resultado = auditar()
    assert resultado['gate_paso19_inicial']['discrepancias_no_clasificables_automaticamente'] == 0
