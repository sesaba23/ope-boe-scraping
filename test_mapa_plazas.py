import pytest
from mapa_plazas import buscar_municipio


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
