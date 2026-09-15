from scripts.audit.aplicar_normalizacion_psicologia_paso8_63 import CANON, VARIANTES, plan
from normalizacion_puestos import _clave


def test_plan_psicologia_es_dinamico_y_solo_incluye_el_conjunto_a():
    filas = plan()
    assert all(fila["puesto_normalizado_anterior"] != fila["puesto_normalizado_nuevo"] for fila in filas)
    assert all(fila["canon"] == CANON and _clave(fila["puesto"]) in VARIANTES for fila in filas)
