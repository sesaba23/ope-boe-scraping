import hashlib
from pathlib import Path

from scripts.audit.auditar_taller_artistico_ocupacional_paso8_32 import auditar


def test_universo_paso32_reconstruido_y_sqlite_inmutable():
    db = Path("datos/boe.db")
    antes = hashlib.sha256(db.read_bytes()).hexdigest()
    informe = auditar()
    despues = hashlib.sha256(db.read_bytes()).hexdigest()
    assert informe["universo"]["filas"] == 14
    assert informe["universo"]["plazas"] == 19
    assert informe["universo"]["denominaciones"] == 13
    assert informe["reconciliacion_paso20"]["faltantes"] == []
    assert informe["reconciliacion_paso20"]["inesperados"] == []
    assert antes == despues
    assert informe["sqlite_modificada"] is False
    assert informe["normalizador_modificado"] is False


def test_paso32_no_declara_conjuntos_a_y_preserva_semantica():
    informe = auditar()
    assert informe["conjuntos_A"] == []
    assert informe["simulacion_A"] == {"esperados": [], "obtenidos": [], "faltantes": [], "inesperados": []}
    assert informe["clasificacion_A"]["filas"] == 0
    assert informe["clasificacion_C"]["filas"] + informe["clasificacion_D"]["filas"] == 14
    assert any(f["clasificacion"] == "D" for f in informe["filas"])
    assert informe["gate_paso19"]["cambios_reales_recalculables"] == 0
    assert informe["gate_paso19"]["discrepancias_contextuales_no_recalculables"] == 329
    assert informe["gate_paso19"]["discrepancias_no_clasificables_automaticamente"] == 0


def test_denominaciones_y_repeticiones_sin_fuzzy_matching():
    informe = auditar()
    assert informe["definicion_universo"]["sin_fuzzy_matching"] is True
    assert len(informe["inventario_denominaciones"]) == 13
    artes = [x for x in informe["inventario_denominaciones"] if "Artes Plásticas" in x["denominacion"]]
    assert artes and sum(x["filas"] for x in artes) == 3 and sum(x["plazas"] for x in artes) == 7
    assert all(len(f["id"] if isinstance(f["id"], list) else str(f["id"])) > 0 for f in informe["filas"])
