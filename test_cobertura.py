from datetime import datetime

import pandas as pd
from openpyxl import Workbook, load_workbook

import preparar_archivo_datos
from cobertura import (
    COLUMNAS_COBERTURA,
    normalizar_cobertura,
    registrar_cobertura,
)


def test_crea_registro_con_columnas_en_orden_y_fecha_estable():
    resultado = registrar_cobertura(
        pd.DataFrame(),
        "2026/08/20",
        "consultado",
        8,
        datetime(2026, 8, 22, 12, 34, 56),
    )

    assert resultado.columns.tolist() == COLUMNAS_COBERTURA
    assert resultado.iloc[0].to_dict() == {
        "Fecha": "2026-08-20",
        "Estado": "consultado",
        "Version_extractor": "1",
        "Fecha_ultima_consulta": "2026-08-22 12:34:56",
        "Numero_publicaciones": 8,
    }


def test_actualiza_fecha_existente_sin_duplicarla_y_error_se_sustituye():
    inicial = registrar_cobertura(
        pd.DataFrame(), "2026-08-20", "error", momento="primer intento"
    )

    resultado = registrar_cobertura(
        inicial, "2026-08-20", "consultado", 3, momento="segundo intento"
    )

    assert len(resultado) == 1
    assert resultado.iloc[0]["Estado"] == "consultado"
    assert resultado.iloc[0]["Numero_publicaciones"] == 3
    assert resultado.iloc[0]["Fecha_ultima_consulta"] == "segundo intento"


def test_error_posterior_preserva_cobertura_correcta_y_actualiza_intento():
    inicial = registrar_cobertura(
        pd.DataFrame(), "2026-08-20", "sin_edicion", 0, momento="correcta"
    )

    resultado = registrar_cobertura(
        inicial, "2026-08-20", "error", momento="fallida"
    )

    assert len(resultado) == 1
    assert resultado.iloc[0]["Estado"] == "sin_edicion"
    assert resultado.iloc[0]["Version_extractor"] == "1"
    assert resultado.iloc[0]["Numero_publicaciones"] == 0
    assert resultado.iloc[0]["Fecha_ultima_consulta"] == "fallida"


def test_registro_y_normalizacion_no_modifican_dataframe_original():
    original = pd.DataFrame(
        [{"Fecha": "2026-08-20", "Estado": "error"}]
    )
    copia = original.copy(deep=True)

    registrar_cobertura(original, "2026-08-20", "consultado", 1)
    normalizar_cobertura(original)

    pd.testing.assert_frame_equal(original, copia)


def test_libro_sin_cobertura_la_crea_vacia_sin_reconstruir_historico(
    monkeypatch, tmp_path
):
    ruta = tmp_path / "BOE-oposiciones.xlsx"
    with pd.ExcelWriter(ruta) as writer:
        pd.DataFrame({"Código": ["histórico"]}).to_excel(
            writer, sheet_name="Búsquedas", index=False
        )
        pd.DataFrame({"Puesto": ["Ingeniero"]}).to_excel(
            writer, sheet_name="Oposiciones", index=False
        )
        pd.DataFrame(columns=["Fecha", "Tipo de error", "Enlace Web"]).to_excel(
            writer, sheet_name="Log-errores", index=False
        )
    monkeypatch.chdir(tmp_path)

    hojas = preparar_archivo_datos.preparar_excel_y_dataframes()

    assert hojas["Cobertura"].empty
    assert hojas["Cobertura"].columns.tolist() == COLUMNAS_COBERTURA


def test_escritura_atomica_incluye_cobertura_y_mantiene_busquedas_oculta(
    monkeypatch, tmp_path
):
    ruta = tmp_path / "BOE-oposiciones.xlsx"
    libro = Workbook()
    libro.active.title = "Búsquedas"
    libro.create_sheet("Oposiciones")
    libro.create_sheet("Log-errores")
    libro.save(ruta)
    monkeypatch.chdir(tmp_path)
    cobertura = registrar_cobertura(
        pd.DataFrame(), "2026-08-20", "consultado", 2
    )

    preparar_archivo_datos.guardar_excel(
        pd.DataFrame({"Puesto": ["Ingeniero"]}),
        pd.DataFrame({"Código": ["codigo"]}),
        pd.DataFrame(columns=["Fecha", "Tipo de error", "Enlace Web"]),
        pd.DataFrame(),
        cobertura,
    )

    comprobacion = load_workbook(ruta, read_only=True)
    assert "Cobertura" in comprobacion.sheetnames
    assert comprobacion["Búsquedas"].sheet_state == "hidden"
    comprobacion.close()
    guardada = pd.read_excel(ruta, sheet_name="Cobertura")
    assert guardada.columns.tolist() == COLUMNAS_COBERTURA
    assert guardada.loc[0, "Numero_publicaciones"] == 2
