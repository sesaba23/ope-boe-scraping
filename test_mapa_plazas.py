import pytest
import pandas as pd
import requests

import mapa_plazas
from mapa_plazas import (
    buscar_municipio,
    enriquecer_filas_sin_coordenadas,
    generar_mapa_municipios,
    normalizar_nombre_municipal,
)
from preparar_archivo_datos import combinar_dataframes


@pytest.mark.parametrize(
    "nombre, esperado",
    [
        ("Calp", "Calp/Calpe"),
        ("A Coruña", "Coruña, A"),
        ("Elx/Elche", "Elche/Elx"),
        ("Elche/Elx", "Elche/Elx"),
    ],
)
def test_buscar_municipio(nombre, esperado):
    resultado = buscar_municipio(nombre)
    assert resultado is not None, f"No se encontró el municipio para '{nombre}'"
    assert (
        esperado.lower() in resultado["Municipio"].lower()
    ), f"Esperado '{esperado}' en '{resultado['Municipio']}'"


def test_buscar_municipio_prioriza_municipio_entre_parentesis():
    resultado = buscar_municipio(
        "Cabildo Insular de Tenerife (Santa Cruz de Tenerife)"
    )

    assert resultado == {
        "Municipio": "Santa Cruz de Tenerife",
        "Provincia": "Santa Cruz de Tenerife",
        "Latitud": 28.46981,
        "Longitud": -16.25486,
        "Habitantes": 222417,
    }


def test_provincia_ambigua_no_asigna_su_capital_a_otro_territorio():
    resultado = buscar_municipio(
        "Cabildo Insular de La Gomera (Santa Cruz de Tenerife)"
    )

    assert resultado is None or resultado["Municipio"] != "Santa Cruz de Tenerife"


def test_referencia_provincial_ambigua_no_asigna_lleida_capital():
    resultado = buscar_municipio("Consejo General de Arán (Lleida)")

    assert resultado is None or resultado["Municipio"] != "Lleida"


def test_buscar_municipio_normal_mantiene_el_resultado():
    assert buscar_municipio("A Coruña") == {
        "Municipio": "Coruña, A",
        "Provincia": "A Coruña",
        "Latitud": 43.37149478,
        "Longitud": -8.395825599,
        "Habitantes": 251277,
    }


@pytest.mark.parametrize(
    "administracion, municipio, provincia, latitud, longitud, habitantes",
    [
        (
            "Ayuntamiento de Castell d'Aro (Girona)",
            "Castell d'Aro, Platja d'Aro i s'Agaró",
            "Girona",
            41.8175818,
            3.067323841,
            12889,
        ),
        (
            "Ayuntamiento de L'Alcora (Castellón/Castelló)",
            "Alcora, l'",
            "Castellón/Castelló",
            40.07434197,
            -0.213046923,
            10646,
        ),
        (
            "Ayuntamiento de L'Eliana (Valencia/València)",
            "Eliana, l'",
            "Valencia/València",
            39.56657901,
            -0.530183987,
            19952,
        ),
        (
            "Ayuntamiento de L'Espluga de Francolí (Tarragona)",
            "Espluga de Francolí, L'",
            "Tarragona",
            41.39655369,
            1.104462437,
            3892,
        ),
        (
            "Ayuntamiento de L'Olleria (Valencia/València)",
            "Olleria, l'",
            "Valencia/València",
            38.91172401,
            -0.546653364,
            8928,
        ),
        (
            "Ayuntamiento de La Ràpita (Tarragona)",
            "Ràpita, La",
            "Tarragona",
            40.62029937,
            0.592405252,
            16230,
        ),
        (
            "Ayuntamiento de Medina Sidonia (Cádiz)",
            "Medina Sidonia",
            "Cádiz",
            36.45606047,
            -5.927588997,
            11870,
        ),
    ],
)
def test_ayuntamientos_auditados_resuelven_con_su_provincia(
    administracion, municipio, provincia, latitud, longitud, habitantes
):
    assert buscar_municipio(administracion) == {
        "Municipio": municipio,
        "Provincia": provincia,
        "Latitud": latitud,
        "Longitud": longitud,
        "Habitantes": habitantes,
    }


def test_normalizacion_municipal_unifica_apostrofos_espacios_tildes_y_guiones():
    assert normalizar_nombre_municipal("L'Alcora") == normalizar_nombre_municipal(
        "  l’ alcóra  "
    )
    assert normalizar_nombre_municipal(
        "Medina-Sidonia"
    ) == normalizar_nombre_municipal("Medina Sidonia")
    assert normalizar_nombre_municipal("Sant Joan d´Alacant") == normalizar_nombre_municipal(
        "Sant Joan d'Alacant"
    )


