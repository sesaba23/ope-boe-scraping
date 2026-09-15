from scripts.audit.auditar_profesores_municipales_paso8_5 import ejecutar
import sqlite3

def test_auditoria_profesores_municipales_read_only(tmp_path):
    db=tmp_path/'x.db'; c=sqlite3.connect(db); c.executescript("CREATE TABLE oposiciones(oposicion_id INTEGER,puesto TEXT,puesto_normalizado TEXT,num_plazas REAL,ambito TEXT); INSERT INTO oposiciones VALUES(1,'Profesor de Música','Profesor de Música',1,'LOCAL');"); c.commit(); c.close(); before=db.read_bytes(); out=ejecutar(db,tmp_path/'r.json'); assert out['conjunto_seguro']['filas']==0; assert db.read_bytes()==before
