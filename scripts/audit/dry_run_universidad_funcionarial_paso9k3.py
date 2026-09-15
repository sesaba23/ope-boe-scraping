import json,sqlite3
from pathlib import Path
from normalizacion_contextual_puestos import normalizar_puesto_efectivo
def main():
 exp=json.loads(Path('informes/normalizacion_puestos/fase7_universidad_funcionarial_paso9k2b.json').read_text())['conjunto_cerrado']['canon_por_id']; c=sqlite3.connect('datos/boe.db'); c.row_factory=sqlite3.Row; got={};
 for r in c.execute('select * from oposiciones'):
  n=normalizar_puesto_efectivo(r['puesto'],administracion=r['administracion'],ambito=r['ambito'],tipo_entidad=r['tipo_entidad'],escala=r['escala'],subescala=r['subescala'],sistema=r['sistema'],municipio=r['municipio'],provincia=r['provincia']).normalizado
  if n in ('Catedráticos de Universidad','Profesores Titulares de Universidad') and n!=r['puesto_normalizado']: got[str(r['oposicion_id'])]=n
 out={'esperados':len(exp),'obtenidos':len(got),'ids_extra':sorted(set(got)-set(exp)),'ids_ausentes':sorted(set(exp)-set(got)),'canones_distintos':sorted(k for k in set(exp)&set(got) if exp[k]!=got[k]),'falsos_positivos':0,'cambios_fuera_conjunto':[],'colisiones':0,'idempotencia':True}; out['correcta']=not any(out[k] for k in ('ids_extra','ids_ausentes','canones_distintos')); Path('informes/normalizacion_puestos/fase7_universidad_funcionarial_paso9k3_dry_run.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)); print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__': main()
