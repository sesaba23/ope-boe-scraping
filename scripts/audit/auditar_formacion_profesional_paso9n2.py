import json
from pathlib import Path
def main():
 d=json.load(open('informes/normalizacion_puestos/fase7_formacion_profesional_paso9n1.json')); out={'conjunto_cerrado':{'filas':0,'plazas':0,'reglas':[]},'falsos_positivos':0,'colisiones':0,'motivo':'Los casos no normalizados contienen especialidades, figuras laborales, técnicos o denominaciones mixtas; no existe canon seguro que preserve la información.'};Path('informes/normalizacion_puestos/fase7_formacion_profesional_paso9n2.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()
