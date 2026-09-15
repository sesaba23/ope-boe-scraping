import json,re,sqlite3
from pathlib import Path
from collections import Counter
def main():
 c=sqlite3.connect('datos/boe.db');c.row_factory=sqlite3.Row; casos=[]
 for r in c.execute('select * from oposiciones'):
  p=r['puesto'] or ''; l=p.casefold()
  if not re.search(r'maestr|profesor|docente|catedr|titular|monitor|tecnic|auxiliar|taller|universidad|secundaria|formaci[oó]n profesional|idioma',p,re.I): continue
  if re.search(r'universidad|catedr|titular|maestr|secundaria|formaci[oó]n profesional|\bfp\b|idioma',p,re.I): continue
  fam='musica' if re.search(r'm[uú]sic|instrument|piano|viol[ií]n',l) else 'artística' if re.search(r'arte|cer[aá]mica|danza|pintura',l) else 'taller' if 'taller' in l else 'monitor' if 'monitor' in l else 'tecnico' if 'tecnic' in l else 'auxiliar' if 'auxiliar' in l else 'educador' if re.search(r'educador|instructor',l) else 'profesor_generico' if 'profesor' in l or 'docente' in l else 'otros'
  casos.append({'oposicion_id':r['oposicion_id'],'puesto':p,'puesto_normalizado':r['puesto_normalizado'],'num_plazas':r['num_plazas'],'familia':fam,'clasificacion':'YA_NORMALIZADA' if r['puesto_normalizado']!=p else ('NO_DOCENTE' if fam in ('tecnico','auxiliar') else 'PENDIENTE_REAL')})
 out={'universo':{'filas':len(casos),'plazas':sum(float(x['num_plazas']) for x in casos if str(x['num_plazas']).replace('.','',1).isdigit())},'familias':dict(Counter(x['familia'] for x in casos)),'clasificacion':dict(Counter(x['clasificacion'] for x in casos)),'casos':casos};p=Path('informes/normalizacion_puestos/fase7_otros_docentes_paso9q1.json');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps({'universo':out['universo'],'familias':out['familias']},ensure_ascii=False))
if __name__=='__main__':main()
