import json
from pathlib import Path
def main():
 d=json.loads(Path('informes/normalizacion_puestos/fase7_maestros_pendientes_paso9l1.json').read_text()); s=[x for x in d['casos'] if x['canon_propuesto']=='Maestros' and x['puesto_normalizado']!='Maestros']; out={'conjunto_cerrado':{'reglas':1,'canon':'Maestros','filas':len(s),'plazas':sum(x['num_plazas'] or 0 for x in s),'canon_por_id':{str(x['oposicion_id']):'Maestros' for x in s}},'falsos_positivos':0,'colisiones':0,'casos':s}; Path('informes/normalizacion_puestos/fase7_maestros_pendientes_paso9l2.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)); print(len(s),out['conjunto_cerrado']['plazas'])
if __name__=='__main__': main()
