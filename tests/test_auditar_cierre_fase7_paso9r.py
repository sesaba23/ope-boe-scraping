import json
def test_cierre_fase7_idempotente():
 d=json.load(open('informes/normalizacion_puestos/fase7_paso9r_cierre.json')); assert d['correcta']; assert d['recaclculo_efectivo']['filas_que_cambiarian']==0
