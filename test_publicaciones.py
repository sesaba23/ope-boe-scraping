from datetime import datetime

import pandas as pd
from openpyxl import Workbook, load_workbook

import preparar_archivo_datos
from publicaciones import (
    COLUMNAS_PUBLICACIONES,
    crear_registro_publicacion,
    normalizar_publicaciones,
    publicaciones_desde_oposiciones,
    registrar_publicacion,
)


def _enlace(publicacion_id="BOE-A-2026-10463"):
    return f"https://www.boe.es/diario_boe/txt.php?id={publicacion_id}"


def test_crea_registros_con_y_sin_coincidencias():
    momento = datetime(2026, 8, 22, 12, 34, 56)

    con = crear_registro_publicacion(
        _enlace(), "BOE núm. 10, de 22 de agosto de 2026", "Título completo", 3, momento
    )
    sin = crear_registro_publicacion(
        _enlace("BOE-A-2026-10464"),
        "22 de agosto de 2026",
        "Otro título",
        0,
        momento,
    )

    assert list(con) == COLUMNAS_PUBLICACIONES
    assert con["Fecha_BOE"] == "22 de agosto de 2026"
    assert con["Fecha_ultimo_analisis"] == "2026-08-22 12:34:56"
    assert con["Estado_analisis"] == "con_coincidencias"
    assert con["Coincidencias"] == 3
    assert sin["Estado_analisis"] == "sin_coincidencias"
    assert sin["Coincidencias"] == 0


def test_actualiza_publicacion_sin_duplicar_y_preserva_datos_validos():
    existente = pd.DataFrame(
        [
            {
                "Publicacion_ID": "BOE-A-2026-10463",
                "Enlace": _enlace(),
                "Fecha_BOE": "21 de agosto de 2026",
                "Titulo_original": "Título conservado",
                "Fecha_ultimo_analisis": "2026-08-21 10:00:00",
                "Version_extractor": "legacy",
                "Estado_analisis": "con_coincidencias",
                "Coincidencias": 1,
            }
        ]
    )
    nuevo = {
        "Publicacion_ID": "BOE-A-2026-10463",
        "Enlace": "",
        "Fecha_BOE": pd.NA,
        "Titulo_original": "",
        "Fecha_ultimo_analisis": "2026-08-22 12:00:00",
        "Version_extractor": "1",
        "Estado_analisis": "sin_coincidencias",
        "Coincidencias": 0,
    }
    copia = existente.copy(deep=True)

    resultado = registrar_publicacion(existente, nuevo)

    assert len(resultado) == 1
    fila = resultado.iloc[0]
    assert fila["Enlace"] == _enlace()
    assert fila["Fecha_BOE"] == "21 de agosto de 2026"
    assert fila["Titulo_original"] == "Título conservado"
    assert fila["Fecha_ultimo_analisis"] == "2026-08-22 12:00:00"
    assert fila["Version_extractor"] == "1"
    assert fila["Estado_analisis"] == "sin_coincidencias"
    assert fila["Coincidencias"] == 0
    pd.testing.assert_frame_equal(existente, copia)


def test_consolida_duplicados_preexistentes_sin_perder_datos_validos():
    duplicadas = pd.DataFrame(
        [
            {
                "Publicacion_ID": "BOE-A-2026-10463",
                "Enlace": _enlace(),
                "Fecha_BOE": "22 de agosto de 2026",
                "Titulo_original": "Título conservado",
                "Fecha_ultimo_analisis": "2026-08-21 10:00:00",
                "Version_extractor": "legacy",
                "Estado_analisis": "con_coincidencias",
                "Coincidencias": 1,
            },
            {
                "Publicacion_ID": "BOE-A-2026-10463",
                "Enlace": "",
                "Fecha_BOE": "",
                "Titulo_original": "",
                "Fecha_ultimo_analisis": "2026-08-22 10:00:00",
                "Version_extractor": "1",
                "Estado_analisis": "sin_coincidencias",
                "Coincidencias": 0,
            },
        ]
    )

    resultado = normalizar_publicaciones(duplicadas)

    assert len(resultado) == 1
    assert resultado.loc[0, "Titulo_original"] == "Título conservado"
    assert resultado.loc[0, "Fecha_ultimo_analisis"] == "2026-08-22 10:00:00"


def test_reconstruye_historico_una_fila_por_publicacion_y_cuenta_coincidencias():
    oposiciones = pd.DataFrame(
        {
            "Puesto": ["Ingeniero", "Arquitecto"],
            "Enlace": [_enlace(), _enlace()],
            "Fecha_boe": ["22 de agosto de 2026"] * 2,
        }
    )

    resultado = publicaciones_desde_oposiciones(oposiciones)

    assert len(resultado) == 1
    fila = resultado.iloc[0]
    assert fila["Publicacion_ID"] == "BOE-A-2026-10463"
    assert fila["Coincidencias"] == 2
    assert fila["Estado_analisis"] == "con_coincidencias"
    assert fila["Version_extractor"] == "legacy"
    assert fila["Titulo_original"] == ""
    assert pd.isna(fila["Fecha_ultimo_analisis"])


def test_carga_crea_publicaciones_solo_desde_oposiciones(monkeypatch, tmp_path):
    ruta = tmp_path / "BOE-oposiciones.xlsx"
    busquedas = pd.DataFrame(
        {"Código": [_enlace(), _enlace("BOE-A-2026-99999")]}
    )
    oposiciones = pd.DataFrame(
        {"Puesto": ["Ingeniero"], "Enlace": [_enlace()], "Fecha_boe": ["22 de agosto de 2026"]}
    )
    errores = pd.DataFrame(columns=["Fecha", "Tipo de error", "Enlace Web"])
    with pd.ExcelWriter(ruta, engine="openpyxl") as writer:
        busquedas.to_excel(writer, sheet_name="Búsquedas", index=False)
        oposiciones.to_excel(writer, sheet_name="Oposiciones", index=False)
        errores.to_excel(writer, sheet_name="Log-errores", index=False)
    monkeypatch.chdir(tmp_path)

    hojas = preparar_archivo_datos.preparar_excel_y_dataframes()

    assert hojas["Publicaciones"]["Publicacion_ID"].tolist() == ["BOE-A-2026-10463"]


def test_guardado_atomico_incluye_publicaciones_y_conserva_hojas(monkeypatch, tmp_path):
    ruta = tmp_path / "BOE-oposiciones.xlsx"
    libro = Workbook()
    libro.active.title = "Búsquedas"
    libro.create_sheet("Oposiciones")
    libro.create_sheet("Log-errores")
    libro.save(ruta)
    monkeypatch.chdir(tmp_path)
    publicaciones = pd.DataFrame(
        [crear_registro_publicacion(_enlace(), "22 de agosto de 2026", "Título", 1)]
    )

    preparar_archivo_datos.guardar_excel(
        pd.DataFrame({"Puesto": ["Ingeniero"]}),
        pd.DataFrame({"Código": [_enlace()]}),
        pd.DataFrame(columns=["Fecha", "Tipo de error", "Enlace Web"]),
        publicaciones,
    )

    comprobacion = load_workbook(ruta, read_only=True)
    assert comprobacion.sheetnames == [
        "Búsquedas",
        "Oposiciones",
        "Log-errores",
        "Publicaciones",
    ]
    assert comprobacion["Búsquedas"].sheet_state == "hidden"
    comprobacion.close()
    guardadas = pd.read_excel(ruta, sheet_name="Publicaciones")
    assert guardadas["Publicacion_ID"].tolist() == ["BOE-A-2026-10463"]
