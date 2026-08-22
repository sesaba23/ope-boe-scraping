from datetime import datetime

import pandas as pd
import pytest

import preparar_archivo_datos
from trazabilidad import (
    VERSION_EXTRACTOR,
    añadir_trazabilidad_convocatorias,
    enriquecer_historico_oposiciones,
    extraer_publicacion_id,
    necesita_reprocesamiento,
)


def test_extrae_identificador_oficial_de_publicacion():
    enlace = "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-10463"

    assert extraer_publicacion_id(enlace) == "BOE-A-2026-10463"


def test_extrae_id_con_otros_parametros_en_la_url():
    enlace = "https://www.boe.es/diario_boe/txt.php?lang=es&id=BOE-A-2026-10463&origen=web"

    assert extraer_publicacion_id(enlace) == "BOE-A-2026-10463"


def test_url_sin_id_devuelve_nulo():
    assert extraer_publicacion_id("https://www.boe.es/diario_boe/txt.php?lang=es") is None


def test_id_invalido_devuelve_nulo():
    enlace = "https://www.boe.es/diario_boe/txt.php?id=10463"

    assert extraer_publicacion_id(enlace) is None


@pytest.mark.parametrize(
    "version",
    ["legacy", None, "", "desconocida", "0", "1.5"],
)
def test_version_legacy_vacia_o_invalida_necesita_reprocesamiento(version):
    assert necesita_reprocesamiento(version, "1")


def test_version_actual_no_necesita_reprocesamiento():
    assert not necesita_reprocesamiento("1", "1")


def test_version_anterior_necesita_reprocesamiento_con_comparacion_numerica():
    assert necesita_reprocesamiento("1", "2")
    assert necesita_reprocesamiento("2", "10")
    assert not necesita_reprocesamiento("10", "2")


def test_enriquece_historico_sin_modificar_columnas_ni_dataframe_original():
    original = pd.DataFrame(
        {
            "Num_plazas": [2],
            "Puesto": ["Ingeniero"],
            "Enlace": [
                "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-10463"
            ],
        }
    )
    copia = original.copy(deep=True)

    resultado = enriquecer_historico_oposiciones(original)

    assert resultado.columns.tolist() == [
        "Num_plazas",
        "Puesto",
        "Enlace",
        "Publicacion_ID",
        "Version_extractor",
        "Fecha_analisis",
    ]
    assert resultado.loc[0, "Publicacion_ID"] == "BOE-A-2026-10463"
    assert resultado.loc[0, "Version_extractor"] == "legacy"
    assert pd.isna(resultado.loc[0, "Fecha_analisis"])
    pd.testing.assert_frame_equal(original, copia)


def test_nuevas_convocatorias_reciben_version_y_fecha_comun():
    resultados = [{"Puesto": "Ingeniero"}, {"Puesto": "Arquitecto"}]
    copia = [resultado.copy() for resultado in resultados]
    momento = datetime(2026, 8, 22, 12, 34, 56)
    enlace = "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-10463"

    enriquecidos = añadir_trazabilidad_convocatorias(resultados, enlace, momento)

    assert [fila["Version_extractor"] for fila in enriquecidos] == [
        VERSION_EXTRACTOR,
        VERSION_EXTRACTOR,
    ]
    assert [fila["Fecha_analisis"] for fila in enriquecidos] == [
        "2026-08-22 12:34:56",
        "2026-08-22 12:34:56",
    ]
    assert all(fila["Publicacion_ID"] == "BOE-A-2026-10463" for fila in enriquecidos)
    assert resultados == copia


def test_historico_con_trazabilidad_conserva_sus_valores():
    original = pd.DataFrame(
        {
            "Puesto": ["Ingeniero"],
            "Enlace": ["https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-1"],
            "Publicacion_ID": ["BOE-A-2026-1"],
            "Version_extractor": ["0"],
            "Fecha_analisis": ["2026-01-01 10:00:00"],
        }
    )

    resultado = enriquecer_historico_oposiciones(original)

    pd.testing.assert_frame_equal(resultado, original)


def test_carga_solo_enriquece_oposiciones_y_no_cambia_otras_hojas(
    monkeypatch, tmp_path
):
    ruta = tmp_path / "BOE-oposiciones.xlsx"
    busquedas = pd.DataFrame({"Código": ["codigo"]})
    errores = pd.DataFrame(
        {"Fecha": ["2026-08-22"], "Tipo de error": ["Error"], "Enlace Web": ["url"]}
    )
    oposiciones = pd.DataFrame(
        {
            "Puesto": ["Ingeniero"],
            "Enlace": ["https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-10463"],
        }
    )
    with pd.ExcelWriter(ruta, engine="openpyxl") as writer:
        busquedas.to_excel(writer, sheet_name="Búsquedas", index=False)
        oposiciones.to_excel(writer, sheet_name="Oposiciones", index=False)
        errores.to_excel(writer, sheet_name="Log-errores", index=False)
    monkeypatch.chdir(tmp_path)

    hojas = preparar_archivo_datos.preparar_excel_y_dataframes()

    pd.testing.assert_frame_equal(hojas["Búsquedas"], busquedas)
    pd.testing.assert_frame_equal(hojas["Log-errores"], errores)
    assert hojas["Oposiciones"].columns.tolist() == [
        "Puesto",
        "Enlace",
        "Publicacion_ID",
        "Version_extractor",
        "Fecha_analisis",
    ]
