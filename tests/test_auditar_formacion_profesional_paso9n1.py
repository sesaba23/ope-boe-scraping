import json
def test_universo_fp_auditado():
 d=json.load(open('informes/normalizacion_puestos/fase7_formacion_profesional_paso9n1.json'))
 assert d['universo']['filas']==54
 assert sum(d['clasificacion'].values())==54
