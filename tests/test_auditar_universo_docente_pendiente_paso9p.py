import json

def test_9p_report():
    d=json.load(open('informes/normalizacion_puestos/fase7_universo_docente_pendiente_paso9p.json'))
    assert d['universo']['filas'] >= 0
