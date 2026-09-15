import hashlib
from pathlib import Path
from scripts.audit.reconciliar_baseline_paso8_16a1 import main
def test_cadena_data42_47_reconciliada_sin_escritura(tmp_path):
    p=Path('datos/boe.db'); antes=hashlib.sha256(p.read_bytes()).hexdigest(); d=main(tmp_path/'r.json')
    assert d['baseline_actual_valido'] and d['estados'][-1]['data_version'] in {'47', '48', '49', '50'}
    assert all(t['oposiciones_bajas']==0 and t['oposiciones_modificadas']==0 for t in d['transiciones'])
    assert hashlib.sha256(p.read_bytes()).hexdigest()==antes
