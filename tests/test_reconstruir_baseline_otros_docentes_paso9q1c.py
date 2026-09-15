import json
def test_baseline_canónico():
 d=json.load(open('informes/normalizacion_puestos/fase7_otros_docentes_paso9q1c_baseline.json')); assert d['baseline_canonico_valido']; assert d['diferencia_simetrica']==0
