from scripts.audit.aplicar_normalizacion_tecnicos_informaticos_paso8_48 import CANONES, plan


def test_plan_tecnicos_informaticos_es_dinamico_y_acotado():
    filas = plan()
    assert all(fila['puesto_normalizado_anterior'] != fila['puesto_normalizado_nuevo'] for fila in filas)
    assert {fila['canon'] for fila in filas} <= CANONES
