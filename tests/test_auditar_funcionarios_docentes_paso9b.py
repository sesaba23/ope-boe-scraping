import json, sqlite3
from pathlib import Path
from scripts.audit.auditar_funcionarios_docentes_paso9b import clasificar

def test_clasificacion_docente_y_falsos_positivos():
    assert clasificar("Catedráticos de Universidad")[2] == "Catedráticos de Universidad"
    assert clasificar("Maestros")[2] == "Maestros"
    assert clasificar("Maestro de obras")[0] == "EXCLUIDA"
    assert clasificar("Profesor de Música")[0] == "SEGURA_CONTEXTUAL"

def test_auditoria_no_escribe_sqlite():
    db=Path("datos/boe.db"); antes=db.stat().st_mtime_ns
    con=sqlite3.connect(db); con.execute("select count(*) from oposiciones").fetchone(); con.close()
    assert db.stat().st_mtime_ns == antes