def test_ayuntamiento_con_provincia_incompatible_no_se_geolocaliza():
    assert buscar_municipio("Ayuntamiento de L'Alcora (Valencia/València)") is None


def test_alias_no_se_aplica_por_coincidencia_parcial():
    assert buscar_municipio("Ayuntamiento de Castell XYZ (Girona)") is None


def test_parentesis_sin_municipio_continua_con_la_busqueda_normal():
    resultado = buscar_municipio("Ayuntamiento de Calp (convocatoria ordinaria)")

    assert resultado["Municipio"] == "Calp/Calpe"


def test_municipio_compuesto_con_preposiciones_entre_parentesis():
    resultado = buscar_municipio(
        "Diputación Provincial de Cádiz (Vejer de la Frontera)"
    )

    assert resultado["Municipio"] == "Vejer de la Frontera"


def test_municipio_entre_parentesis_tiene_prioridad_sobre_el_resto_del_texto():
    resultado = buscar_municipio("Entidad de Santa Cruz de Tenerife (Adeje)")

    assert resultado["Municipio"] == "Adeje"


def test_enriquece_fila_historica_sin_coordenadas():
    df = pd.DataFrame(
        [
            {
                "Administración": "Cabildo Insular de Tenerife "
                "(Santa Cruz de Tenerife)",
                "Municipio": pd.NA,
                "Provincia": pd.NA,
                "Latitud": pd.NA,
                "Longitud": pd.NA,
                "Habitantes": pd.NA,
            }
        ]
    )

    resultado = enriquecer_filas_sin_coordenadas(df)

    assert resultado.loc[0, "Municipio"] == "Santa Cruz de Tenerife"
    assert resultado.loc[0, "Provincia"] == "Santa Cruz de Tenerife"
    assert resultado.loc[0, "Latitud"] == 28.46981
    assert resultado.loc[0, "Longitud"] == -16.25486
    assert resultado.loc[0, "Habitantes"] == 222417


def test_enriquecimiento_no_modifica_fila_con_coordenadas_validas(monkeypatch):
    df = pd.DataFrame(
        [
            {
                "Administración": "Cabildo Insular de Tenerife "
                "(Santa Cruz de Tenerife)",
                "Municipio": "Municipio existente",
                "Provincia": "Provincia existente",
                "Latitud": 1.25,
                "Longitud": 2.5,
                "Habitantes": 100,
            }
        ]
    )
    monkeypatch.setattr(
        mapa_plazas,
        "buscar_municipio",
        lambda *args: pytest.fail("No debe buscar una fila ya geolocalizada"),
    )

    resultado = enriquecer_filas_sin_coordenadas(df)

    pd.testing.assert_frame_equal(resultado, df)


def test_enriquecimiento_deja_igual_administracion_no_resoluble():
    df = pd.DataFrame(
        [
            {
                "Administración": "Entidad administrativa sin municipio",
                "Municipio": pd.NA,
                "Provincia": pd.NA,
                "Latitud": pd.NA,
                "Longitud": pd.NA,
                "Habitantes": pd.NA,
            }
        ]
    )

    resultado = enriquecer_filas_sin_coordenadas(df)

    pd.testing.assert_frame_equal(resultado, df)


def test_enriquecimiento_admite_resolucion_sin_coordenadas(monkeypatch):
    df = pd.DataFrame([{
        "Administración": "Entidad municipal", "Municipio": pd.NA,
        "Provincia": pd.NA, "Latitud": pd.NA, "Longitud": pd.NA,
        "Habitantes": pd.NA,
    }])
    monkeypatch.setattr(
        mapa_plazas, "buscar_municipio",
        lambda *_: {"Municipio": "Municipio", "Provincia": "Provincia"},
    )

    resultado = enriquecer_filas_sin_coordenadas(df)

    assert resultado.loc[0, "Municipio"] == "Municipio"
    assert resultado.loc[0, "Provincia"] == "Provincia"
    assert pd.isna(resultado.loc[0, "Latitud"])


def test_enriquecimiento_no_realiza_peticiones_http(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: pytest.fail("No debe realizar peticiones HTTP"),
    )
    df = pd.DataFrame(
        [
            {
                "Administración": "Ayuntamiento de Calp",
                "Latitud": pd.NA,
                "Longitud": pd.NA,
            }
        ]
    )

    resultado = enriquecer_filas_sin_coordenadas(df)

    assert resultado.loc[0, "Municipio"] == "Calp/Calpe"


