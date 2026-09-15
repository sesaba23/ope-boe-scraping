from scripts.audit.auditar_fase8_paso3 import ejecutar


def test_paso3_no_propone_reglas_inseguras(tmp_path):
    db = tmp_path / "boe.db"
    # La auditoría debe poder ejecutarse contra una base mínima sin escribirla.
    import sqlite3
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE metadata (clave TEXT, valor TEXT); INSERT INTO metadata VALUES ('schema_version','6'),('data_version','36'); CREATE TABLE oposiciones (oposicion_id INTEGER, puesto TEXT, puesto_normalizado TEXT, num_plazas REAL, ambito TEXT);")
    con.execute("INSERT INTO oposiciones VALUES (1, 'Profesor de Música', 'Profesor de Música', 1, 'LOCAL')")
    con.commit(); con.close()
    before = db.read_bytes()
    out = ejecutar(db, tmp_path / "informe.json")
    assert out["conjunto_seguro"]["filas"] == 0
    assert db.read_bytes() == before
