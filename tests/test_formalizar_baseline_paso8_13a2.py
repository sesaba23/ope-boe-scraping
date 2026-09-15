import hashlib, json
from pathlib import Path
from scripts.audit.formalizar_baseline_paso8_13a2 import main
def test_baseline_42_formalizado_sin_escritura(tmp_path):
 db=Path('datos/boe.db'); antes=(hashlib.sha256(db.read_bytes()).hexdigest(),db.stat().st_mtime_ns)
 d=main(tmp_path/'baseline.json'); despues=(hashlib.sha256(db.read_bytes()).hexdigest(),db.stat().st_mtime_ns)
 assert antes==despues and d['baseline_actual_valido'] and int(d['data_version']) >= 42 and d['normalizador_cambios']==0
 assert json.loads((tmp_path/'baseline.json').read_text())['sha256']==antes[0]
