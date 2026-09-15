import json,re,sqlite3
from pathlib import Path
from collections import Counter
def main():
 c=sqlite3.connect('datos/boe.db');c.row_factory=sqlite3.Row; rows=[]
 for r in c.execute('select oposicion_id,puesto,puesto_normalizado,num_plazas from oposiciones'):
  p=r['puesto'] or ''
  if re.search(r'maestr|profesor|docente|catedr|titular|monitor|tecnic|auxiliar|taller|universidad|secundaria|formaci[oó]n profesional|idioma',p,re.I): rows.append(r)
 fam=Counter('universidad' if re.search(r'universidad|catedr|titular',r['puesto'] or '',re.I) else 'maestros' if re.search(r'maestr',r['puesto'] or '',re.I) else 'secundaria' if re.search(r'secundaria',r['puesto'] or '',re.I) else 'fp' if re.search(r'formaci[oó]n profesional|\bfp\b',r['puesto'] or '',re.I) else 'otros' for r in rows)
 plazas=sum(float(r['num_plazas']) for r in rows if str(r['num_plazas'] or '').replace('.','',1).isdigit())
 out={'universo':{'filas':len(rows),'plazas':plazas},'familias':dict(fam),'pendiente':sum(r['puesto_normalizado']==r['puesto'] for r in rows)};p=Path('informes/normalizacion_puestos/fase7_universo_docente_pendiente_paso9p.json');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()
