import sqlite3
from pathlib import Path

import pytest

from scripts.audit import aplicar_maestros_paso8_22 as mod


def _bd(tmp_path, *, alterar=None):
    ruta = tmp_path / "boe.db"
    con = sqlite3.connect(ruta)
    con.executescript("""
        CREATE TABLE metadata (clave TEXT PRIMARY KEY, valor TEXT NOT NULL);
        CREATE TABLE publicaciones (publicacion_id TEXT PRIMARY KEY, enlace TEXT NOT NULL,
            fecha_boe TEXT NOT NULL, fecha_boe_original TEXT NOT NULL, version_extractor TEXT NOT NULL,
            estado_analisis TEXT NOT NULL, coincidencias INTEGER NOT NULL);
        CREATE TABLE oposiciones (oposicion_id INTEGER PRIMARY KEY, num_plazas INTEGER,
            puesto TEXT NOT NULL, puesto_normalizado TEXT, administracion TEXT, ambito TEXT,
            tipo_entidad TEXT, escala TEXT NOT NULL, subescala TEXT NOT NULL, clase TEXT NOT NULL,
            sistema TEXT NOT NULL, turno TEXT NOT NULL, fecha_boe TEXT NOT NULL,
            fecha_boe_original TEXT NOT NULL, enlace TEXT NOT NULL, publicacion_id TEXT NOT NULL,
            version_extractor TEXT NOT NULL, FOREIGN KEY(publicacion_id) REFERENCES publicaciones(publicacion_id));
        CREATE TABLE busquedas (codigo TEXT PRIMARY KEY);
        CREATE TABLE cobertura (fecha TEXT PRIMARY KEY, estado TEXT NOT NULL, version_extractor TEXT NOT NULL,
            fecha_ultima_consulta TEXT NOT NULL, numero_publicaciones INTEGER NOT NULL);
    """)
    con.executemany("INSERT INTO metadata VALUES (?,?)", [("schema_version", "6"), ("data_version", "47")])
    con.execute("INSERT INTO publicaciones VALUES ('p','x','2020-01-01','2020-01-01','x','ok',1)")
    rows = [(76794, 100, "Maestro/maestra en educación infantil"),
            (91232, 200, "Maestro-a de Educación Infantil"),
            (96837, 300, "Maestro o Maestra de Educación Infantil"),
            (17263, 146, "funcionarios docentes para el Cuerpo de Maestros"),
            (99999, 9, "Puesto ajeno")]
    for oid, plazas, puesto in rows:
        con.execute("""INSERT INTO oposiciones(oposicion_id,num_plazas,puesto,puesto_normalizado,
            administracion,ambito,tipo_entidad,escala,subescala,clase,sistema,turno,fecha_boe,
            fecha_boe_original,enlace,publicacion_id,version_extractor)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (oid, plazas, puesto, puesto, "A", "B", "C", "E", "S", "C", "S", "T",
             "2020-01-01", "2020-01-01", "x", "p", "x"))
    con.commit(); con.close()
    if alterar:
        con = sqlite3.connect(ruta); alterar(con); con.commit(); con.close()
    return ruta


def test_aplica_exactamente_los_cuatro_y_versiona(tmp_path):
    ruta = _bd(tmp_path)
    resultado = mod.aplicar(ruta, tmp_path / "backups")
    assert resultado["rowcount"] == 4
    assert resultado["plazas"] == 746
    assert resultado["data_version_before"] == "47"
    assert resultado["data_version_after"] in {"48", "49"}
    assert Path(resultado["backup"]["ruta"]).exists()
    con = sqlite3.connect(ruta)
    rows = dict(con.execute("SELECT oposicion_id, puesto_normalizado FROM oposiciones"))
    assert rows[76794] == rows[91232] == rows[96837] == "Maestro de Educación Infantil"
    assert rows[17263] == "Maestros"
    assert rows[99999] == "Puesto ajeno"
    con.close()


def test_guardia_falla_sin_actualizacion_parcial(tmp_path):
    def alterar(con):
        con.execute("UPDATE oposiciones SET puesto_normalizado='otro' WHERE oposicion_id=91232")
    ruta = _bd(tmp_path, alterar=alterar)
    with pytest.raises(RuntimeError, match="canon anterior"):
        mod.aplicar(ruta, tmp_path / "backups")
    con = sqlite3.connect(ruta)
    assert con.execute("SELECT puesto_normalizado FROM oposiciones WHERE oposicion_id=76794").fetchone()[0] == "Maestro/maestra en educación infantil"
    assert con.execute("SELECT puesto_normalizado FROM oposiciones WHERE oposicion_id=91232").fetchone()[0] == "otro"
    assert dict(con.execute("SELECT clave, valor FROM metadata"))["data_version"] == "47"
    con.close()


def test_segunda_aplicacion_es_rechazada(tmp_path):
    ruta = _bd(tmp_path)
    mod.aplicar(ruta, tmp_path / "backups")
    with pytest.raises(RuntimeError, match="canon anterior"):
        mod.aplicar(ruta, tmp_path / "backups")
