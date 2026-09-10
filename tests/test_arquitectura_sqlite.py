import ast
import importlib
from pathlib import Path

import pytest


MODULOS_PRODUCTIVOS = (
    "plazasboe",
    "cargar_historico_boe",
    "estadisticas",
    "web_estadisticas",
    "mapa_plazas",
)

APIS_LECTURA_EXCEL = {"read_excel", "ExcelFile", "load_workbook"}


@pytest.mark.parametrize("nombre", MODULOS_PRODUCTIVOS)
def test_modulo_productivo_no_lee_excel(nombre):
    """Comprueba llamadas/imports, no simples coincidencias en comentarios."""
    modulo = importlib.import_module(nombre)
    arbol = ast.parse(Path(modulo.__file__).read_text(encoding="utf-8"))

    llamadas = {
        nodo.func.attr
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
    }
    imports = {
        alias.name
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.ImportFrom)
        for alias in nodo.names
    }
    assert not APIS_LECTURA_EXCEL & (llamadas | imports)


@pytest.mark.parametrize("nombre", MODULOS_PRODUCTIVOS)
def test_modulo_productivo_importa_sin_excel_historico(nombre, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert not (tmp_path / "BOE-oposiciones.xlsx").exists()
    assert importlib.reload(importlib.import_module(nombre))
    assert not (tmp_path / "BOE-oposiciones.xlsx").exists()
