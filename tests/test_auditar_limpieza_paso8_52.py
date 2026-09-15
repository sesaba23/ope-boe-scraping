import hashlib
from pathlib import Path
from scripts.audit.auditar_limpieza_paso8_52 import auditar
def test_paso52_reconstruye_sin_escribir_sqlite():
 db=Path('datos/boe.db'); antes=hashlib.sha256(db.read_bytes()).hexdigest();r=auditar()
 assert r['universo_reconstruido']['filas']==1856 and r['universo_reconstruido']['plazas']==4542
 assert r['reconciliacion_paso39']['faltantes']==[] and len(r['reconciliacion_paso39']['inesperados'])==3 and hashlib.sha256(db.read_bytes()).hexdigest()==antes
def test_paso52_simulaciones_son_exactas():
 r=auditar();assert len(r['conjuntos_A'])==4
 assert all(not x['faltantes'] and not x['inesperados'] and not x['colisiones'] for x in r['simulaciones_A'])
