"""Protecciones de hermeticidad para la suite."""
import hashlib
from pathlib import Path

import pytest


RUTA_EXCEL_REAL = Path(__file__).parent / "BOE-oposiciones.xlsx"


def _firma(ruta):
    datos = ruta.read_bytes()
    estado = ruta.stat()
    return hashlib.sha256(datos).hexdigest(), estado.st_size, estado.st_mtime_ns


@pytest.fixture(autouse=True)
def no_modificar_excel_real(request):
    """Identifica el test responsable aun cuando use defaults productivos."""
    antes = _firma(RUTA_EXCEL_REAL)
    yield
    despues = _firma(RUTA_EXCEL_REAL)
    assert despues == antes, (
        f"{request.node.nodeid} modificó el Excel real; use tmp_path y una ruta explícita. "
        f"Antes={antes}; después={despues}"
    )
