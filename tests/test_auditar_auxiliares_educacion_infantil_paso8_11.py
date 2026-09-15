from scripts.audit.auditar_auxiliares_educacion_infantil_paso8_11 import _cat, ejecutar
def test_clasifica_variantes_sin_fusionarlas():
    assert _cat('Auxiliar de Educación Infantil') == 'AUXILIAR_EDUCACION_INFANTIL_EXPLICITO'
    assert _cat('Auxiliar de Escuela Infantil') == 'AUXILIAR_ESCUELA_INFANTIL'
    assert _cat('Auxiliar de Guardería') == 'AUXILIAR_GUARDERIA'
    assert _cat('Técnico Auxiliar de Educación Infantil') == 'AUXILIAR_TECNICO'
def test_auditoria_es_reproducible_y_conservadora():
    r=ejecutar(salida='/tmp/fase8_paso11_aux.json')
    assert r['reconciliacion']['iguales']
    assert r['reconciliacion']['diferencia_simetrica']==[]
    assert r['conjunto_seguro']['reglas']==[]
