import json
from pathlib import Path

INF = Path(__file__).parents[1] / "informes" / "normalizacion_puestos"


def test_paso79_reconcilia_418_y_selecciona_cinco():
    p = json.loads((INF / "fase8_paso79_estado_418.json").read_text())
    assert p["familias_historicas"] == 418
    assert sum(p["estados"].values()) == 418
    assert len(p["siguiente_lote"]) == 5
    assert p["ids_perdidos"] == p["duplicados_incompatibles"] == 0


def test_paso80_cobertura_y_ruta_no_aplicable():
    p = json.loads((INF / "fase8_paso80_auditoria_lote.json").read_text())
    assert p["universo"]["ids"] == p["cobertura"]["ids_origen"] == p["cobertura"]["ids_clasificados"]
    assert p["cobertura"]["ids_perdidos"] == p["cobertura"]["ids_duplicados"] == 0
    assert p["A_NUEVO"]["filas"] == 0
    assert p["generalizables_seguros"] == []
    assert p["decision"] == "PASO81_NO_APLICABLE_PASO82_RUTA_B"


def test_paso82_cierre_es_idempotente_y_determinista():
    p = json.loads((INF / "fase8_paso82_cierre_lote.json").read_text())
    assert p["ruta"] == "RUTA_B_SIN_APLICACION"
    assert p["sqlite_modificado"] is False
    assert p["idempotencia"]["modificaciones"] == 0
    assert p["fingerprint1"] == p["fingerprint2"]
