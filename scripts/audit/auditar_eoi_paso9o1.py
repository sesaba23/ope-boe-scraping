import json,re,sqlite3
from pathlib import Path
from collections import Counter
def main():
 c=sqlite3.connect('datos/boe.db');c.row_factory=sqlite3.Row; casos=[]
 for r in c.execute('select * from oposiciones'):
  p=r['puesto'] or ''; l=p.casefold()
  if not re.search(r'escuela[s]? oficial(?:es)? de idiomas|\beoi\b|idioma',l): continue
  ya=r['puesto_normalizado']=='Profesores de Escuelas Oficiales de Idiomas'
  cat='YA_NORMALIZADA' if ya else ('LABORAL_DOCENTE' if re.search(r'laboral|plantilla|fijo',l) and 'profesor' in l else ('NO_DOCENTE' if re.search(r't[eé]cnico|auxiliar|traductor|interprete|monitor',l) else ('CUERPO_EOI_EXPLICITO' if re.search(r'profesor.*escuela[s]? oficial|catedratico.*escuela[s]? oficial',l) else 'DOCENTE_IDIOMAS_NO_EOI')))
  casos.append({'oposicion_id':r['oposicion_id'],'puesto':p,'puesto_normalizado':r['puesto_normalizado'],'num_plazas':r['num_plazas'],'clasificacion':cat})
 out={'universo':{'filas':len(casos),'plazas':sum(x['num_plazas'] or 0 for x in casos)},'clasificacion':dict(Counter(x['clasificacion'] for x in casos)),'casos':casos};p=Path('informes/normalizacion_puestos/fase7_eoi_paso9o1.json');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps({'universo':out['universo'],'clasificacion':out['clasificacion']},ensure_ascii=False))
if __name__=='__main__':main()
