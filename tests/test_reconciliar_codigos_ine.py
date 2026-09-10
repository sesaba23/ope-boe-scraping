import hashlib
import sqlite3

import pytest

import base_datos
from reconciliar_codigos_ine import reconciliar


def _sha(ruta):
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _base(tmp_path):
    ruta = tmp_path / "boe.db"
    con = sqlite3.connect(ruta)
    con.executescript("""
        CREATE TABLE metadata(clave TEXT PRIMARY KEY, valor TEXT);
        INSERT INTO metadata VALUES ('schema_version','6'),('data_version','25'),('created_at','x'),('updated_at','x');
        CREATE TABLE comunidades_autonomas(comunidad_id INTEGER PRIMARY KEY, nombre TEXT, es_ciudad_autonoma INTEGER DEFAULT 0);
        CREATE TABLE provincias(provincia_id TEXT PRIMARY KEY, nombre TEXT, comunidad_id INTEGER);
        CREATE TABLE municipios(codigo_ine TEXT PRIMARY KEY,nombre TEXT,nombre_normalizado TEXT,provincia_id TEXT,comunidad_id INTEGER,latitud REAL,longitud REAL);
        CREATE TABLE oposiciones(oposicion_id INTEGER PRIMARY KEY, puesto TEXT, puesto_normalizado TEXT, administracion TEXT,
          administracion_normalizada TEXT, municipio TEXT, provincia TEXT, comunidad_autonoma TEXT, ambito TEXT, tipo_entidad TEXT,
          municipio_codigo_ine TEXT, latitud REAL, longitud REAL, fecha_boe TEXT);
        INSERT INTO comunidades_autonomas VALUES (10,'Comunidad de Madrid',0),(11,'Comunitat Valenciana',0),(13,'Galicia',0);
        INSERT INTO provincias VALUES ('28','Madrid',10),('46','Valencia/València',11),('36','Pontevedra',13);
        INSERT INTO municipios VALUES ('28079','Madrid','madrid','28',10,40.4,-3.7),('46250','València','valencia','46',11,39.4,-0.4);
        INSERT INTO oposiciones VALUES
          (1,'p','','Ayuntamiento de Madrid','','Madrid','Madrid','Comunidad de Madrid','LOCAL','MUNICIPAL',NULL,1,2,'2026-01-01'),
          (2,'p','','Diputación Provincial','','Valencia','Valencia/València','Comunitat Valenciana','LOCAL','PROVINCIAL',NULL,3,4,'2026-01-01'),
          (3,'p','','Consejo Comarcal','','Madrid','Pontevedra','Galicia','LOCAL','SUPRAMUNICIPAL',NULL,5,6,'2026-01-01'),
          (4,'p','','Ayuntamiento de Cerdedo','','Cerdedo','Pontevedra','Galicia','LOCAL','MUNICIPAL',NULL,NULL,NULL,'2015-01-01'),
          (5,'p','','Cabildo Insular de Lanzarote','','','Las Palmas','Canarias','LOCAL','INSULAR',NULL,NULL,NULL,'2026-01-01');
    """)
    con.commit(); con.close()
    return ruta


def test_dry_run_es_inmutable_y_selecciona_exacto_normalizado(tmp_path):
    ruta = _base(tmp_path); antes = _sha(ruta)
    resultado = reconciliar(ruta, dry_run=True, esperados=2)
    assert resultado["numero_candidatos"] == 2
    assert {x["oposicion_id"] for x in resultado["candidatos"]} == {1, 2}
    assert resultado["sha256_antes"] == resultado["sha256_despues"] == antes


def test_escritura_solo_actualiza_fk_y_versiona_con_backup(tmp_path):
    ruta = _base(tmp_path)
    resultado = reconciliar(ruta, directorio_backup=tmp_path / "backups", esperados=2)
    assert resultado["actualizados"] == resultado["enlazados_con_coordenadas"] == 2
    assert (tmp_path / "backups").exists() and resultado["data_version_despues"] == "26"
    con = base_datos.conectar(ruta, readonly=True)
    try:
        assert con.execute("SELECT municipio_codigo_ine FROM oposiciones WHERE oposicion_id=1").fetchone()[0] == "28079"
        assert con.execute("SELECT municipio_codigo_ine FROM oposiciones WHERE oposicion_id=2").fetchone()[0] == "46250"
        assert con.execute("SELECT municipio_codigo_ine,latitud,longitud FROM oposiciones WHERE oposicion_id=3").fetchone() == (None, 5.0, 6.0)
        assert con.execute("SELECT municipio_codigo_ine FROM oposiciones WHERE oposicion_id=4").fetchone()[0] is None
        assert base_datos.integrity_check(con) == ["ok"] and base_datos.foreign_key_check(con) == []
    finally:
        con.close()


def test_deriva_y_rollback_no_dejan_actualizaciones_parciales(tmp_path, monkeypatch):
    ruta = _base(tmp_path)
    with pytest.raises(RuntimeError, match="Deriva"):
        reconciliar(ruta, dry_run=True, esperados=75)
    original = base_datos.guardar_metadata
    monkeypatch.setattr(base_datos, "guardar_metadata", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fallo")))
    with pytest.raises(RuntimeError, match="fallo"):
        reconciliar(ruta, directorio_backup=tmp_path / "backups", esperados=2)
    monkeypatch.setattr(base_datos, "guardar_metadata", original)
    con = base_datos.conectar(ruta, readonly=True)
    try:
        assert con.execute("SELECT COUNT(*) FROM oposiciones WHERE municipio_codigo_ine IS NOT NULL").fetchone()[0] == 0
        assert dict(con.execute("SELECT clave,valor FROM metadata"))["data_version"] == "25"
    finally:
        con.close()
