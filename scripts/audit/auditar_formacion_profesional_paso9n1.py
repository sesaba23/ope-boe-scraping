import json,re,sqlite3
from pathlib import Path
from collections import Counter
def main():
 c=sqlite3.connect('datos/boe.db'); c.row_factory=sqlite3.Row; casos=[]
 for r in c.execute('select * from oposiciones'):
  p=r['puesto'] or ''
  if not re.search(r'formaci[oó]n profesional|\bfp\b|ciclo formativo|profesor.*t[eé]cnico',p,re.I): continue
  l=p.casefold(); ya=r['puesto_normalizado'] in ('Profesores Técnicos de Formación Profesional','Profesores de Enseñanza Secundaria')
  cat='YA_NORMALIZADA' if ya else ('LABORAL_DOCENTE' if re.search(r'laboral|plantilla|fijo',l) else ('NO_DOCENTE' if re.search(r't[eé]cnico|auxiliar|director',l) and 'profesor' not in l else 'DUDOSA'))
  casos.append({'oposicion_id':r['oposicion_id'],'puesto':p,'puesto_normalizado':r['puesto_normalizado'],'num_plazas':r['num_plazas'],'clasificacion':cat})
 out={'universo':{'filas':len(casos),'plazas':sum(x['num_plazas'] or 0 for x in casos)},'clasificacion':dict(Counter(x['clasificacion'] for x in casos)),'casos':casos}; p=Path('informes/normalizacion_puestos/fase7_formacion_profesional_paso9n1.json');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps({'universo':out['universo'],'clasificacion':out['clasificacion']},ensure_ascii=False))
if __name__=='__main__':main()
