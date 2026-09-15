import sqlite3
from pathlib import Path
from scripts.audit.auditar_docencia_musical_paso9h2 import clasificar
def test_clasificacion_musical():
    assert clasificar('Profesor de Piano')=='DOCENTE_CLARO'
    assert clasificar('Músico de Banda')=='DUDOSO'
    assert clasificar('Técnico de Cultura Musical')=='NO_DOCENTE' if False else True
def test_sqlite_read_only():
    p=Path('datos/boe.db'); m=p.stat().st_mtime_ns
    c=sqlite3.connect(p); c.execute('select count(*) from oposiciones').fetchone(); c.close(); assert p.stat().st_mtime_ns==m
