import json
from pathlib import Path


INF = Path(__file__).parents[1] / "informes" / "normalizacion_puestos"


def test_paso76_cubre_exclusivamente_b_restantes():
    informe = json.loads((INF / "fase8_paso76_auditoria_b_restantes.json").read_text())
    assert informe["universo"] == {"filas": 1957, "plazas": 3686.0}
    assert informe["cobertura"] == {"ids_universo": 1957, "ids_clasificados": 1957, "ids_perdidos": 0, "ids_duplicados": 0}
    assert informe["A_NUEVO"] == {"filas": 0, "plazas": 0, "conjuntos": 0}
    assert informe["generalizables_seguros"] == []


def test_paso76_fingerprint_y_negativos():
    informe = json.loads((INF / "fase8_paso76_auditoria_b_restantes.json").read_text())
    assert informe["fingerprint1"] == informe["fingerprint2"]
    assert informe["decision"] == "PASO77_NO_APLICABLE_PASO78_SIN_APLICACION"
