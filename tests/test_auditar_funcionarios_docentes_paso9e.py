import sqlite3
from pathlib import Path
from scripts.audit.auditar_funcionarios_docentes_paso9e import clasificar

def test_clasifica_familias_y_exclusiones():
    assert clasificar('Catedráticos de Universidad')[2] == 'Catedráticos de Universidad'
    assert clasificar('Maestro de obras')[0] == 'EXCLUIDA'
    assert clasificar('Profesor de Música')[1] == 'artistica'
    assert clasificar('Profesor Contratado Doctor')[0] in {'DUDOSA','SEGURA_TEXTUAL'}

def test_auditoria_es_read_only():
    p=Path('datos/boe.db'); m=p.stat().st_mtime_ns
    con=sqlite3.connect(p); con.execute('select count(*) from oposiciones').fetchone(); con.close()
    assert p.stat().st_mtime_ns == m
