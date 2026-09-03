import subprocess
import sys

from test_consultas_boe import ruta_busqueda


def test_cli_consulta_motor_compartido_y_sin_resultados(ruta_busqueda):
    resultado = subprocess.run(
        [sys.executable, "buscar_oposiciones.py", "ingeniero", "--bd", str(ruta_busqueda), "--provincia", "Madrid"],
        check=False, capture_output=True, text=True,
    )
    assert resultado.returncode == 0
    assert "Resultados: 1" in resultado.stdout
    assert "Ingeniero Técnico Industrial" in resultado.stdout
    vacio = subprocess.run(
        [sys.executable, "buscar_oposiciones.py", "inexistente", "--bd", str(ruta_busqueda)],
        check=False, capture_output=True, text=True,
    )
    assert vacio.returncode == 0
    assert vacio.stdout.strip() == "No se encontraron oposiciones."


def test_cli_argumento_incorrecto_devuelve_error():
    resultado = subprocess.run(
        [sys.executable, "buscar_oposiciones.py", "--tamano", "200"],
        check=False, capture_output=True, text=True,
    )
    assert resultado.returncode == 2
