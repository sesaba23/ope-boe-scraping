from diagnostico_origen_administracion import (
    construir_muestra_persistida, extraer_administracion_concreta,
    seleccionar_muestra, seleccionar_submuestra,
)
import pandas as pd


def _datos():
    publicaciones = pd.DataFrame([
        {"Publicacion_ID": f"BOE-A-{ano}-{n}", "Fecha_BOE": f"{ano}-01-01", "Titulo_original": ""}
        for ano, inicio in ((2004, 0), (2012, 10), (2020, 20)) for n in range(inicio, inicio + 10)
    ])
    oposiciones = pd.DataFrame([
        {"Publicacion_ID": x, "Administración": "Administración Local"}
        for x in publicaciones["Publicacion_ID"]
    ])
    return publicaciones, oposiciones


def test_muestra_reproducible_y_distribuida_en_tres_tramos():
    publicaciones, oposiciones = _datos()
    primera = seleccionar_muestra(publicaciones, oposiciones)
    assert primera == seleccionar_muestra(publicaciones, oposiciones)
    assert len(primera) == 30
    assert [sum(f"-{ano}-" in x for x in primera) for ano in (2004, 2012, 2020)] == [10, 10, 10]


def test_detecta_solo_familias_concretas_explicitas_reales():
    assert extraer_administracion_concreta("Resolución del Ayuntamiento de Ciudad Real") == "Ayuntamiento de Ciudad Real"
    assert extraer_administracion_concreta("Administración Local") == ""
    assert extraer_administracion_concreta("Diputación Provincial de Valencia") == "Diputación Provincial de Valencia"
    assert extraer_administracion_concreta(
        "Resolución de 12 de febrero de 2008, del Consorcio Hospitalario Provincial de Castellón, referente a la convocatoria"
    ) == "Consorcio Hospitalario Provincial de Castellón"


def test_muestra_persistida_conserva_vacio_del_estado_sin_inventar_metadatos():
    publicaciones, oposiciones = _datos()
    muestra = construir_muestra_persistida(publicaciones, oposiciones, ["BOE-A-2004-0"], {})
    assert muestra[0]["titulo_persistido"] == ""
    assert muestra[0]["metadatos_estado"] == {}
    assert muestra[0]["estado_json"] == "NO_ENCONTRADO"


def test_submuestra_reparte_las_consultas_entre_los_tres_tramos():
    publicaciones, oposiciones = _datos()
    muestra = construir_muestra_persistida(publicaciones, oposiciones, seleccionar_muestra(publicaciones, oposiciones), {})
    seleccion = seleccionar_submuestra(muestra, 10)
    assert len(seleccion) == 10
    assert [sum(x["ano"] == ano for x in seleccion) for ano in (2004, 2012, 2020)] == [4, 3, 3]
