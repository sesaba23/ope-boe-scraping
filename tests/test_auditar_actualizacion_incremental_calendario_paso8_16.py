import hashlib, json
from pathlib import Path
from scripts.audit.auditar_actualizacion_incremental_calendario_paso8_16 import main
def test_auditoria_incremental_read_only(tmp_path):
 p=Path('datos/boe.db'); antes=hashlib.sha256(p.read_bytes()).hexdigest(); d=main(tmp_path/'informe.json')
 assert d['sqlite_real_modificada'] is False and 'fechas_completadas' in d['contrato_api']
 assert json.loads((tmp_path/'informe.json').read_text())['baseline']['data_version'] in {'47', '48', '49', '50'}
 assert hashlib.sha256(p.read_bytes()).hexdigest()==antes
