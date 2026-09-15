import json
from pathlib import Path
def main():
 out={'familia_seleccionada':None,'conjunto_cerrado':{'reglas':[],'filas':0,'plazas':0,'canon_por_id':{}},'falsos_positivos':0,'colisiones':0,'motivo':'El bloque Otros es heterogéneo; no existe una familia homogénea con regla segura que preserve especialidades y excluya técnicos, monitores, laborales y profesionales no docentes.'};Path('informes/normalizacion_puestos/fase7_otros_docentes_paso9q2.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()
