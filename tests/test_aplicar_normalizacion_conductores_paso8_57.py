from scripts.audit.aplicar_normalizacion_conductores_paso8_57 import plan
def test_plan_conductores_es_dinamico_y_acotado():
    assert all(x['canon']=='Conductor' for x in plan())
