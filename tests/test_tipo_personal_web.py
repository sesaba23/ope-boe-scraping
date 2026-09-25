from pathlib import Path
import sqlite3
import pytest

from consultas_boe import buscar_oposiciones, opciones_busqueda, resumen_mapa_oposiciones
from web_estadisticas import crear_app


RUTA_PRODUCTIVA = Path(__file__).parents[1] / "datos" / "boe.db"


def test_catalogo_y_filtro_repetido_se_aplican_en_la_consulta_compartida():
    opciones = opciones_busqueda(RUTA_PRODUCTIVA)
    assert opciones["tipos_personal"] == [
        "Funcionario", "Laboral", "Estatutario", "Universitario",
        "Militar", "Otros", "No determinado",
    ]
    resultado = buscar_oposiciones(RUTA_PRODUCTIVA, tipo_personal=["Funcionario", "Laboral"], tamano_pagina=3)
    assert resultado["total"] > 0
    assert {fila["tipo_personal"] for fila in resultado["filas"]} <= {"Funcionario", "Laboral"}
    assert buscar_oposiciones(RUTA_PRODUCTIVA, tamano_pagina=1)["total"] == 109429
    assert buscar_oposiciones(RUTA_PRODUCTIVA, tipo_personal=list(opciones["tipos_personal"]), tamano_pagina=1)["total"] == 109429


@pytest.mark.parametrize("categoria", ["Funcionario", "Laboral", "Estatutario", "Universitario", "Militar", "Otros", "No determinado"])
def test_cada_categoria_web_reconcilia_con_sql_directo(categoria):
    conexion = sqlite3.connect(f"file:{RUTA_PRODUCTIVA}?mode=ro", uri=True)
    esperado = conexion.execute("SELECT COUNT(*) FROM oposiciones WHERE tipo_personal = ?", (categoria,)).fetchone()[0]
    conexion.close()
    assert buscar_oposiciones(RUTA_PRODUCTIVA, tipo_personal=[categoria], tamano_pagina=1)["total"] == esperado


def test_mapa_reutiliza_el_mismo_filtro_de_tipo_personal():
    funcionario = resumen_mapa_oposiciones(RUTA_PRODUCTIVA, tipo_personal=["Funcionario"])
    laboral = resumen_mapa_oposiciones(RUTA_PRODUCTIVA, tipo_personal=["Laboral"])
    assert funcionario["resumen"]["convocatorias"] > 0
    assert laboral["resumen"]["convocatorias"] > 0
    assert funcionario["resumen"]["convocatorias"] != laboral["resumen"]["convocatorias"]


def test_listado_html_conserva_checkboxes_y_tipo_en_la_ficha():
    cliente = crear_app(RUTA_PRODUCTIVA).test_client()
    respuesta = cliente.get("/oposiciones?tipo_personal=Funcionario&tipo_personal=Laboral&ver_todas=1")
    assert respuesta.status_code == 200
    html = respuesta.get_data(as_text=True)
    assert 'name="tipo_personal"' in html
    assert 'value="Funcionario"' in html
    assert 'Tipo de personal' in html


def test_api_mapa_y_estadisticas_aceptan_tipo_personal_repetido():
    cliente = crear_app(RUTA_PRODUCTIVA).test_client()
    mapa = cliente.get("/api/oposiciones/mapa?tipo_personal=Funcionario&tipo_personal=Laboral")
    assert mapa.status_code == 200
    estadisticas = cliente.get("/api/estadisticas?tipo_personal=Funcionario&tipo_personal=Laboral")
    assert estadisticas.status_code == 200
    assert estadisticas.get_json()["filtros"]["tipo_personal"] == ["Funcionario", "Laboral"]


def test_tipo_personal_desconocido_se_rechaza():
    cliente = crear_app(RUTA_PRODUCTIVA).test_client()
    respuesta = cliente.get("/api/oposiciones/mapa?tipo_personal=Inventado")
    assert respuesta.status_code == 400
