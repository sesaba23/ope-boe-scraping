import sqlite3

import pandas as pd
import pytest

import base_datos


CATALOGO = {
    "Funcionario", "Laboral", "Estatutario", "Universitario",
    "Militar", "Otros", "No determinado",
}


def _schema7(tmp_path, *, version="tipo-personal-v1"):
    ruta = tmp_path / "boe.db"
    con = base_datos.conectar(ruta)
    base_datos.crear_esquema(con)
    con.execute("ALTER TABLE oposiciones ADD COLUMN tipo_personal TEXT NOT NULL DEFAULT 'No determinado' CHECK(tipo_personal IN ('Funcionario','Laboral','Estatutario','Universitario','Militar','Otros','No determinado'))")
    base_datos.guardar_metadata(con, schema_version=7, data_version=78)
    con.execute("INSERT INTO metadata(clave,valor) VALUES ('tipo_personal_version',?)", (version,))
    con.commit()
    con.close()
    return ruta


def _frames(rows, *, fecha="2026-01-01"):
    publicaciones = pd.DataFrame([
        {
            "Publicacion_ID": row["Publicacion_ID"], "Enlace": f"https://example/{row['Publicacion_ID']}",
            "Fecha_BOE": fecha, "Titulo_original": row.get("titulo", "Convocatoria"),
            "Fecha_ultimo_analisis": None, "Version_extractor": "test",
            "Estado_analisis": "OK", "Coincidencias": 1,
            "Departamento_BOE": None, "Administracion_resuelta": None,
            "Familia_administrativa": None, "Estado_resolucion": None,
            "Metodo_resolucion": None, "Confianza_resolucion": None,
            "Version_resolucion": None,
        }
        for row in rows
    ])
    oposiciones = pd.DataFrame([
        {
            "Num_plazas": 1, "Puesto": row["Puesto"], "Administración": row.get("Administración", "Ayuntamiento"),
            "Escala": row.get("Escala", "--"), "Subescala": row.get("Subescala", "--"), "Clase": row.get("Clase", "--"),
            "Sistema": "Oposición", "Turno": "Libre", "Fecha_boe": fecha,
            "Publicación": "", "Enlace": f"https://example/{row['Publicacion_ID']}",
            "Municipio": "", "Provincia": "", "Latitud": None, "Longitud": None,
            "Habitantes": None, "Publicacion_ID": row["Publicacion_ID"],
            "Version_extractor": "test", "Fecha_analisis": None,
        }
        for row in rows
    ])
    cobertura = pd.DataFrame([{
        "Fecha": fecha, "Estado": "consultado", "Version_extractor": "test",
        "Fecha_ultima_consulta": "2026-01-02", "Numero_publicaciones": len(rows),
    }])
    return {
        "Publicaciones": publicaciones, "Oposiciones": oposiciones,
        "Cobertura": cobertura, "Búsquedas": pd.DataFrame(columns=["Código"]),
        "Log-errores": pd.DataFrame(columns=["Fecha", "Tipo de error", "Enlace Web"]),
    }


def _stored(ruta):
    con = base_datos.conectar(ruta, readonly=True)
    try:
        return dict(con.execute("SELECT tipo_personal,COUNT(*) FROM oposiciones GROUP BY tipo_personal"))
    finally:
        con.close()


def test_altas_reales_persisten_todas_las_categorias(tmp_path):
    ruta = _schema7(tmp_path)
    rows = [
        {"Publicacion_ID": "P1", "Puesto": "Funcionario de carrera"},
        {"Publicacion_ID": "P2", "Puesto": "Personal laboral fijo"},
        {"Publicacion_ID": "P3", "Puesto": "Profesor Titular de Universidad"},
        {"Publicacion_ID": "P4", "Puesto": "Oficiales de los Cuerpos Generales de los Ejércitos"},
        {"Publicacion_ID": "P5", "Puesto": "Personal estatutario fijo de los Servicios de Salud"},
        {"Publicacion_ID": "P6", "Puesto": "Director de Coro de personal eventual"},
        {"Publicacion_ID": "P7", "Puesto": "Trabajador Social"},
    ]
    datos = _frames(rows)
    con = base_datos.conectar(ruta)
    with base_datos.transaccion(con):
        base_datos.insertar_publicaciones(con, datos["Publicaciones"])
        base_datos.insertar_oposiciones(con, datos["Oposiciones"])
    con.close()
    assert set(_stored(ruta)) == CATALOGO
    assert _stored(ruta) == {
        "Funcionario": 1, "Laboral": 1, "Universitario": 1,
        "Militar": 1, "Estatutario": 1, "Otros": 1, "No determinado": 1,
    }


