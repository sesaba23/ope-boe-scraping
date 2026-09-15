import hashlib
from pathlib import Path
from scripts.audit.auditar_priorizacion_fase8_paso39 import auditar

def test_paso39_excluye_docencia_y_no_modifica_sqlite():
    db=Path('datos/boe.db'); before=hashlib.sha256(db.read_bytes()).hexdigest(); r=auditar()
    assert hashlib.sha256(db.read_bytes()).hexdigest()==before
    assert r['docencia_maestros_excluido'] is True
    assert r['universo_fase8_restante']['filas'] > 0
    assert r['sqlite_modificada'] is False and r['normalizador_modificado'] is False

def test_paso39_prioriza_bomberos_y_no_crea_reglas():
    r=auditar(); assert r['siguiente_bloque_profesional']=='Bomberos y bomberos-conductores'
    assert len(r['ranking_top10'])==10
    assert r['estimacion_siguiente_bloque']['candidatos_A_preliminares']
    assert 'PASO 40' in r['propuesta_paso40']

def test_paso39_gate_estable():
    r=auditar(); assert r['gate_paso19']=={'cambios_reales_recalculables':0,'discrepancias_contextuales_no_recalculables':329,'discrepancias_no_clasificables_automaticamente':0}
