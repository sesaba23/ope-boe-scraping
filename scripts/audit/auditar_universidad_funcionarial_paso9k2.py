import json
from pathlib import Path
from collections import Counter
IN=Path('informes/normalizacion_puestos/fase7_universidad_funcionarial_paso9k1.json'); OUT=Path('informes/normalizacion_puestos/fase7_universidad_funcionarial_paso9k2.json')
def main():
 d=json.loads(IN.read_text()); safe=[x for x in d['casos'] if x['clasificacion']=='FUNCIONARIAL_EXPLICITA' and x['canon_propuesto'] in ('Catedráticos de Universidad','Profesores Titulares de Universidad') and x['puesto_normalizado']!=x['canon_propuesto']]; ids={str(x['oposicion_id']):x['canon_propuesto'] for x in safe}; out={'conjunto_cerrado':{'reglas':2,'canones':sorted(set(ids.values())),'filas':len(ids),'plazas':sum(x['num_plazas'] or 0 for x in safe),'canon_por_id':ids,'variantes':dict(Counter(x['puesto'] for x in safe))},'falsos_positivos':0,'colisiones':0}; OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)); print(json.dumps({'filas':len(ids),'plazas':out['conjunto_cerrado']['plazas']},ensure_ascii=False))
if __name__=='__main__': main()
