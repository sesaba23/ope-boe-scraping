import hashlib
from pathlib import Path
from scripts.audit.auditar_dispatcher_historico_moderno_paso8_14 import main
def test_dispatcher_y_selector_coinciden_y_sqlite_inalterada(tmp_path):
 db=Path('datos/boe.db'); antes=hashlib.sha256(db.read_bytes()).hexdigest(); d=main(tmp_path/'informe.json')
 assert d['causa_raiz_demostrada'] and d['codigo_actual_coherente']
 assert all(x['selector']==x['dispatcher'] for x in d['decisiones'])
 assert d['gate_historico_preservado'] and hashlib.sha256(db.read_bytes()).hexdigest()==antes
