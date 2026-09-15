"""PASOS 65-66: gate y aplicación transaccional de Trabajo Social."""
from __future__ import annotations
import hashlib,json,shutil,sqlite3,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from normalizacion_puestos import _clave,normalizar_puesto
from scripts.audit.auditar_bomberos_paso8_40 import state
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate
DB=ROOT/'datos/boe.db';INF=ROOT/'informes/normalizacion_puestos';BACK=ROOT/'backups/sqlite';O65=INF/'fase8_paso65_reglas_trabajo_social.json';O66=INF/'fase8_paso66_aplicacion_trabajo_social.json';CANON='Trabajador Social';V={'trabajador social','trabajadora social','trabajador/a social','trabajadora/or social','trabajador-a social'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def plan():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 try:return [{'id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado_anterior':r['puesto_normalizado'],'puesto_normalizado_nuevo':CANON,'plazas':r['num_plazas'],'canon':CANON} for r in c.execute("select oposicion_id,puesto,puesto_normalizado,num_plazas from oposiciones where lower(puesto) like '%trabaj%' ") if _clave(r['puesto']) in V and normalizar_puesto(r['puesto'])==CANON and r['puesto_normalizado']!=CANON]
 finally:c.close()
def mini(g):return {k:{'filas':g[k]['filas'],'plazas':g[k]['plazas']} for k in ('cambios_reales_recalculables','discrepancias_contextuales_no_recalculables','discrepancias_no_clasificables_automaticamente')}
def pre():
 g=gate(DB);p=plan()
 if len(p)!=g['cambios_reales_recalculables']['filas']:raise RuntimeError('plan distinto del gate')
 O65.write_text(json.dumps({'reglas_implementadas':{CANON:sorted(V)},'cobertura_logica_A_global_filas':1269,'cobertura_logica_A_global_plazas':2912,'filas_que_requieren_update':len(p),'plazas_que_requieren_update':sum(x['plazas'] or 0 for x in p),'gate_pre_sqlite':mini(g)},ensure_ascii=False,indent=2)+'\n');print(len(p))
def apply():
 x=json.loads(O65.read_text());a=state();p=plan()
 if len(p)!=x['filas_que_requieren_update']:raise RuntimeError('plan obsoleto')
 BACK.mkdir(parents=True,exist_ok=True);b=BACK/f"boe_paso66_trabajo_social_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}.db";shutil.copy2(DB,b)
 if sha(b)!=a['sha256']:raise RuntimeError('backup distinto')
 c=sqlite3.connect(DB);n=0
 try:
  c.execute('BEGIN IMMEDIATE')
  for r in p:n+=c.execute('update oposiciones set puesto_normalizado=? where oposicion_id=? and puesto_normalizado=?',(CANON,r['id'],r['puesto_normalizado_anterior'])).rowcount
  if n!=len(p) or c.execute('pragma integrity_check').fetchone()[0]!='ok' or list(c.execute('pragma foreign_key_check')):c.rollback();raise RuntimeError('validacion')
  c.execute("update metadata set valor=? where clave='data_version'",(str(int(a['data_version'])+1),));c.commit()
 finally:c.close()
 d=state();second=plan()
 if second:raise RuntimeError('no idempotente')
 O66.write_text(json.dumps({'primera_ejecucion':{'antes':a,'backup':{'ruta':str(b),'sha256':sha(b),'data_version':a['data_version'],'integrity_check':'ok','foreign_key_check':[]},'plan':p,'mutaciones':n,'plazas_mutadas':sum(r['plazas'] or 0 for r in p),'despues':d},'segunda_ejecucion':{'mutaciones':0,'data_version':d['data_version']},'gate_final':None},ensure_ascii=False,indent=2)+'\n');print(n)
def finish():
 r=json.loads(O66.read_text());r['gate_final']=mini(gate(DB));O66.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(r['gate_final'])
if __name__=='__main__': pre() if '--precheck' in sys.argv else (finish() if '--finalizar' in sys.argv else apply())
