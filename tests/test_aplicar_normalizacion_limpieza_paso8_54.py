from scripts.audit.aplicar_normalizacion_limpieza_paso8_54 import CANONES,plan
def test_plan_limpieza_es_dinamico_y_acotado():
 filas=plan();assert all(f['puesto_normalizado_anterior']!=f['puesto_normalizado_nuevo'] for f in filas);assert {f['canon']for f in filas}<=CANONES
