import sqlite3

import pytest

import base_datos
import migrar_esquema_sqlite as migracion


def _base_v2(ruta, puestos=("Ingeniero/a Técnico/a Industrial", "Arquitecto")):
    conexion = base_datos.conectar(ruta)
    esquema_v2 = base_datos.ESQUEMA.replace("    puesto_normalizado TEXT,\n", "")
    conexion.executescript(esquema_v2)
    conexion.executescript(base_datos.INDICES)
    conexion.executemany(
        "INSERT INTO metadata(clave, valor) VALUES (?, ?)",
        [
            ("schema_version", "2"),
            ("data_version", "7"),
            ("created_at", "2026-01-01T00:00:00"),
            ("updated_at", "2026-01-01T00:00:00"),
        ],
    )
    for indice, puesto in enumerate(puestos, 1):
        pid = f"BOE-A-{indice}"
        conexion.execute(
            "INSERT INTO publicaciones VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, f"https://x/{indice}", "2026-01-01", "20260101", None,
             None, "1", "con_coincidencias", 1, None, None, None, None, None,
             None, None),
        )
        conexion.execute(
            """INSERT INTO oposiciones(
                num_plazas,puesto,administracion,escala,subescala,clase,sistema,
                turno,fecha_boe,fecha_boe_original,enlace,publicacion_id,version_extractor
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (1, puesto, "A", "--", "--", "--", "--", "--", "2026-01-01",
             "20260101", f"https://x/{indice}", pid, "1"),
        )
    conexion.commit(); conexion.close()
    return ruta


def test_migracion_v2_v3_preserva_original_y_normaliza(tmp_path):
    ruta = _base_v2(tmp_path / "boe.db")
    resultado = migracion.migrar_v2_v3(ruta, tmp_path / "backups")
    conexion = base_datos.conectar(ruta, readonly=True)
    try:
        filas = conexion.execute(
            "SELECT puesto, puesto_normalizado FROM oposiciones ORDER BY oposicion_id"
        ).fetchall()
        metadata = dict(conexion.execute("SELECT clave, valor FROM metadata"))
        columnas = [fila[1] for fila in conexion.execute("PRAGMA table_info(oposiciones)")]
        assert filas == [
            ("Ingeniero/a Técnico/a Industrial", "Ingeniero Técnico Industrial"),
            ("Arquitecto", "Arquitecto"),
        ]
        assert "puesto_normalizado" in columnas
        assert metadata["schema_version"] == "3"
        assert metadata["data_version"] == "8"
        assert base_datos.integrity_check(conexion) == ["ok"]
        assert base_datos.foreign_key_check(conexion) == []
    finally:
        conexion.close()
    assert resultado["actualizada"] is True
    assert resultado["auditoria"]["filas"] == 2
    assert resultado["backup"]


def test_migracion_v3_es_idempotente(tmp_path):
    ruta = _base_v2(tmp_path / "boe.db")
    migracion.migrar_v2_v3(ruta, tmp_path / "backups")
    antes = base_datos.hash_archivo(ruta)
    resultado = migracion.migrar_v2_v3(ruta, tmp_path / "otros-backups")
    assert resultado == {"actualizada": False, "schema_version": "3", "data_version": "8"}
    assert base_datos.hash_archivo(ruta) == antes
    assert not (tmp_path / "otros-backups").exists()


def test_migracion_revierte_si_falla_normalizacion(tmp_path, monkeypatch):
    ruta = _base_v2(tmp_path / "boe.db")
    monkeypatch.setattr(
        migracion, "normalizar_puesto",
        lambda _: (_ for _ in ()).throw(RuntimeError("fallo deliberado")),
    )
    with pytest.raises(RuntimeError, match="fallo deliberado"):
        migracion.migrar_v2_v3(ruta, tmp_path / "backups")
    conexion = sqlite3.connect(ruta)
    try:
        metadata = dict(conexion.execute("SELECT clave, valor FROM metadata"))
        columnas = [fila[1] for fila in conexion.execute("PRAGMA table_info(oposiciones)")]
    finally:
        conexion.close()
    assert metadata["schema_version"] == "2"
    assert metadata["data_version"] == "7"
    assert "puesto_normalizado" not in columnas


def test_v2_da_error_productivo_con_comando_explicito(tmp_path):
    ruta = _base_v2(tmp_path / "boe.db")
    with pytest.raises(base_datos.EspejoSQLiteError, match="migrar_esquema_sqlite.py"):
        base_datos.validar_base_principal(ruta)
