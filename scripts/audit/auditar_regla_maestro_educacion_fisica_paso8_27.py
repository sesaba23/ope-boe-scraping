"""Auditoría reproducible de la regla de Educación Física; no escribe SQLite."""
from __future__ import annotations
import argparse, csv, hashlib, json, sqlite3, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from normalizacion_puestos import normalizar_puesto
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as auditar_global
from scripts.audit.aplicar_maestros_paso8_22 import estado

DB=ROOT/'datos/boe.db'; OUT=ROOT/'informes/normalizacion_puestos/fase8_paso27_regla_maestro_educacion_fisica.json'; CSV_OUT=ROOT/'informes/normalizacion_puestos/fase8_paso27_regla_maestro_educacion_fisica_detalle.csv'
IDS=(11067,99076); VARIANTS=('Maestro de Educación Física','Maestro/a de Educación Física'); CANON='Maestro de Educación Física'

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()

def git_state():
 def run(*a):return subprocess.check_output(['git',*a],cwd=ROOT,text=True)
 return {'rama':run('branch','--show-current'),'head':run('rev-parse','HEAD'),'origin_main':run('rev-parse','origin/main'),'status_short':run('status','--short'),'diff_stat':run('diff','--stat')}

def rows(path=DB):
 c=sqlite3.connect(f'file:{Path(path).resolve()}?mode=ro',uri=True); c.row_factory=sqlite3.Row
 try:
  return [dict(x) for x in c.execute('''select o.oposicion_id,o.puesto,o.puesto_normalizado,o.num_plazas,o.fecha_boe,o.administracion,o.escala,o.subescala,o.clase,o.ambito,o.tipo_entidad,o.publicacion_id,p.titulo_original from oposiciones o left join publicaciones p on p.publicacion_id=o.publicacion_id where o.oposicion_id in (11067,99076) order by o.oposicion_id''')]
 finally:c.close()

def exact_universe(path=DB):
 c=sqlite3.connect(f'file:{Path(path).resolve()}?mode=ro',uri=True)
 c.row_factory=sqlite3.Row
 try:
  out={}
  for text in VARIANTS: out[text]=[dict(r) for r in c.execute('select oposicion_id,puesto,puesto_normalizado,num_plazas,fecha_boe,administracion from oposiciones where puesto=? order by oposicion_id',(text,))]
  return out
 finally:c.close()

def auditar(path=DB):
 before=estado(path); norm_before=sha(ROOT/'normalizacion_puestos.py'); target=rows(path); universe=exact_universe(path)
 if [r['oposicion_id'] for r in target] != list(IDS): raise RuntimeError('Los dos IDs validados no coinciden')
 details=[]
 for r in target:
  recal=normalizar_puesto(r['puesto']); details.append({'oposicion_id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado_persistido':r['puesto_normalizado'],'recalculado':recal,'plazas':r['num_plazas'],'cambio_real':recal != r['puesto_normalizado'],'ya_canonico':recal == r['puesto_normalizado'] == CANON,'fecha_boe':r['fecha_boe'],'administracion':r['administracion'],'escala':r['escala'],'subescala':r['subescala'],'clase':r['clase'],'publicacion_id':r['publicacion_id'],'titulo_publicacion':r['titulo_original']})
 expected=list(IDS); obtained=[d['oposicion_id'] for d in details if d['recalculado'] == CANON]; effective=[d['oposicion_id'] for d in details if d['cambio_real']]; after=estado(path); norm_after=sha(ROOT/'normalizacion_puestos.py'); gate=auditar_global(path)
 if before != after: raise RuntimeError('SQLite cambió durante auditoría')
 near=[]
 c=sqlite3.connect(f'file:{Path(path).resolve()}?mode=ro',uri=True)
 try:
  for text in ('Maestro/a Educación Física','Maestra de Educación Física','Maestro Educación Física','Maestro Especialista en Educación Física','Maestro/a Especialista en Educación Física'):
   near.append({'puesto':text,'filas':c.execute('select count(*) from oposiciones where puesto=?',(text,)).fetchone()[0],'ids':[x[0] for x in c.execute('select oposicion_id from oposiciones where puesto=? order by oposicion_id',(text,))]})
 finally:c.close()
 return {'version':'fase8-paso27-v1','generado_utc':datetime.now(timezone.utc).isoformat(),'git':git_state(),'sqlite_precheck':before,'revalidacion_ids':details,'variantes_exactas':{'textos':list(VARIANTS),'filas':sum(len(v) for v in universe.values()),'plazas':sum(float(x['num_plazas'] or 0) for v in universe.values() for x in v),'universo':universe},'casos_cercanos_excluidos':near,'regla_implementada':{'funcion':'_normalizar_maestro_educacion_fisica','canon':CANON,'independiente_de_ids_contexto_y_plazas':True},'dry_run':{'esperados':expected,'obtenidos':obtained,'faltantes':sorted(set(expected)-set(obtained)),'inesperados':sorted(set(obtained)-set(expected)),'filas_recalculables':len(effective),'plazas_recalculables':sum(float(d['plazas'] or 0) for d in details if d['cambio_real']),'filas_cubiertas_por_regla':len(obtained),'plazas_cubiertas_por_regla':sum(float(d['plazas'] or 0) for d in details if d['recalculado'] == CANON),'filas_afectadas_por_regla':len(expected),'plazas_afectadas_por_regla':sum(float(d['plazas'] or 0) for d in details),'no_op_ya_canonico':[d['oposicion_id'] for d in details if d['ya_canonico']],'detalle':details},'puerta_global_paso19':{'total_discrepancias':gate['total_discrepancias'],'total_plazas_discrepantes':gate['total_plazas_discrepantes'],'cambios_reales_recalculables':gate['cambios_reales_recalculables']['filas'],'plazas_recalculables':gate['cambios_reales_recalculables']['plazas'],'discrepancias_contextuales_no_recalculables':gate['discrepancias_contextuales_no_recalculables']['filas'],'plazas_contextuales':gate['discrepancias_contextuales_no_recalculables']['plazas'],'discrepancias_no_clasificables_automaticamente':gate['discrepancias_no_clasificables_automaticamente']['filas']},'colisiones':{'contextuales_preservadas':gate['discrepancias_contextuales_no_recalculables']['filas'],'no_clasificables':gate['discrepancias_no_clasificables_automaticamente']['filas']},'normalizador_sha256_inicial':norm_before,'normalizador_sha256_final':norm_after,'normalizador_modificado':norm_before != norm_after,'sqlite_final':after,'sqlite_modificada':before != after,'observacion_contrato':'El ID 11067 ya estaba persistido con el canon exacto; por eso sólo 99076 es mutación efectiva.','recomendacion_paso28':'Aplicar únicamente el cambio efectivo de 99076, o tratar ambos IDs idempotentemente, tras confirmar el no-op de 11067.'}

def main():
 p=argparse.ArgumentParser();p.add_argument('--bd',type=Path,default=DB);p.add_argument('--salida',type=Path,default=OUT);p.add_argument('--csv',type=Path,default=CSV_OUT);a=p.parse_args();r=auditar(a.bd);a.salida.parent.mkdir(parents=True,exist_ok=True);a.salida.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); fields=['oposicion_id','puesto','puesto_normalizado_persistido','recalculado','plazas','cambio_real','ya_canonico','fecha_boe','administracion'];
 with a.csv.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows({k:d.get(k) for k in fields} for d in r['dry_run']['detalle'])
 print(json.dumps({'dry_run':r['dry_run'],'gate':r['puerta_global_paso19'],'sqlite_modificada':r['sqlite_modificada']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
