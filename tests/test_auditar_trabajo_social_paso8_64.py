from scripts.audit.auditar_trabajo_social_paso8_64 import auditar
def test_paso64_reconcilia_trabajo_social_y_separa_asistente():
 r=auditar(); assert r['universo_reconstruido']['filas']==496; assert r['taxonomia']['ASISTENTE_SOCIAL']['filas'] >= 0
