import sqlite3
from pathlib import Path
from scripts.audit.auditar_funcionarios_docentes_paso9f2 import sem
def test_subfamilias_y_especialidad():
    assert sem('Catedráticos de Universidad')[0]=='UNIVERSIDAD_FUNCIONARIAL'
    assert sem('Profesor de Piano')[0]=='ARTISTICA_LOCAL'
    assert sem('Maestro de obras')[0]=='EXCLUIDA'
def test_sqlite_solo_lectura():
    p=Path('datos/boe.db'); m=p.stat().st_mtime_ns
    c=sqlite3.connect(p); c.execute('select count(*) from oposiciones').fetchone(); c.close()
    assert p.stat().st_mtime_ns==m
