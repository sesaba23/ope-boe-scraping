import sqlite3
from pathlib import Path
from scripts.audit.auditar_docencia_musical_paso9h3 import naturaleza
def test_clasificacion_musical():
    assert naturaleza('Profesor de Piano')=='DOCENTE'
    assert naturaleza('Músico de Banda')=='DUDOSA'
    assert naturaleza('Técnico de Cultura Musical')=='EXCLUIDA'
def test_sqlite_read_only():
    p=Path('datos/boe.db'); m=p.stat().st_mtime_ns
    c=sqlite3.connect(p); c.execute('select count(*) from oposiciones').fetchone(); c.close(); assert p.stat().st_mtime_ns==m
