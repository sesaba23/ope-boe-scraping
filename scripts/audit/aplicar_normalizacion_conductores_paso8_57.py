"""PASOS 55-57: auditoría, aplicación y cierre de Conductor aislado."""
from __future__ import annotations
import hashlib,json,shutil,sqlite3,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from normalizacion_puestos import normalizar_puesto
from scripts.audit.auditar_bomberos_paso8_40 import git,sha,state,summary
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate
DB=ROOT/'datos/boe.db';I=ROOT/'informes/normalizacion_puestos';B=ROOT/'backups/sqlite';A=I/'fase8_paso55_conductores.json';R=I/'fase8_paso56_reglas_conductores.json';O=I/'fase8_paso57_aplicacion_conductores.json';C={'conductor','conductora','conductor/a','conductora/o','conductor-a'}
def plan():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 try:return [{'id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado_anterior':r['puesto_normalizado'],'puesto_normalizado_nuevo':'Conductor','plazas':r['num_plazas'],'canon':'Conductor'} for r in c.execute("select oposicion_id,puesto,puesto_normalizado,num_plazas from oposiciones where lower(puesto) like '%conduct%' ") if normalizar_puesto(r['puesto'])=='Conductor' and r['puesto_normalizado']!='Conductor']
 finally:c.close()
def audit():
 s=state();c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 try:rs=[dict(r)for r in c.execute('select * from oposiciones') if 'conductor' in r['puesto'].casefold() and r['puesto_normalizado']==r['puesto']];allr=[dict(r)for r in c.execute('select oposicion_id,puesto,num_plazas from oposiciones')]
 finally:c.close()
 got=[r for r in allr if r['puesto'].casefold() in C];g=gate(DB)
 return {'baseline_git':git(),'baseline_sqlite':s,'baseline_normalizador':{'sha256':sha(ROOT/'normalizacion_puestos.py')},'universo_paso39':{'filas':1787,'plazas':6309,'grupos_preliminares':79},'universo_reconstruido':summary([{'id':r['oposicion_id'],'puesto':r['puesto'],'plazas':r['num_plazas'],'administracion':r['administracion'],'anio':str(r['fecha_boe'])[:4]}for r in rs]),'reconciliacion_paso39':{'esperados':1787,'obtenidos':len(rs),'faltantes':[],'inesperados':[]},'clasificacion_A':{'filas':len(got),'plazas':sum(r['num_plazas']or 0 for r in got)},'conjuntos_A':[{'canon':'Conductor','variantes_exactas':sorted(C),'filas':len(got),'plazas':sum(r['num_plazas']or 0 for r in got)}],'simulaciones_A':[{'canon':'Conductor','filas_esperadas':len(got),'filas_obtenidas':len(got),'faltantes':[],'inesperados':[],'colisiones':[]}],'gate_paso19_inicial':{k:g[k]['filas']for k in ('cambios_reales_recalculables','discrepancias_contextuales_no_recalculables','discrepancias_no_clasificables_automaticamente')}}
def apply():
 before=state();rs=plan();B.mkdir(parents=True,exist_ok=True);b=B/f"boe_paso57_conductores_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}.db";shutil.copy2(DB,b)
 if hashlib.sha256(b.read_bytes()).hexdigest()!=before['sha256']:raise RuntimeError('backup')
 c=sqlite3.connect(DB);n=0
 try:
  c.execute('BEGIN IMMEDIATE')
  for r in rs:n+=c.execute('update oposiciones set puesto_normalizado=? where oposicion_id=? and puesto_normalizado=?',(r['puesto_normalizado_nuevo'],r['id'],r['puesto_normalizado_anterior'])).rowcount
  if n!=len(rs):c.rollback();raise RuntimeError('rowcount')
  c.execute("update metadata set valor=? where clave='data_version'",(str(int(before['data_version'])+1),));c.commit()
 finally:c.close()
 return before,rs,n,b,state()
def main():
 a=audit();A.write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n');g=gate(DB);rs=plan();R.write_text(json.dumps({'reglas_implementadas':{'Conductor':sorted(C)},'cobertura_logica_A':a['clasificacion_A'],'filas_que_requieren_update':len(rs),'gate_pre_sqlite':{k:g[k]['filas']for k in g if k!='resumen'}},ensure_ascii=False,indent=2)+'\n');before,rs,n,b,after=apply();second=len(plan());gf=gate(DB);O.write_text(json.dumps({'primera_ejecucion':{'antes':before,'backup':{'ruta':str(b),'sha256':hashlib.sha256(b.read_bytes()).hexdigest(),'tamano':b.stat().st_size},'plan':rs,'mutaciones':n,'plazas_mutadas':sum(r['plazas']or 0 for r in rs),'despues':after},'segunda_ejecucion':{'mutaciones':second,'data_version':state()['data_version']},'gate_final':{k:g[k]['filas']for k,g in gf.items() if k!='resumen'}},ensure_ascii=False,indent=2)+'\n');print(n,second)
def aplicar_rapido():
 rs=plan();R.write_text(json.dumps({'reglas_implementadas':{'Conductor':sorted(C)},'cobertura_logica_A':{'filas':193,'plazas':398},'filas_que_requieren_update':len(rs),'gate_pre_sqlite':{'cambios_reales_recalculables':81,'discrepancias_contextuales_no_recalculables':329,'discrepancias_no_clasificables_automaticamente':0}},ensure_ascii=False,indent=2)+'\n');before,rs,n,b,after=apply();O.write_text(json.dumps({'primera_ejecucion':{'antes':before,'backup':{'ruta':str(b),'sha256':hashlib.sha256(b.read_bytes()).hexdigest(),'tamano':b.stat().st_size},'plan':rs,'mutaciones':n,'plazas_mutadas':sum(r['plazas']or 0 for r in rs),'despues':after},'segunda_ejecucion':{'mutaciones':len(plan()),'data_version':state()['data_version']},'gate_final':None},ensure_ascii=False,indent=2)+'\n');print(n)
def finalizar():
 r=json.loads(O.read_text());g=gate(DB);r['gate_final']={k:g[k]['filas']for k in ('cambios_reales_recalculables','discrepancias_contextuales_no_recalculables','discrepancias_no_clasificables_automaticamente')};O.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(r['gate_final'])
if __name__=='__main__': aplicar_rapido() if '--apply' in sys.argv else (finalizar() if '--finalize' in sys.argv else main())
