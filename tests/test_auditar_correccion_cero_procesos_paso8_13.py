import hashlib, json
from pathlib import Path
from scripts.audit.auditar_correccion_cero_procesos_paso8_13 import main
def test_auditoria_cero_procesos_reproducible_y_read_only(tmp_path):
 db=Path('datos/boe.db'); antes=hashlib.sha256(db.read_bytes()).hexdigest(); d=main(tmp_path/'informe.json')
 assert d['sqlite_real_modificada'] is False and d['normalizador_cambios']==0
 assert 'sin_procesos_selectivos=True' in d['comportamiento_corregido']
 assert json.loads((tmp_path/'informe.json').read_text())['baseline_data_version']=='42'
 assert hashlib.sha256(db.read_bytes()).hexdigest()==antes
