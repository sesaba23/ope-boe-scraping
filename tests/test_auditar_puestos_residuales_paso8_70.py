from scripts.audit.auditar_puestos_residuales_paso8_70 import auditar
def test_paso70_inventaria_sin_mutar():assert auditar()['universo_residual_inicial']['filas']>0
