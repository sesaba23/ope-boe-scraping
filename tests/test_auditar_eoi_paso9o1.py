import json

def test_eoi_audit():
    d=json.load(open('informes/normalizacion_puestos/fase7_eoi_paso9o1.json'))
    assert sum(d['clasificacion'].values()) == d['universo']['filas']
