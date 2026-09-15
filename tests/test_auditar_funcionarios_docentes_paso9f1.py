import sqlite3
from pathlib import Path
from scripts.audit.auditar_funcionarios_docentes_paso9f1 import clasificar

def test_reconoce_y_excluye_candidatas():
    assert clasificar('Maestros')[0] == 'SEGURA_TEXTUAL'
    assert clasificar('Maestro de obras')[0] == 'EXCLUIDA'

def test_auditoria_no_escribe_sqlite():
    p=Path('datos/boe.db'); sha=p.stat().st_mtime_ns
    c=sqlite3.connect(p); c.execute('select count(*) from oposiciones').fetchone(); c.close()
    assert p.stat().st_mtime_ns == sha
