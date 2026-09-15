import hashlib
from pathlib import Path
from scripts.audit.auditar_cuerpo_docente_explicito_paso8_35 import auditar

def test_universo_reconciliacion_inmutable():
    db=Path('datos/boe.db'); b=hashlib.sha256(db.read_bytes()).hexdigest(); r=auditar()
    assert len(r['filas'])==26 and r['plazas']==9177 and r['denominaciones']==16
    assert r['reconciliacion_paso20']['faltantes']==[] and r['reconciliacion_paso20']['inesperados']==[]
    assert hashlib.sha256(db.read_bytes()).hexdigest()==b and not r['sqlite_modificada']

def test_cuerpo_maestros_y_conjunto_a():
    r=auditar(); assert r['cuerpo_maestros']['filas']==26
    assert r['conjuntos_A']==[]; assert r['clasificacion_A']['filas']==0
    assert r['simulacion_A']['faltantes']==[] and r['simulacion_A']['inesperados']==[]

def test_gate_normalizador_y_sin_anomalias():
    r=auditar(); assert not r['normalizador_modificado']; assert r['comparacion_persistido_normalizador']['discrepancias']==0
    assert r['gate_paso19']['cambios_reales_recalculables']==0
    assert r['gate_paso19']['discrepancias_contextuales_no_recalculables']==329
    assert r['gate_paso19']['discrepancias_no_clasificables_automaticamente']==0
    assert r['anomalias_historicas']==[]
