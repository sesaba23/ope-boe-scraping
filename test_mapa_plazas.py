import pytest
import pandas as pd

import mapa_plazas
from mapa_plazas import buscar_municipio, generar_mapa_municipios


@pytest.mark.parametrize(
    "nombre, esperado",
    [
        ("Calp", "Calp/Calpe"),
        ("A Coruña", "Coruña (A)"),
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


def test_buscar_municipio_desde_otro_directorio(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    resultado = buscar_municipio("A Coruña")

    assert resultado is not None
    assert resultado["Municipio"] == "Coruña (A)"


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
    assert resultado_coruna["Municipio"] == "Coruña (A)"
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
