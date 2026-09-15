"""Auditoría reproducible del universo universitario funcionarial (9K-1)."""
import json, re, sqlite3
from pathlib import Path
from collections import Counter
from normalizacion_puestos import normalizar_puesto

OUT=Path('informes/normalizacion_puestos/fase7_universidad_funcionarial_paso9k1.json')
def main():
 con=sqlite3.connect('datos/boe.db'); con.row_factory=sqlite3.Row
 rows=con.execute("select * from oposiciones where lower(puesto) like '%universidad%' or lower(puesto) like '%catedr%' or lower(puesto) like '%titular%'").fetchall(); casos=[]
 for r in rows:
  p=r['puesto'] or ''; low=p.casefold()
  if re.search(r'contratad|ayudante|asociad|laboral|visitante|sustitut',low): cat='LABORAL_CONTRACTUAL'
  elif normalizar_puesto(p) in ('Catedráticos de Universidad','Profesores Titulares de Universidad'): cat='FUNCIONARIAL_EXPLICITA'
  elif re.search(r'profesor|catedr|docente',low): cat='UNIVERSITARIA_INDETERMINADA'
  else: cat='NO_DOCENTE'
  casos.append({'oposicion_id':r['oposicion_id'],'puesto':p,'puesto_normalizado':r['puesto_normalizado'],'num_plazas':r['num_plazas'],'clasificacion':cat,'canon_propuesto':normalizar_puesto(p)})
 out={'universo':{'filas':len(casos),'plazas':sum(x['num_plazas'] or 0 for x in casos)},'clasificacion':dict(Counter(x['clasificacion'] for x in casos)),'casos':casos}
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)); print(json.dumps({'universo':out['universo'],'clasificacion':out['clasificacion']},ensure_ascii=False))
if __name__=='__main__': main()
