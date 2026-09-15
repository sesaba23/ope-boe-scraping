import json,sqlite3,re
from pathlib import Path
from collections import Counter
from normalizacion_contextual_puestos import normalizar_puesto_efectivo
def main():
 c=sqlite3.connect('datos/boe.db'); c.row_factory=sqlite3.Row; casos=[]
 for r in c.execute('select * from oposiciones'):
  n=normalizar_puesto_efectivo(r['puesto'],administracion=r['administracion'],ambito=r['ambito'],tipo_entidad=r['tipo_entidad'],escala=r['escala'],subescala=r['subescala'],sistema=r['sistema'],municipio=r['municipio'],provincia=r['provincia']).normalizado
  if 'maestr' in (r['puesto'] or '').casefold(): casos.append({'oposicion_id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado':r['puesto_normalizado'],'num_plazas':r['num_plazas'],'canon_propuesto':n,'clasificacion':'CUERPO_MAESTROS_EXPLICITO' if n=='Maestros' else ('MAESTRO_PROFESIONAL_NO_DOCENTE' if re.search(r'industrial|obras?|taller|mantenimiento|electric|limpieza|arsenal',r['puesto'],re.I) else 'MAESTRO_DOCENTE_NO_CUERPO')})
 out={'universo':{'filas':len(casos),'plazas':sum(x['num_plazas'] or 0 for x in casos)},'clasificacion':dict(Counter(x['clasificacion'] for x in casos)),'casos':casos}; p=Path('informes/normalizacion_puestos/fase7_maestros_pendientes_paso9l1.json'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(out,ensure_ascii=False,indent=2)); print(json.dumps({'universo':out['universo'],'clasificacion':out['clasificacion']},ensure_ascii=False))
if __name__=='__main__': main()
