import sqlite3

import pytest

import base_datos
import recalcular_puestos_normalizados as modulo


def _base(ruta, *, version="7"):
    conexion = base_datos.conectar(ruta)
    base_datos.crear_esquema(conexion)
    conexion.executemany(
        "INSERT INTO metadata(clave,valor) VALUES (?,?)",
        [("schema_version", "3"), ("data_version", version),
         ("created_at", "x"), ("updated_at", "x")],
    )
    conexion.execute(
        "INSERT INTO publicaciones(publicacion_id,enlace,fecha_boe,fecha_boe_original,version_extractor,estado_analisis,coincidencias) VALUES ('p','e','2026-01-01','x','1','ok',2)"
    )
    for indice, puesto in enumerate((
        "Ingeniero Técnico Industrial",
        "Técnico de Grado Medio Ingeniero Técnico Industrial",
    ), 1):
        conexion.execute(
            "INSERT INTO oposiciones(oposicion_id,puesto,puesto_normalizado,escala,subescala,clase,sistema,turno,fecha_boe,fecha_boe_original,enlace,publicacion_id,version_extractor) VALUES (?,?,?,'--','--','--','--','--','2026-01-01','x','e','p','1')",
            (indice, puesto, puesto),
        )
    conexion.commit(); conexion.close()


def _estado(ruta):
    conexion = sqlite3.connect(ruta)
    try:
        return (
            dict(conexion.execute("SELECT clave,valor FROM metadata")),
            conexion.execute("SELECT puesto,puesto_normalizado FROM oposiciones ORDER BY oposicion_id").fetchall(),
        )
    finally:
        conexion.close()


def test_dry_run_no_escribe_ni_crea_backup(tmp_path):
    ruta = tmp_path / "base.db"; _base(ruta)
    antes = _estado(ruta)
    resultado = modulo.recalcular(ruta, tmp_path / "backups", dry_run=True)
    assert resultado["filas_examinadas"] == 2
    assert resultado["filas_que_cambiarian"] == 1
    assert resultado["grupos_fusionados"] == 1
    assert _estado(ruta) == antes
    assert not (tmp_path / "backups").exists()


def test_aplica_backup_version_integridad_e_idempotencia(tmp_path):
    ruta = tmp_path / "base.db"; _base(ruta)
    resultado = modulo.recalcular(ruta, tmp_path / "backups")
    assert resultado["actualizada"] is True
    assert resultado["data_version_despues"] == "8"
    assert list((tmp_path / "backups").glob("*.db"))
    metadata, filas = _estado(ruta)
    assert metadata["schema_version"] == "5" and metadata["data_version"] == "8"
    assert filas == [
        ("Ingeniero Técnico Industrial", "Ingeniero Técnico Industrial"),
        ("Técnico de Grado Medio Ingeniero Técnico Industrial", "Ingeniero Técnico Industrial"),
    ]
    conexion = base_datos.conectar(ruta, readonly=True)
    assert base_datos.integrity_check(conexion) == ["ok"]
    assert base_datos.foreign_key_check(conexion) == []
    conexion.close()
    segundo = modulo.recalcular(ruta, tmp_path / "otros")
    assert segundo["actualizada"] is False
    assert segundo["filas_que_cambiarian"] == 0
    assert segundo["data_version_despues"] == "8"
    assert not (tmp_path / "otros").exists()


def test_error_de_integridad_hace_rollback(tmp_path, monkeypatch):
    ruta = tmp_path / "base.db"; _base(ruta)
    antes = _estado(ruta)
    monkeypatch.setattr(
        modulo.base_datos, "crear_backup", lambda *_: tmp_path / "backup.db"
    )
    monkeypatch.setattr(modulo.base_datos, "integrity_check", lambda conexion: ["error"])
    with pytest.raises(RuntimeError, match="integrity_check"):
        modulo.recalcular(ruta, tmp_path / "backups")
    assert _estado(ruta) == antes


def test_rechaza_schema_distinto_de_v3(tmp_path):
    ruta = tmp_path / "base.db"; _base(ruta)
    conexion = sqlite3.connect(ruta)
    conexion.execute("UPDATE metadata SET valor='2' WHERE clave='schema_version'")
    conexion.commit(); conexion.close()
    with pytest.raises(RuntimeError, match="schema_version 3"):
        modulo.recalcular(ruta, tmp_path / "backups", dry_run=True)
