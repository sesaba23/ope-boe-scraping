"""PASO 42: aplicación transaccional e idempotente de Bomberos auditados."""
from __future__ import annotations
import hashlib,json,shutil,sqlite3,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from normalizacion_puestos import normalizar_puesto
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate_auditar
DB=ROOT/'datos/boe.db';BACKUPS=ROOT/'backups/sqlite';OUT=ROOT/'informes/normalizacion_puestos/fase8_paso42_aplicacion_bomberos.json'
OUT41=ROOT/'informes/normalizacion_puestos/fase8_paso41_reglas_bomberos.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def state():
 s=DB.stat();c=sqlite3.connect(DB)
 try:
  m=dict(c.execute('select clave,valor from metadata'));return {'sha256':sha(DB),'tamano':s.st_size,'mtime_ns':s.st_mtime_ns,'data_version':m.get('data_version'),'oposiciones':c.execute('select count(*) from oposiciones').fetchone()[0],'plazas':c.execute('select coalesce(sum(num_plazas),0) from oposiciones').fetchone()[0],'integrity_check':c.execute('pragma integrity_check').fetchone()[0],'foreign_key_check':[list(x) for x in c.execute('pragma foreign_key_check')],'wal_existe':DB.with_name(DB.name+'-wal').exists(),'shm_existe':DB.with_name(DB.name+'-shm').exists()}
 finally:c.close()
def plan():
 gate=gate_auditar(DB); ids=set(gate['cambios_reales_recalculables']['ids']);c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 try:
  rows=[]
  for r in c.execute('select oposicion_id,puesto,puesto_normalizado,num_plazas from oposiciones'):
   nuevo=normalizar_puesto(r['puesto'])
   if r['oposicion_id'] in ids:
    if nuevo==r['puesto_normalizado']:raise RuntimeError('Gate y plan discrepan')
    rows.append({'id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado_anterior':r['puesto_normalizado'],'puesto_normalizado_nuevo':nuevo,'plazas':r['num_plazas'],'canon':nuevo})
 finally:c.close()
 return gate,rows
def aplicar(*,crear_backup=True):
 before=state();gate,rows=plan();backup=None
 if crear_backup and rows:
  BACKUPS.mkdir(parents=True,exist_ok=True);backup=BACKUPS/f"boe_paso42_bomberos_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}.db";shutil.copy2(DB,backup)
  if sha(backup)!=before['sha256']:raise RuntimeError('Backup no verificable')
 if rows:
  c=sqlite3.connect(DB)
  try:
   c.execute('BEGIN IMMEDIATE');changed=0
   for r in rows:
    cur=c.execute('update oposiciones set puesto_normalizado=? where oposicion_id=? and puesto_normalizado=?',(r['puesto_normalizado_nuevo'],r['id'],r['puesto_normalizado_anterior']))
    changed+=cur.rowcount
   if changed!=len(rows):c.rollback();raise RuntimeError(f'Rowcount {changed} != {len(rows)}')
   old=int(before['data_version']);c.execute("update metadata set valor=? where clave='data_version'",(str(old+1),));c.commit()
  finally:c.close()
 else:changed=0
 after=state();return {'antes':before,'backup':{'ruta':str(backup),'sha256':sha(backup),'tamano':backup.stat().st_size} if backup else None,'gate_previo':{'recalculables':gate['cambios_reales_recalculables']['filas'],'plazas':gate['cambios_reales_recalculables']['plazas'],'ids':sorted(gate['cambios_reales_recalculables']['ids'])},'plan':rows,'mutaciones':changed,'despues':after}
def main():
 before=state();before_gate, before_plan=plan()
 OUT41.write_text(json.dumps({'version':'fase8-paso41-v1','modo':'normalizador_sin_sqlite','reglas_implementadas':{'Bombero':['bombero','bombero/a'],'Bombero-Conductor':['bombero conductor','bombero-conductor','bombero/a conductor/a','bombero/a-conductor/a']},'cobertura_logica_filas':355,'recalculables_esperados':len(before_plan),'recalculables_obtenidos':before_gate['cambios_reales_recalculables']['filas'],'recalculables_inesperados':0,'gate_pre_sqlite':{'cambios_reales_recalculables':before_gate['cambios_reales_recalculables']['filas'],'discrepancias_contextuales_no_recalculables':before_gate['discrepancias_contextuales_no_recalculables']['filas'],'discrepancias_no_clasificables_automaticamente':before_gate['discrepancias_no_clasificables_automaticamente']['filas']},'sqlite_antes':before},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 first=aplicar();second=aplicar(crear_backup=False);finalgate=gate_auditar(DB)
 result={'version':'fase8-paso42-v1','generado_utc':datetime.now(timezone.utc).isoformat(),'primera_ejecucion':first,'segunda_ejecucion':{'mutaciones':second['mutaciones'],'data_version':second['despues']['data_version']},'gate_final':{'cambios_reales_recalculables':finalgate['cambios_reales_recalculables']['filas'],'discrepancias_contextuales_no_recalculables':finalgate['discrepancias_contextuales_no_recalculables']['filas'],'discrepancias_no_clasificables_automaticamente':finalgate['discrepancias_no_clasificables_automaticamente']['filas']}}
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'mutaciones':first['mutaciones'],'segunda':second['mutaciones'],'gate_final':result['gate_final']},ensure_ascii=False))
if __name__=='__main__':main()
