import sqlite3
from pathlib import Path
from scripts.audit.auditar_docencia_musical_paso9h1 import clasificar
def test_separa_docencia_musical_y_no_docencia():
    assert clasificar('Profesor de Piano')=='DOCENTE_CLARO'
    assert clasificar('Músico de Banda')=='DUDOSO'
    assert clasificar('Técnico de Cultura Musical')=='NO_DOCENTE'
def test_read_only_sqlite():
    p=Path('datos/boe.db'); m=p.stat().st_mtime_ns
    c=sqlite3.connect(p); c.execute('select count(*) from oposiciones').fetchone(); c.close(); assert p.stat().st_mtime_ns==m
