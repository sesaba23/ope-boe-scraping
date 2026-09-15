from scripts.audit.aplicar_normalizacion_enfermeria_paso8_51 import plan


def test_plan_enfermeria_es_dinamico_y_acotado():
    filas = plan()
    assert all(fila['puesto_normalizado_anterior'] != fila['puesto_normalizado_nuevo'] for fila in filas)
    assert all(fila['canon'] == 'Enfermero' for fila in filas)
