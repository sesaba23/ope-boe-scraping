import sqlite3
from pathlib import Path
from scripts.audit.auditar_funcionarios_docentes_paso9g import familia
def test_familias_y_falsos_positivos():
    assert familia('Profesor de Piano')=='PROFESOR_INSTRUMENTO'
    assert familia('Profesor de Conservatorio')=='PROFESOR_CONSERVATORIO'
    assert familia('Técnico de Cultura')=='FALSO_POSITIVO'
def test_sqlite_read_only():
    p=Path('datos/boe.db'); m=p.stat().st_mtime_ns
    c=sqlite3.connect(p); c.execute('select count(*) from oposiciones').fetchone(); c.close(); assert p.stat().st_mtime_ns==m