def test_prioridades_se_persisten_desde_el_pipeline(tmp_path):
    ruta = _schema7(tmp_path)
    rows = [
        {"Publicacion_ID": "P1", "Puesto": "Personal laboral fijo", "Administración": "Universidades"},
        {"Publicacion_ID": "P2", "Puesto": "Funcionario de carrera", "Administración": "Universidades"},
        {"Publicacion_ID": "P3", "Puesto": "Personal laboral fijo", "Escala": "Administración General"},
        {"Publicacion_ID": "P4", "Puesto": "Policía Local con reserva de una plaza para militares profesionales de tropa y marinería", "Escala": "Administración Especial", "Subescala": "Servicios Especiales", "Clase": "Policía Local"},
        {"Publicacion_ID": "P5", "Puesto": "Enfermero de hospital", "Administración": "Servicio de Salud"},
    ]
    datos = _frames(rows)
    con = base_datos.conectar(ruta)
    with base_datos.transaccion(con):
        base_datos.insertar_publicaciones(con, datos["Publicaciones"])
        base_datos.insertar_oposiciones(con, datos["Oposiciones"])
    con.close()
    assert _stored(ruta) == {"Universitario": 2, "Laboral": 1, "Funcionario": 1, "No determinado": 1}


def test_actualizacion_recalcula_y_cambio_irrelevante_no_cambia_resultado(tmp_path):
    ruta = _schema7(tmp_path)
    datos = _frames([{"Publicacion_ID": "P1", "Puesto": "Auxiliar Administrativo"}])
    primero = base_datos.persistir_lote_principal(ruta, datos, "2026-01-01", "2026-01-01", tmp_path / "backups")
    assert primero["cambios"] and primero["data_version"] == 79
    datos["Oposiciones"].loc[0, "Puesto"] = "Personal laboral fijo"
    segundo = base_datos.persistir_lote_principal(ruta, datos, "2026-01-01", "2026-01-01", tmp_path / "backups")
    assert segundo["cambios"] and segundo["data_version"] == 80
    assert _stored(ruta) == {"Laboral": 1}
    datos["Oposiciones"].loc[0, "Latitud"] = 40.4
    tercero = base_datos.persistir_lote_principal(ruta, datos, "2026-01-01", "2026-01-01", tmp_path / "backups")
    assert tercero["cambios"] and tercero["data_version"] == 81
    assert _stored(ruta) == {"Laboral": 1}


def test_version_incompatible_exige_migracion_explicita(tmp_path):
    ruta = _schema7(tmp_path, version="tipo-personal-v2")
    datos = _frames([{"Publicacion_ID": "P1", "Puesto": "Funcionario de carrera"}])
    con = base_datos.conectar(ruta)
    with pytest.raises(base_datos.EspejoSQLiteError, match="versiones incompatibles"):
        base_datos.insertar_oposiciones(con, datos["Oposiciones"])
    con.close()
    assert _stored(ruta) == {}


def test_error_de_clasificacion_revierte_toda_la_transaccion(tmp_path, monkeypatch):
    ruta = _schema7(tmp_path)
    datos = _frames([
        {"Publicacion_ID": "P1", "Puesto": "Funcionario de carrera"},
        {"Publicacion_ID": "P2", "Puesto": "Personal laboral fijo"},
    ])
    original = base_datos.clasificar_tipo_personal
    llamadas = 0

    def fallar_en_segunda(*args, **kwargs):
        nonlocal llamadas
        llamadas += 1
        if llamadas == 2:
            raise RuntimeError("fallo de clasificación")
        return original(*args, **kwargs)

    monkeypatch.setattr(base_datos, "clasificar_tipo_personal", fallar_en_segunda)
    con = base_datos.conectar(ruta)
    with pytest.raises(RuntimeError, match="fallo de clasificación"):
        with base_datos.transaccion(con):
            base_datos.insertar_publicaciones(con, datos["Publicaciones"])
            base_datos.insertar_oposiciones(con, datos["Oposiciones"])
    con.close()
    assert _stored(ruta) == {}
