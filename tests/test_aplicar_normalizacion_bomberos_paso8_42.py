from scripts.audit.aplicar_normalizacion_bomberos_paso8_42 import plan

def test_plan_bomberos_es_dinamico_y_coherente_con_gate():
    gate, filas=plan()
    assert len(filas)==gate['cambios_reales_recalculables']['filas']
    assert all(f['puesto_normalizado_anterior'] != f['puesto_normalizado_nuevo'] for f in filas)
    assert {f['canon'] for f in filas} <= {'Bombero','Bombero-Conductor'}
