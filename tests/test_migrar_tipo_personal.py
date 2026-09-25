import sqlite3

import pytest

import base_datos
import migrar_tipo_personal


def _base_v6(tmp_path):
    ruta = tmp_path / "boe.db"
    con = base_datos.conectar(ruta)
    base_datos.crear_esquema(con)
    base_datos.guardar_metadata(con, schema_version=6, data_version=10)
    con.executemany(
        """INSERT INTO publicaciones(
               publicacion_id,enlace,fecha_boe,fecha_boe_original,titulo_original,
               version_extractor,estado_analisis,coincidencias)
           VALUES (?,?,?,?,?,?,?,?)""",
        [
            ("P1", "https://example/1", "2026-01-01", "01/01/2026", "Convocatoria", "1", "OK", 1),
            ("P2", "https://example/2", "2026-01-02", "02/01/2026", "Convocatoria", "1", "OK", 1),
        ],
    )
    con.executemany(
        """INSERT INTO oposiciones(
               oposicion_id,num_plazas,puesto,puesto_normalizado,administracion,
               escala,subescala,clase,sistema,turno,fecha_boe,fecha_boe_original,
               enlace,publicacion_id,version_extractor)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [
            (1, 2, "Personal laboral fijo", "Personal laboral fijo", "Ayuntamiento", "--", "--", "--", "Oposición", "Libre", "2026-01-01", "01/01/2026", "https://example/1", "P1", "1"),
            (2, 1, "Técnico de Administración General", "Técnico de Administración General", "Ayuntamiento", "Administración General", "Técnica", "--", "Oposición", "Libre", "2026-01-02", "02/01/2026", "https://example/2", "P2", "1"),
        ],
    )
    con.commit()
    con.close()
    return ruta


def _estado(ruta):
    con = base_datos.conectar(ruta, readonly=True)
    try:
        return (
            base_datos.leer_metadata(con),
            [tuple(f) for f in con.execute("SELECT oposicion_id,puesto FROM oposiciones ORDER BY oposicion_id")],
            [f[1] for f in con.execute("PRAGMA table_info(oposiciones)")],
        )
    finally:
        con.close()


def test_dry_run_doble_es_determinista_y_no_escribe(tmp_path):
    ruta = _base_v6(tmp_path)
    antes = _estado(ruta)
    plan = migrar_tipo_personal.validar_dry_run_doble(ruta)
    resultado = migrar_tipo_personal.migrar(
        ruta, tmp_path / "backups", tmp_path / "informe", dry_run=True
    )
    assert plan["sha256"] == resultado["sha256_resultado"]
    assert plan["recuentos"]["Laboral"] == 1
    assert plan["recuentos"]["Funcionario"] == 1
    assert _estado(ruta) == antes
    assert (tmp_path / "informe" / "tipo_personal_v1_detalle.csv").is_file()


def test_migracion_persiste_catalogo_metadata_y_preserva_datos(tmp_path):
    ruta = _base_v6(tmp_path)
    antes = _estado(ruta)[1]
    resultado = migrar_tipo_personal.migrar(
        ruta, tmp_path / "backups", tmp_path / "informe"
    )
    assert resultado["actualizada"] is True
    assert resultado["invariantes_antes"] == resultado["invariantes_despues"]
    con = base_datos.conectar(ruta)
    try:
        metadata = base_datos.leer_metadata(con)
        assert metadata["schema_version"] == "7"
        assert metadata["data_version"] == "11"
        assert metadata["tipo_personal_version"] == "tipo-personal-v1"
        assert dict(con.execute("SELECT oposicion_id,tipo_personal FROM oposiciones")) == {
            1: "Laboral", 2: "Funcionario"
        }
        assert [tuple(f) for f in con.execute("SELECT oposicion_id,puesto FROM oposiciones ORDER BY oposicion_id")] == antes
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("UPDATE oposiciones SET tipo_personal='Inválido' WHERE oposicion_id=1")
    finally:
        con.close()


def test_segunda_ejecucion_y_recalculo_son_idempotentes(tmp_path):
    ruta = _base_v6(tmp_path)
    migrar_tipo_personal.migrar(ruta, tmp_path / "backups", tmp_path / "informe")
    segunda = migrar_tipo_personal.migrar(ruta, tmp_path / "backups", tmp_path / "informe")
    recalculo = migrar_tipo_personal.recalcular(ruta, dry_run=True)
    assert segunda["actualizada"] is False
    assert recalculo["filas_que_cambiarian"] == 0
    assert recalculo["data_version_antes"] == recalculo["data_version_despues"] == "11"


def test_error_revierte_columna_metadata_y_datos(tmp_path, monkeypatch):
    ruta = _base_v6(tmp_path)
    antes = _estado(ruta)

    def fallar(conexion, plan):
        conexion.execute("UPDATE oposiciones SET puesto='ALTERADO' WHERE oposicion_id=1")
        raise RuntimeError("fallo inyectado")

    monkeypatch.setattr(migrar_tipo_personal, "_persistir_plan", fallar)
    with pytest.raises(RuntimeError, match="fallo inyectado"):
        migrar_tipo_personal.migrar(ruta, tmp_path / "backups", tmp_path / "informe")
    assert _estado(ruta) == antes


def test_recalculo_corrige_solo_tipo_personal_y_solo_una_vez(tmp_path):
    ruta = _base_v6(tmp_path)
    migrar_tipo_personal.migrar(ruta, tmp_path / "backups", tmp_path / "informe")
    con = base_datos.conectar(ruta)
    con.execute("UPDATE oposiciones SET tipo_personal='No determinado' WHERE oposicion_id=1")
    con.commit()
    con.close()
    antes = _estado(ruta)[1]
    resultado = migrar_tipo_personal.recalcular(
        ruta, dry_run=False, directorio_backup=tmp_path / "backups"
    )
    assert resultado["filas_que_cambiarian"] == 1
    assert resultado["data_version_despues"] == "12"
    assert _estado(ruta)[1] == antes
    assert migrar_tipo_personal.recalcular(ruta, dry_run=True)["filas_que_cambiarian"] == 0
