import sqlite3

import pandas as pd
import pytest

import base_datos


def test_crear_esquema_activa_claves_foraneas_y_indices(tmp_path):
    conexion = base_datos.conectar(tmp_path / "boe.db")
    base_datos.crear_esquema(conexion)
    base_datos.crear_indices(conexion)
    assert conexion.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    tablas = {fila[0] for fila in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"publicaciones", "oposiciones", "busquedas", "cobertura", "log_errores"} <= tablas
    indices = {fila[0] for fila in conexion.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "ix_oposiciones_clave_deduplicacion" in indices
    assert base_datos.integrity_check(conexion) == ["ok"]


def test_fk_y_rollback_preservan_null_y_num_plazas_textual(tmp_path):
    conexion = base_datos.conectar(tmp_path / "boe.db")
    base_datos.crear_esquema(conexion)
    with base_datos.transaccion(conexion):
        conexion.execute("INSERT INTO publicaciones VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            "BOE-A-1", "https://x", "2026-01-01", "1 de enero de 2026", None,
            None, "1", "con_coincidencias", 1, None, None, None, None, None, None, None,
        ))
        conexion.execute("""INSERT INTO oposiciones(
            num_plazas,puesto,administracion,escala,subescala,clase,sistema,turno,
            fecha_boe,fecha_boe_original,enlace,publicacion_id,version_extractor
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            "la", "Auxiliar", None, "--", "--", "--", "--", "--",
            "2026-01-01", "1 de enero de 2026", "https://x", "BOE-A-1", "1",
        ))
    fila = conexion.execute("SELECT num_plazas, administracion FROM oposiciones").fetchone()
    assert fila == ("la", None)
    with pytest.raises(sqlite3.IntegrityError):
        with base_datos.transaccion(conexion):
            conexion.execute("""INSERT INTO oposiciones(
                puesto,administracion,escala,subescala,clase,sistema,turno,fecha_boe,
                fecha_boe_original,enlace,publicacion_id,version_extractor
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (
                "X", None, "--", "--", "--", "--", "--", "2026-01-01",
                "1 de enero de 2026", "x", "inexistente", "1",
            ))
    assert conexion.execute("SELECT count(*) FROM oposiciones").fetchone()[0] == 1
    assert base_datos.foreign_key_check(conexion) == []


def _lote(publicacion_id="BOE-A-1"):
    return {
        "Publicaciones": pd.DataFrame([{
            "Publicacion_ID": publicacion_id, "Enlace": "https://x", "Fecha_BOE": "2026-01-01",
            "Titulo_original": None, "Fecha_ultimo_analisis": None, "Version_extractor": "1",
            "Estado_analisis": "con_coincidencias", "Coincidencias": 1,
        }]),
        "Oposiciones": pd.DataFrame([{
            "Num_plazas": "la", "Puesto": "Auxiliar", "Administración": None, "Escala": "--",
            "Subescala": "--", "Clase": "--", "Sistema": "--", "Turno": "--",
            "Fecha_boe": "20260101", "Publicación": None, "Enlace": "https://x",
            "Municipio": None, "Provincia": None, "Latitud": None, "Longitud": None,
            "Habitantes": None, "Publicacion_ID": publicacion_id, "Version_extractor": "1",
            "Fecha_analisis": None,
        }]),
        "Búsquedas": pd.DataFrame({"Código": ["codigo"]}),
        "Cobertura": pd.DataFrame([{"Fecha": "2026-01-01", "Estado": "consultado", "Version_extractor": "1", "Fecha_ultima_consulta": "2026-01-01 00:00:00", "Numero_publicaciones": 1}]),
        "Log-errores": pd.DataFrame([{"Fecha": "2026-01-01 00:00:00", "Tipo de error": "x", "Enlace Web": "https://x"}]),
    }


def _base_con_lote(tmp_path):
    ruta = tmp_path / "boe.db"
    conexion = base_datos.conectar(ruta)
    base_datos.crear_esquema(conexion)
    base_datos.crear_indices(conexion)
    lote = _lote()
    with base_datos.transaccion(conexion):
        base_datos.insertar_publicaciones(conexion, lote["Publicaciones"])
        base_datos.insertar_oposiciones(conexion, lote["Oposiciones"])
        base_datos.actualizar_busquedas(conexion, lote["Búsquedas"])
        base_datos.actualizar_cobertura(conexion, lote["Cobertura"])
        base_datos.insertar_log_errores(conexion, lote["Log-errores"])
    conexion.close()
    return ruta


def test_lectura_selectiva_por_rango_preserva_texto_y_null(tmp_path):
    ruta = _base_con_lote(tmp_path)
    conexion = base_datos.conectar(ruta)
    base_datos.guardar_metadata(conexion, source_excel_hash="x")
    conexion.commit()
    with base_datos.transaccion(conexion):
        conexion.execute("UPDATE oposiciones SET fecha_boe='2025-01-01' WHERE oposicion_id=1")
        conexion.execute("UPDATE publicaciones SET fecha_boe='2025-01-01' WHERE publicacion_id='BOE-A-1'")
    datos = base_datos.cargar_para_lectura(ruta, "2026/01/01", "2026/01/01")
    assert datos["Oposiciones"].empty
    assert len(datos["Búsquedas"]) == len(datos["Log-errores"]) == 1
    datos = base_datos.cargar_para_lectura(ruta, "2025-01-01", "2025-01-01")
    fila = datos["Oposiciones"].iloc[0]
    assert fila["Num_plazas"] == "la"
    assert pd.isna(fila["Administración"])
    assert fila["Fecha_boe"] == "20260101"


def test_lote_historico_ignora_timestamps_de_auditoria(tmp_path):
    ruta = _base_con_lote(tmp_path)
    conexion = base_datos.conectar(ruta)
    base_datos.guardar_metadata(conexion, data_version=1)
    conexion.commit(); conexion.close()
    datos = base_datos.cargar_historico_para_aplicar(ruta, "2026-01-01", "2026-01-01")
    publicaciones = datos["Publicaciones"].copy()
    cobertura = datos["Cobertura"].copy()
    publicaciones.loc[:, "Fecha_ultimo_analisis"] = "2026-02-01 00:00:00"
    cobertura.loc[:, "Fecha_ultima_consulta"] = "2026-02-01 00:00:00"
    resultado = base_datos.persistir_lote_historico(
        ruta, datos["Oposiciones"].iloc[0:0], publicaciones, cobertura,
        "2026-01-01", "2026-01-01", tmp_path / "backups")
    assert resultado == {"cambios": False, "backup": None, "data_version": 1}
    assert not (tmp_path / "backups").exists()
