from scripts.audit.auditar_correccion_actualizacion_cobertura_paso8_12 import ejecutar

def test_fecha_historica_no_se_desvia_silenciosamente_en_mock():
    r=ejecutar(salida='/tmp/fase8_paso12.json')
    assert r['seleccion_extractor']=='historico'
    assert r['llamada_capturada']['fechas_explicitamente']==['2004/01/01']
    assert r['correccion_aplicada'] is True
