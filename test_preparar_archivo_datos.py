import warnings

import pandas as pd
import pytest
from pandas.core.strings.accessor import StringMethods

import preparar_archivo_datos
from fechas import convertir_fecha
from preparar_archivo_datos import combinar_dataframes, prepara_data_frame_mostrar_resultados


@pytest.fixture(autouse=True)
def simular_conversion_fechas(monkeypatch):
    fechas_iso = {
        "2 de enero de 2025": "2025/01/02",
        "3 de enero de 2025": "2025/01/03",
    }
    monkeypatch.setattr(
        preparar_archivo_datos, "convertir_fecha", lambda fecha: fechas_iso[fecha]
    )


def crear_dataframe():
    return pd.DataFrame(
        [
            {"Fecha_boe": "2 de enero de 2025", "Puesto": "Ingeniero Industrial"},
            {"Fecha_boe": "3 de enero de 2025", "Puesto": "Auxiliar Administrativo"},
        ]
    )


def crear_convocatoria(**cambios):
    convocatoria = {
        "Puesto": "Ingeniero",
        "Fecha_boe": "2 de enero de 2025",
        "Administración": "Ayuntamiento de Ejemplo",
        "Enlace": "https://www.boe.es/ejemplo",
        "Num_plazas": 1,
        "Turno": "Libre",
        "Sistema": "Oposición",
        "Escala": "Administración Especial",
        "Subescala": "Técnica",
        "Clase": "Superior",
    }
    convocatoria.update(cambios)
    return convocatoria


def combinar_convocatorias(*convocatorias):
    return combinar_dataframes(
        pd.DataFrame(convocatorias).to_dict(orient="list"),
        {"Código": []},
        pd.DataFrame(),
        pd.DataFrame({"Código": []}),
    )[0]


def test_combinar_dataframes_elimina_filas_identicas():
    convocatoria = crear_convocatoria()

    resultado = combinar_convocatorias(convocatoria, convocatoria.copy())

    assert len(resultado) == 1


def test_combinar_dataframes_conserva_convocatorias_con_distinto_turno():
    resultado = combinar_convocatorias(
        crear_convocatoria(), crear_convocatoria(Turno="Discapacidad")
    )

    assert len(resultado) == 2


def test_combinar_dataframes_conserva_convocatorias_con_distinto_numero_plazas():
    resultado = combinar_convocatorias(
        crear_convocatoria(), crear_convocatoria(Num_plazas=2)
    )

    assert len(resultado) == 2


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("Sistema", "Concurso-oposición"),
        ("Escala", "Administración General"),
        ("Subescala", "Administrativa"),
        ("Clase", "Auxiliar"),
    ],
)
def test_combinar_dataframes_conserva_diferencias_en_campos_identificativos(
    campo, valor
):
    resultado = combinar_convocatorias(
        crear_convocatoria(), crear_convocatoria(**{campo: valor})
    )

    assert len(resultado) == 2


def test_filtrado_no_modifica_dataframe_original_y_mantiene_resultado():
    df_original = crear_dataframe()

    resultado = prepara_data_frame_mostrar_resultados(
        "ingeniero industrial", df_original, ["2025/01/01", "2025/01/03"]
    )

    assert "Fecha_dt" not in df_original.columns
    assert resultado["Puesto"].tolist() == ["Ingeniero Industrial"]


def test_filtrado_con_objetos_datetime_reales(monkeypatch):
    monkeypatch.setattr(preparar_archivo_datos, "convertir_fecha", convertir_fecha)
    df_original = crear_dataframe()

    resultado = prepara_data_frame_mostrar_resultados(
        "ingeniero industrial", df_original, ["2025/01/01", "2025/01/03"]
    )

    assert pd.api.types.is_datetime64_any_dtype(resultado["Fecha_dt"])
    assert resultado["Puesto"].tolist() == ["Ingeniero Industrial"]


@pytest.mark.parametrize("fecha_invalida", ["--", "", "fecha corrupta"])
def test_filtrado_excluye_fechas_invalidas_sin_modificar_fecha_original(
    monkeypatch, fecha_invalida
):
    monkeypatch.setattr(preparar_archivo_datos, "convertir_fecha", convertir_fecha)
    df_original = pd.DataFrame(
        [
            {"Fecha_boe": "2 de enero de 2025", "Puesto": "Ingeniero válido"},
            {"Fecha_boe": fecha_invalida, "Puesto": "Ingeniero inválido"},
        ]
    )

    resultado = prepara_data_frame_mostrar_resultados(
        "ingeniero", df_original, ["2025/01/01", "2025/01/03"]
    )

    assert resultado["Puesto"].tolist() == ["Ingeniero válido"]
    assert df_original["Fecha_boe"].tolist() == ["2 de enero de 2025", fecha_invalida]
    assert "Fecha_dt" not in df_original.columns


def test_filtrado_no_modifica_configuracion_global_de_warnings():
    filtros_antes = list(warnings.filters)

    prepara_data_frame_mostrar_resultados(
        "ingeniero", crear_dataframe(), ["2025/01/01", "2025/01/03"]
    )

    assert warnings.filters == filtros_antes


def test_warnings_se_restauran_si_el_filtrado_lanza_excepcion(monkeypatch):
    filtros_antes = list(warnings.filters)

    def lanzar_error(*args, **kwargs):
        raise RuntimeError("Error simulado durante el filtrado")

    monkeypatch.setattr(StringMethods, "contains", lanzar_error)

    with pytest.raises(RuntimeError, match="Error simulado durante el filtrado"):
        prepara_data_frame_mostrar_resultados(
            "ingeniero", crear_dataframe(), ["2025/01/01", "2025/01/03"]
        )

    assert warnings.filters == filtros_antes
