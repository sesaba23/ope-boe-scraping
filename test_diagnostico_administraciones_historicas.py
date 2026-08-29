import pandas as pd
import pytest

from diagnostico_administraciones_historicas import (
    crear_indice_municipios,
    cargar_catalogo,
    detectar_administracion,
    resolver_entidad,
)


@pytest.mark.parametrize(("entidad", "municipio", "provincia"), [
    ("Torredelcampo (Jaén)", "Torredelcampo", "Jaén"),
    ("Torrent (Valencia)", "Torrent", "Valencia/València"),
    ("Santa Eulària des Riu (Illes Balears)", "Santa Eulària des Riu", "Illes Balears"),
    ("El Puig de Santa Maria (Valencia/València)", "Puig de Santa Maria, el", "Valencia/València"),
    ("Vila Joiosa/Villajoyosa (Alicante/Alacant)", "Vila Joiosa, la/Villajoyosa", "Alicante/Alacant"),
    ("Garafía (Santa Cruz de Tenerife)", "Garafía", "Santa Cruz de Tenerife"),
    ("Palma (Illes Balears)", "Palma", "Illes Balears"),
    ("Granada (Granada)", "Granada", "Granada"),
    ("Calahorra (La Rioja)", "Calahorra", "La Rioja"),
    ("Sanxenxo (Pontevedra)", "Sanxenxo", "Pontevedra"),
    ("Adeje (Santa Cruz de Tenerife)", "Adeje", "Santa Cruz de Tenerife"),
])
def test_catalogo_oficial_resuelve_regresiones_reales(entidad, municipio, provincia):
    indice = crear_indice_municipios(cargar_catalogo())
    resultado = resolver_entidad(entidad, indice)
    assert resultado[:2] == (municipio, provincia)
    assert resultado[-1] == "ALTA"


def test_detecta_ayuntamiento_real_presente_en_datos_historicos():
    dato = detectar_administracion("Ayuntamiento de Ciudad Real, referente a la convocatoria")
    assert dato == {
        "tipo_administracion": "AYUNTAMIENTO",
        "administracion_detectada": "Ayuntamiento de Ciudad Real",
        "entidad_extraida": "Ciudad Real",
    }


def test_detecta_las_cuatro_familias_explicitas():
    assert detectar_administracion("Diputación Provincial de Toledo")["tipo_administracion"] == "DIPUTACION_PROVINCIAL"
    assert detectar_administracion("Diputación de Barcelona")["tipo_administracion"] == "DIPUTACION"
    assert detectar_administracion("Universidad de Salamanca")["tipo_administracion"] == "UNIVERSIDAD"


def test_resolucion_exacta_y_ambigua_sin_coincidencia_difusa():
    catalogo = pd.DataFrame([
        {"Población": "Ciudad Real", "Provincia": "Ciudad Real"},
        {"Población": "Villa", "Provincia": "Uno"},
        {"Población": "Villa", "Provincia": "Dos"},
    ])
    indice = crear_indice_municipios(catalogo)
    assert resolver_entidad("Ciudad Real", indice)[:2] == ("Ciudad Real", "Ciudad Real")
    assert resolver_entidad("Villa", indice)[2:] == ("CATALOGO_MUNICIPIOS_AMBIGUO", "AMBIGUA")
    assert resolver_entidad("No Existe", indice)[2:] == ("CATALOGO_MUNICIPIOS_SIN_COINCIDENCIA", "NO_RESUELTA")


def test_resuelve_provincia_parentetica_real_sin_lista_manual():
    catalogo = pd.DataFrame([
        {"Población": "Gijón", "Provincia": "Asturias"},
        {"Población": "Gijón", "Provincia": "Otra"},
    ])
    municipio, provincia, _, confianza = resolver_entidad("Gijón (Asturias)", crear_indice_municipios(catalogo))
    assert (municipio, provincia, confianza) == ("Gijón", "Asturias", "ALTA")
