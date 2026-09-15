import hashlib
from pathlib import Path

from scripts.audit.auditar_psicologia_paso8_61 import auditar


def test_paso61_reconstruye_y_no_modifica_sqlite():
    db = Path("datos/boe.db")
    antes = hashlib.sha256(db.read_bytes()).hexdigest()
    resultado = auditar()
    assert resultado["universo_reconstruido"]["filas"] == 1030
    assert resultado["universo_reconstruido"]["plazas"] == 1832
    assert resultado["reconciliacion_paso39"]["faltantes"] == []
    assert hashlib.sha256(db.read_bytes()).hexdigest() == antes


def test_paso61_no_confunde_especialidades_con_el_generico():
    resultado = auditar()
    simulacion = resultado["simulaciones_A"][0]
    assert simulacion["faltantes"] == []
    assert simulacion["inesperados"] == []
    assert resultado["psicologia_clinica"]["filas"] > 0
    assert resultado["tecnico_psicologia"]["filas"] > 0
