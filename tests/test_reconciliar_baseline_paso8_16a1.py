import hashlib
from pathlib import Path
from scripts.audit.reconciliar_baseline_paso8_16a1 import main
def test_cadena_data42_47_reconciliada_sin_escritura(tmp_path):
    p=Path('datos/boe.db'); antes=hashlib.sha256(p.read_bytes()).hexdigest(); d=main(tmp_path/'r.json')
    assert d['baseline_actual_valido'] and d['estados'][-1]['data_version'] == '62'
    # Historical transitions are immutable; the final 46→62 transition
    # records the approved FASE 8 normalisation updates explicitly.
    assert all(t['oposiciones_bajas'] == 0 for t in d['transiciones'])
    assert all(t['oposiciones_modificadas'] == 0 for t in d['transiciones'][:-1])
    assert d['transiciones'][-1]['oposiciones_modificadas'] == 6566
    assert hashlib.sha256(p.read_bytes()).hexdigest()==antes
