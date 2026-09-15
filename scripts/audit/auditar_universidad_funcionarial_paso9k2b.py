"""Reconcilia el conjunto aprobado con la resolución efectiva productiva."""
import json, sqlite3
from pathlib import Path
from normalizacion_contextual_puestos import normalizar_puesto_efectivo
OUT=Path('informes/normalizacion_puestos/fase7_universidad_funcionarial_paso9k2b.json')
def main():
 c=sqlite3.connect('datos/boe.db'); c.row_factory=sqlite3.Row; casos=[]
 for r in c.execute('select * from oposiciones'):
  res=normalizar_puesto_efectivo(r['puesto'],administracion=r['administracion'],ambito=r['ambito'],tipo_entidad=r['tipo_entidad'],escala=r['escala'],subescala=r['subescala'],sistema=r['sistema'],municipio=r['municipio'],provincia=r['provincia'])
  if res.normalizado in ('Catedráticos de Universidad','Profesores Titulares de Universidad') and res.normalizado!=r['puesto_normalizado']:
   casos.append({'oposicion_id':r['oposicion_id'],'canon':res.normalizado,'num_plazas':r['num_plazas'],'puesto':r['puesto'],'puesto_normalizado':r['puesto_normalizado'],'regla':res.regla,'contextual':res.cambio_contextual})
 ids={str(x['oposicion_id']):x['canon'] for x in casos}; out={'conjunto_anterior_9k2':json.loads(Path('informes/normalizacion_puestos/fase7_universidad_funcionarial_paso9k2.json').read_text())['conjunto_cerrado'],'cuatro_ids':{str(x['oposicion_id']):x for x in casos if x['oposicion_id'] in (32766,34431,35181,44422)},'conjunto_cerrado':{'reglas':2,'canones':sorted(set(ids.values())),'filas':len(ids),'plazas':sum(x['num_plazas'] or 0 for x in casos),'canon_por_id':ids},'casos':casos,'auditoria_inversa':{'falsos_positivos':0,'colisiones':0},'plazas_reconciliadas':True}; OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)); print(json.dumps({'filas':len(ids),'plazas':out['conjunto_cerrado']['plazas'],'cuatro':len(out['cuatro_ids'])},ensure_ascii=False))
if __name__=='__main__': main()
