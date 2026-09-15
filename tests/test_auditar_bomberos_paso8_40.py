import hashlib
from pathlib import Path
from scripts.audit.auditar_bomberos_paso8_40 import auditar

def test_paso40_reconstruye_y_no_modifica_sqlite():
    db=Path('datos/boe.db'); before=hashlib.sha256(db.read_bytes()).hexdigest(); r=auditar()
    assert len(r['filas'])==786 and r['universo_reconstruido']['plazas']==8135
    assert r['reconciliacion_paso39']['faltantes']==[] and r['reconciliacion_paso39']['inesperados']==[]
    assert hashlib.sha256(db.read_bytes()).hexdigest()==before and not r['sqlite_modificada']

def test_paso40_separa_base_conductor_y_no_toca_fronteras():
    r=auditar(); assert r['clasificacion_A']['filas']==355
    assert all(not x['faltantes'] and not x['inesperados'] and not x['colisiones'] for x in r['simulaciones_A'])
    assert r['colisiones']['bombero_vs_conductor']

def test_paso40_gate_previo_estable():
    r=auditar(); assert r['gate_paso19_inicial']['discrepancias_no_clasificables_automaticamente']==0
