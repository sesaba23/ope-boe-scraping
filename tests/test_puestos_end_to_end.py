import pandas as pd

import base_datos
import exportar_excel
from estadisticas import calcular_estadisticas_sqlite


def test_puesto_original_y_normalizado_recorrido_completo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ruta = tmp_path / "datos" / "boe.db"
    ruta.parent.mkdir()
    conexion = base_datos.conectar(ruta)
    base_datos.crear_esquema(conexion)
    base_datos.crear_indices(conexion)
    base_datos.guardar_metadata(conexion, data_version=1)
    conexion.commit(); conexion.close()

    publicaciones = pd.DataFrame([
        {"Publicacion_ID": pid, "Enlace": f"https://x/{pid}",
         "Fecha_BOE": "1 de enero de 2026", "Titulo_original": None,
         "Fecha_ultimo_analisis": None, "Version_extractor": "1",
         "Estado_analisis": "con_coincidencias", "Coincidencias": 1,
         "Departamento_BOE": None, "Administracion_resuelta": None,
         "Familia_administrativa": None, "Estado_resolucion": None,
         "Metodo_resolucion": None, "Confianza_resolucion": None,
         "Version_resolucion": None}
        for pid in ("BOE-A-1", "BOE-A-2")
    ])
    oposiciones = pd.DataFrame([
        {"Num_plazas": plazas, "Puesto": puesto, "Administración": "Entidad",
         "Escala": "--", "Subescala": "--", "Clase": "--", "Sistema": "--",
         "Turno": "--", "Fecha_boe": "1 de enero de 2026", "Publicación": None,
         "Enlace": f"https://x/{pid}", "Municipio": None, "Provincia": None,
         "Latitud": None, "Longitud": None, "Habitantes": None,
         "Publicacion_ID": pid, "Version_extractor": "1", "Fecha_analisis": None}
        for pid, puesto, plazas in (
            ("BOE-A-1", "Ingeniero/a Técnico/a Industrial", 1),
            ("BOE-A-2", "Ingeniero Técnico Industrial", 2),
        )
    ])
    lote = {
        "Oposiciones": oposiciones,
        "Publicaciones": publicaciones,
        "Búsquedas": pd.DataFrame(columns=["Código"]),
        "Cobertura": pd.DataFrame(columns=["Fecha", "Estado", "Version_extractor", "Fecha_ultima_consulta", "Numero_publicaciones"]),
        "Log-errores": pd.DataFrame(columns=["Fecha", "Tipo de error", "Enlace Web"]),
    }
    base_datos.persistir_lote_principal(
        ruta, lote, "2026-01-01", "2026-01-01", tmp_path / "backups"
    )

    conexion = base_datos.conectar(ruta, readonly=True)
    try:
        filas = conexion.execute(
            "SELECT puesto, puesto_normalizado FROM oposiciones ORDER BY publicacion_id"
        ).fetchall()
    finally:
        conexion.close()
    assert filas == [
        ("Ingeniero/a Técnico/a Industrial", "Ingeniero Técnico Industrial"),
        ("Ingeniero Técnico Industrial", "Ingeniero Técnico Industrial"),
    ]
    assert calcular_estadisticas_sqlite(ruta)["top_puestos"][0] == {
        "puesto": "Ingeniero Técnico Industrial", "plazas": 3
    }

    salida = tmp_path / "exportado.xlsx"
    exportar_excel.exportar(ruta, salida)
    exportadas = pd.read_excel(salida, sheet_name="Oposiciones")
    assert exportadas[["Puesto", "Puesto_normalizado"]].to_dict("records") == [
        {"Puesto": "Ingeniero/a Técnico/a Industrial", "Puesto_normalizado": "Ingeniero Técnico Industrial"},
        {"Puesto": "Ingeniero Técnico Industrial", "Puesto_normalizado": "Ingeniero Técnico Industrial"},
    ]
