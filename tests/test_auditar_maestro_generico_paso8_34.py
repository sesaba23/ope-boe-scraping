import hashlib
from pathlib import Path
from scripts.audit.auditar_maestro_generico_paso8_34 import auditar

def test_universo_reconciliacion_y_sqlite_inmutable():
    db=Path('datos/boe.db'); before=hashlib.sha256(db.read_bytes()).hexdigest(); r=auditar()
    assert hashlib.sha256(db.read_bytes()).hexdigest()==before
    assert len(r['filas'])==34 and r['plazas']==502 and r['denominaciones']==6
    assert r['reconciliacion_paso20']['faltantes']==[] and r['reconciliacion_paso20']['inesperados']==[]
    assert r['sqlite_modificada'] is False

def test_singular_plural_cuerpo_y_sin_conjuntos_a():
    r=auditar(); assert r['conjuntos_A']==[]; assert r['clasificacion_A']['filas']==0
    assert r['clasificacion_B']['filas']+r['clasificacion_C']['filas']+r['clasificacion_D']['filas']==34
    assert r['cuerpo_maestros']['ids_explicitos']==[16956]
    assert r['singular_plural']['plural']==1

def test_gate_y_normalizador():
    r=auditar(); assert r['normalizador_modificado'] is False
    assert r['comparacion_persistido_normalizador']['discrepancias']==0
    assert r['gate_paso19']['cambios_reales_recalculables']==0
    assert r['gate_paso19']['discrepancias_contextuales_no_recalculables']==329
    assert r['gate_paso19']['discrepancias_no_clasificables_automaticamente']==0
