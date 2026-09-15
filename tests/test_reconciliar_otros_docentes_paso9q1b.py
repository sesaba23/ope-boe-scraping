import json
def test_reconciliacion_deja_claro_bloqueo():
 d=json.load(open('informes/normalizacion_puestos/fase7_otros_docentes_paso9q1b_reconciliacion.json'))
 assert d['reconciliacion_correcta'] is False
 assert 'IDS_OTROS_9P' in d['diferencia']['motivo']
