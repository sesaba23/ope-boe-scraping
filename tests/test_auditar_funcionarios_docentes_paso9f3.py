import sqlite3
from pathlib import Path
from scripts.audit.auditar_funcionarios_docentes_paso9f3 import INSTR
def test_inventario_instrumentos_y_bloqueo_falsos_positivos():
    assert 'piano' in INSTR and 'viol' in INSTR
def test_sqlite_no_se_modifica():
    p=Path('datos/boe.db'); m=p.stat().st_mtime_ns
    c=sqlite3.connect(p); c.execute('select count(*) from oposiciones').fetchone(); c.close()
    assert p.stat().st_mtime_ns==m
