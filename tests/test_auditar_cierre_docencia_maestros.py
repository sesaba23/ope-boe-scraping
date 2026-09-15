import hashlib
from pathlib import Path
from scripts.audit.auditar_cierre_docencia_maestros import auditar_cierre

def test_cierre_reconstruye_tres_microfamilias_sin_mutar_sqlite():
    db=Path('datos/boe.db'); before=hashlib.sha256(db.read_bytes()).hexdigest(); r=auditar_cierre()
    assert hashlib.sha256(db.read_bytes()).hexdigest()==before
    assert r['informes_etapa']['paso36']['universo']['filas']==16
    assert r['informes_etapa']['paso37']['universo']['filas']==9
    assert r['informes_etapa']['paso38']['universo']['filas']==32
    assert r['sqlite_inicial']==r['sqlite_final']

def test_cierre_no_deja_a_ni_regresiones_y_protege_fotocomposicion():
    r=auditar_cierre(); music=r['informes_etapa']['paso36']
    assert music['fotocomposicion']['protegida'] is True
    assert all(x['clasificacion_A']['filas']==0 for x in r['informes_etapa'].values())
    assert r['regresiones']==[] and r['microfamilias_pendientes']==0 and r['estado_final']=='CERRADO'

def test_gate_final_estable():
    r=auditar_cierre(); gate=r['gate_paso19_final']
    assert gate['cambios_reales_recalculables']==0
    assert gate['discrepancias_contextuales_no_recalculables']==329
    assert gate['discrepancias_no_clasificables_automaticamente']==0
