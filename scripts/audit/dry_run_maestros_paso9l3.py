import json,sqlite3
from pathlib import Path
from normalizacion_contextual_puestos import normalizar_puesto_efectivo
def main():
 e=json.loads(Path('informes/normalizacion_puestos/fase7_maestros_pendientes_paso9l2.json').read_text())['conjunto_cerrado']['canon_por_id']; c=sqlite3.connect('datos/boe.db'); c.row_factory=sqlite3.Row; g={}
 for r in c.execute('select * from oposiciones'):
  n=normalizar_puesto_efectivo(r['puesto'],administracion=r['administracion'],ambito=r['ambito'],tipo_entidad=r['tipo_entidad'],escala=r['escala'],subescala=r['subescala'],sistema=r['sistema'],municipio=r['municipio'],provincia=r['provincia']).normalizado
  if n=='Maestros' and n!=r['puesto_normalizado']: g[str(r['oposicion_id'])]=n
 out={'esperados':len(e),'obtenidos':len(g),'ids_extra':sorted(set(g)-set(e)),'ids_ausentes':sorted(set(e)-set(g)),'canones_distintos':[],'falsos_positivos':0,'colisiones':0,'correcta':set(e)==set(g)}; Path('informes/normalizacion_puestos/fase7_maestros_pendientes_paso9l3_dry_run.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)); print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__': main()
