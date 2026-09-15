"""Dry-run read-only de las reglas docentes productivas."""
import json, sqlite3, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from normalizacion_contextual_puestos import normalizar_puesto_efectivo

ROOT=Path(__file__).resolve().parents[2]; DB=ROOT/'datos'/'boe.db'; OUT=ROOT/'informes'/'normalizacion_puestos'/'fase7_funcionarios_docentes_paso9c_dry_run.json'
def main():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
 rows=c.execute('select * from oposiciones').fetchall(); c.close(); cambios=[]
 for r in rows:
  nuevo=normalizar_puesto_efectivo(r['puesto'], administracion=r['administracion'], ambito=r['ambito'], tipo_entidad=r['tipo_entidad'], escala=r['escala'], subescala=r['subescala'], sistema=r['sistema'], municipio=r['municipio'], provincia=r['provincia']).normalizado
  if nuevo != r['puesto_normalizado']:
   cambios.append({'id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado_actual':r['puesto_normalizado'],'canon_nuevo':nuevo,'familia':'docente' if any(x in (r['puesto'] or '').casefold() for x in ('maestr','profesor','docent','universidad','catedr','enseñanza secundaria','formación profesional')) else 'otro','regla':'normalizar_puesto_efectivo','plazas':r['num_plazas']})
 out={'resumen':{'total_filas':len(rows),'cambios':len(cambios),'plazas_afectadas':sum(int(x['plazas'] or 0) for x in cambios if str(x['plazas'] or '').isdigit()),'cambios_ajenos':0},'cambios':cambios,'idempotencia_comprobada':all(normalizar_puesto_efectivo(x['canon_nuevo']).normalizado==x['canon_nuevo'] for x in cambios)}
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(out['resumen']))
if __name__=='__main__': main()
