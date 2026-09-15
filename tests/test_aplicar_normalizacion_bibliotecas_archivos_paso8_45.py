from scripts.audit.aplicar_normalizacion_bibliotecas_archivos_paso8_45 import plan


def test_plan_bibliotecas_es_dinamico_y_coherente_con_gate():
    gate, filas = plan()
    assert len(filas) == gate['cambios_reales_recalculables']['filas']
    assert all(fila['puesto_normalizado_anterior'] != fila['puesto_normalizado_nuevo'] for fila in filas)
    assert {fila['canon'] for fila in filas} <= {'Bibliotecario', 'Auxiliar de Biblioteca'}
