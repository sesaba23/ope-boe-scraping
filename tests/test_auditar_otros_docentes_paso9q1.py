import json
def test_otros_reconciliado():
 d=json.load(open('informes/normalizacion_puestos/fase7_otros_docentes_paso9q1.json')); assert sum(d['familias'].values())==d['universo']['filas']