def test_enriquecimiento_no_cambia_historico_de_busquedas():
    oposiciones = pd.DataFrame(
        [
            {
                "Puesto": "Ingeniero",
                "Fecha_boe": "2 de enero de 2025",
                "Administración": "Ayuntamiento de Calp",
                "Enlace": "https://www.boe.es/ejemplo",
                "Latitud": pd.NA,
                "Longitud": pd.NA,
            }
        ]
    )
    busquedas = pd.DataFrame({"Código": ["codigo-historico"]})
    df_combinado, df_busquedas_combinado = combinar_dataframes(
        {}, {"Código": []}, oposiciones, busquedas
    )

    enriquecer_filas_sin_coordenadas(df_combinado)

    pd.testing.assert_frame_equal(df_busquedas_combinado, busquedas)


def test_buscar_municipio_desde_otro_directorio(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    resultado = buscar_municipio("A Coruña")

    assert resultado is not None
    assert resultado["Municipio"] == "Coruña, A"


def test_catalogo_municipal_se_carga_una_sola_vez(monkeypatch):
    lecturas = []
    read_csv_original = mapa_plazas.pd.read_csv

    def read_csv_contabilizado(*args, **kwargs):
        lecturas.append(args[0])
        return read_csv_original(*args, **kwargs)

    mapa_plazas._cargar_catalogo_municipios.cache_clear()
    monkeypatch.setattr(mapa_plazas.pd, "read_csv", read_csv_contabilizado)

    resultado_coruna = buscar_municipio("A Coruña")
    resultado_calp = buscar_municipio("Calp")

    assert len(lecturas) == 1
    assert resultado_coruna["Municipio"] == "Coruña, A"
    assert resultado_calp["Municipio"] == "Calp/Calpe"


def test_generar_mapa_sin_columnas_de_coordenadas(monkeypatch, tmp_path):
    df = pd.DataFrame(
        [
            {
                "Puesto": "Auxiliar Administrativo",
                "Num_plazas": 1,
                "Administración": "Ayuntamiento de Ejemplo",
                "Sistema": "Oposición",
                "Fecha_boe": "2 de enero de 2025",
                "Enlace": "https://www.boe.es/ejemplo",
            }
        ]
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mapa_plazas.webbrowser, "open", lambda *args: None)

    generar_mapa_municipios(df)

    assert (tmp_path / "mapa_municipios.html").exists()
    assert (tmp_path / "puestos_sin_coordenadas.html").exists()


def test_generar_mapa_por_defecto_consulta_sqlite_y_no_excel(monkeypatch, tmp_path):
    datos = pd.DataFrame([{
        "Puesto": "Auxiliar", "Num_plazas": "la", "Administración": None,
        "Sistema": "--", "Fecha_boe": "2025-01-01", "Enlace": "https://x",
        "Latitud": pd.NA, "Longitud": pd.NA, "Habitantes": pd.NA,
        "Municipio": None, "Provincia": None,
    }])
    llamadas = []
    monkeypatch.setattr(mapa_plazas, "oposiciones", lambda *a, **k: llamadas.append((a, k)) or datos)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mapa_plazas.webbrowser, "open", lambda *args: None)
    generar_mapa_municipios()
    assert llamadas and (tmp_path / "mapa_municipios.html").exists()


def test_html_escapa_texto_y_no_hace_navegable_un_enlace_invalido(
    monkeypatch, tmp_path
):
    df = pd.DataFrame(
        [
            {
                "Puesto": '<script>alert("x")</script>',
                "Num_plazas": "1 & 2",
                "Administración": "Entidad <prueba>",
                "Fecha_boe": '2 de enero de 2025 "especial"',
                "Enlace": "javascript:alert(1)",
                "Latitud": pd.NA,
                "Longitud": pd.NA,
            }
        ]
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mapa_plazas.webbrowser, "open", lambda *args: None)

    mapa_plazas.mostrar_puestos_sin_coordenadas(df)

    contenido = (tmp_path / "puestos_sin_coordenadas.html").read_text()
    assert '&lt;script&gt;alert(&quot;' in contenido
    assert "1 &amp; 2" in contenido
    assert "Entidad &lt;prueba&gt;" in contenido
    assert "&quot;especial&quot;" in contenido
    assert "javascript:alert(1)" not in contenido
    assert "<a href=" not in contenido
