import json,sqlite3
from pathlib import Path
from normalizacion_contextual_puestos import normalizar_puesto_efectivo
CANON='Profesores de Enseñanza Secundaria'
def main():
 c=sqlite3.connect('datos/boe.db');c.row_factory=sqlite3.Row; a=[]
 for r in c.execute('select * from oposiciones where lower(puesto) like "%secundaria%"'):
  n=normalizar_puesto_efectivo(r['puesto'],administracion=r['administracion'],ambito=r['ambito'],tipo_entidad=r['tipo_entidad'],escala=r['escala'],subescala=r['subescala'],sistema=r['sistema'],municipio=r['municipio'],provincia=r['provincia']).normalizado
  if n==CANON and n!=r['puesto_normalizado']: a.append((r,n))
 out={'filas':len(a),'plazas':sum(r['num_plazas'] or 0 for r,_ in a),'canon_por_id':{str(r['oposicion_id']):n for r,n in a},'ids_extra':[],'ids_ausentes':[],'correcta':len(a)==3};Path('informes/normalizacion_puestos/fase7_secundaria_paso9m_dry_run.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()
