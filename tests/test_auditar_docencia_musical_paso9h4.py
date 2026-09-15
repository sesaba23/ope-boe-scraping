import sqlite3
from pathlib import Path
from scripts.audit.auditar_docencia_musical_paso9h4 import propuesta
def test_canon_conserva_centro_y_especialidad():
    assert propuesta('Profesor de Piano de la Escuela Municipal de Música')[0]=='Profesor de Escuela de Música - Piano'
    assert propuesta('Músico de Banda') is None
    assert propuesta('Profesor de Música')[0]=='Profesor de Música'
def test_sqlite_read_only():
    p=Path('datos/boe.db'); m=p.stat().st_mtime_ns
    c=sqlite3.connect(p); c.execute('select count(*) from oposiciones').fetchone(); c.close(); assert p.stat().st_mtime_ns==m
