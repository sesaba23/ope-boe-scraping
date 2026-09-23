import hashlib, json, sqlite3
from pathlib import Path
from scripts.audit.auditar_actualizacion_incremental_calendario_paso8_16 import main
def test_auditoria_incremental_read_only(tmp_path):
 p=Path('datos/boe.db'); antes=hashlib.sha256(p.read_bytes()).hexdigest(); d=main(tmp_path/'informe.json')
 assert d['sqlite_real_modificada'] is False and 'fechas_completadas' in d['contrato_api']
 informe=json.loads((tmp_path/'informe.json').read_text())['baseline']
 with sqlite3.connect(p) as conexion:
  metadata=dict(conexion.execute("SELECT clave, valor FROM metadata WHERE clave IN ('schema_version', 'data_version')"))
 assert informe['schema_version']==metadata['schema_version']
 assert informe['data_version']==metadata['data_version']
 assert hashlib.sha256(p.read_bytes()).hexdigest()==antes
