import json

import pandas as pd
import pytest

import base_datos
import exportar_excel
import migrar_excel_sqlite as migracion


def _crear_excel(ruta, *, administracion=None):
    busquedas = pd.DataFrame({"Código": ["codigo"]})
    publicaciones = pd.DataFrame({
        "Publicacion_ID": ["BOE-A-1"], "Enlace": ["https://x"],
        "Fecha_BOE": ["1 de enero de 2026"], "Titulo_original": [None],
        "Fecha_ultimo_analisis": ["2026-01-01T10:00:00"], "Version_extractor": ["1"],
        "Estado_analisis": ["con_coincidencias"], "Coincidencias": [1],
    })
    oposiciones = pd.DataFrame({
        "Num_plazas": ["la"], "Puesto": ["Auxiliar"], "Administración": [administracion],
        "Escala": ["--"], "Subescala": ["--"], "Clase": ["--"], "Sistema": ["--"],
        "Turno": ["--"], "Fecha_boe": ["20260101"], "Publicación": [None],
        "Enlace": ["https://x"], "Municipio": [None], "Provincia": [None],
        "Latitud": [None], "Longitud": [None], "Habitantes": [None],
        "Publicacion_ID": ["BOE-A-1"], "Version_extractor": ["1"],
        "Fecha_analisis": [None],
    })
    cobertura = pd.DataFrame({"Fecha": ["2026-01-01"], "Estado": ["consultado"], "Version_extractor": ["1"], "Fecha_ultima_consulta": ["2026-01-01 10:00:00"], "Numero_publicaciones": [1]})
    errores = pd.DataFrame({"Fecha": ["2026-01-01 10:00:00"], "Tipo de error": ["prueba"], "Enlace Web": ["https://e"]})
    with pd.ExcelWriter(ruta, engine="openpyxl") as escritor:
        busquedas.to_excel(escritor, sheet_name="Búsquedas", index=False)
        oposiciones.to_excel(escritor, sheet_name="Oposiciones", index=False)
        errores.to_excel(escritor, sheet_name="Log-errores", index=False)
        publicaciones.to_excel(escritor, sheet_name="Publicaciones", index=False)
        cobertura.to_excel(escritor, sheet_name="Cobertura", index=False)


def test_migracion_fixture_es_atomica_y_auditable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    excel, destino = tmp_path / "origen.xlsx", tmp_path / "datos" / "boe.db"
    _crear_excel(excel)
    resultado = migracion.migrar(excel, destino, progreso=False)
    assert destino.exists()
    assert resultado["conteos"] == {"publicaciones": 1, "oposiciones": 1, "busquedas": 1, "cobertura": 1, "log_errores": 1}
    assert resultado["informe"]["correcta"]
    assert resultado["informe"]["semantica"]["num_plazas_no_enteros"] == ["TEXT:2:la"]
    assert (tmp_path / "informes/migracion_sqlite/auditoria_migracion_sqlite.json").exists()
    conexion = base_datos.conectar(destino)
    assert conexion.execute("SELECT fecha_boe, fecha_boe_original, administracion FROM oposiciones").fetchone() == ("2026-01-01", "20260101", None)


def test_no_reemplaza_base_existente_ni_deja_destino_ante_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    excel, destino = tmp_path / "origen.xlsx", tmp_path / "datos" / "boe.db"
    _crear_excel(excel)
    destino.parent.mkdir()
    destino.write_bytes(b"conservar")
    with pytest.raises(FileExistsError):
        migracion.migrar(excel, destino, progreso=False)
    assert destino.read_bytes() == b"conservar"
    destino.unlink()
    hojas = migracion.leer_excel(excel)
    hojas["Oposiciones"].loc[0, "Publicacion_ID"] = "BOE-A-inexistente"
    monkeypatch.setattr(migracion, "leer_excel", lambda _: hojas)
    with pytest.raises(Exception):
        migracion.migrar(excel, destino, progreso=False)
    assert not destino.exists()


def test_fingerprint_detecta_diferencia(tmp_path):
    excel = tmp_path / "origen.xlsx"
    _crear_excel(excel)
    hojas = migracion.leer_excel(excel)
    conexion = base_datos.conectar(tmp_path / "boe.db")
    base_datos.crear_esquema(conexion)
    migracion.importar(conexion, hojas, progreso=False)
    conexion.execute("UPDATE busquedas SET codigo='otro'")
    informe = migracion.auditar(hojas, conexion)
    assert not informe["correcta"]
    assert not informe["tablas"]["Búsquedas"]["equivalente"]


def test_normalizar_fechas():
    assert migracion.normalizar_fecha("20260102") == "2026-01-02"
    assert migracion.normalizar_fecha("2 de enero de 2026") == "2026-01-02"


def test_puerta_entrada_y_exportacion_excel_con_temporales(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    origen = tmp_path / "historico.xlsx"
    destino = tmp_path / "datos" / "boe.db"
    salida = tmp_path / "exportado.xlsx"
    _crear_excel(origen)

    migracion.migrar(origen, destino, progreso=False)
    conexion = base_datos.conectar(destino, readonly=True)
    try:
        metadata = dict(conexion.execute("SELECT clave, valor FROM metadata"))
        tablas = {
            fila[0]
            for fila in conexion.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert metadata["schema_version"] == "4"
        assert metadata["migration_source_filename"] == "BOE-oposiciones.xlsx"
        assert {"metadata", "oposiciones", "publicaciones", "busquedas", "cobertura", "log_errores"} <= tablas
        assert base_datos.integrity_check(conexion) == ["ok"]
        assert base_datos.foreign_key_check(conexion) == []
    finally:
        conexion.close()

    informe = exportar_excel.exportar(destino, salida)
    hojas = pd.read_excel(salida, sheet_name=None, dtype={"Num_plazas": str})
    assert informe["correcta"]
    assert list(hojas) == list(exportar_excel.CONTRATOS)
    assert hojas["Oposiciones"].columns.tolist() == list(
        exportar_excel.CONTRATOS["Oposiciones"][1]
    )
    assert hojas["Oposiciones"].loc[0, "Num_plazas"] == "la"
    assert hojas["Oposiciones"].loc[0, "Puesto_normalizado"] == "Auxiliar"
    assert pd.isna(hojas["Oposiciones"].loc[0, "Administración"])
    assert str(hojas["Oposiciones"].loc[0, "Fecha_boe"]) == "2026-01-01"
