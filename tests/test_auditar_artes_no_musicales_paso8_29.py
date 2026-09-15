import hashlib
from pathlib import Path

from scripts.audit.auditar_artes_no_musicales_paso8_29 import auditar


def test_auditoria_artes_no_musicales_read_only_y_gate():
    db = Path("datos/boe.db")
    antes = hashlib.sha256(db.read_bytes()).hexdigest()
    resultado = auditar()
    despues = hashlib.sha256(db.read_bytes()).hexdigest()
    assert antes == despues
    assert resultado["sqlite_inmutable"] is True
    assert resultado["reconstruccion"]["filas"] == 5
    assert resultado["reconstruccion"]["plazas"] == 11
    assert resultado["reconstruccion"]["solo_paso20"] == []
    assert resultado["reconstruccion"]["solo_paso29"] == []
    assert resultado["gate_global_paso19"]["cambios_reales_recalculables"] == 0
    assert resultado["gate_global_paso19"]["discrepancias_contextuales_no_recalculables"] == 329
    assert resultado["gate_global_paso19"]["discrepancias_no_clasificables_automaticamente"] == 0


def test_universo_detallado_no_duplica_ids_y_documenta_denominaciones():
    resultado = auditar()
    registros = resultado["registros"]
    assert len({fila["id"] for fila in registros}) == len(registros)
    assert len(resultado["denominaciones"]) == 4
    assert resultado["fotocomposicion"] == []
    assert resultado["conjuntos_A"] == []
    assert all(fila["reproducible"] is False for fila in resultado["anomalias_historicas"])
