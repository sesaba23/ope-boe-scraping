"""PASOS 53-54: aplicación transaccional de conjuntos literales de Limpieza."""
from __future__ import annotations
import hashlib,json,shutil,sqlite3,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from normalizacion_puestos import normalizar_puesto
from scripts.audit.auditar_bomberos_paso8_40 import state
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import _estado,auditar as gate
DB=ROOT/'datos/boe.db';INF=ROOT/'informes/normalizacion_puestos';BACKUPS=ROOT/'backups/sqlite';OUT53=INF/'fase8_paso53_reglas_limpieza.json';OUT54=INF/'fase8_paso54_aplicacion_limpieza.json';CANONES={'Operario de Limpieza','Peón de Limpieza','Encargado de Limpieza','Empleado de Limpieza'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def plan():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 try:
  rs=[]
  for r in c.execute("select oposicion_id,puesto,puesto_normalizado,num_plazas from oposiciones where lower(puesto) like '%limpieza%'"):
   n=normalizar_puesto(r['puesto'])
   if n in CANONES and n!=r['puesto_normalizado']:rs.append({'id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado_anterior':r['puesto_normalizado'],'puesto_normalizado_nuevo':n,'plazas':r['num_plazas'],'conjunto_A':n,'canon':n})
  return rs
 finally:c.close()
def aplicar(*,backup=True,esperado=None):
 antes,rs=state(),plan()
 if esperado is not None and rs and len(rs)!=esperado:raise RuntimeError('Plan distinto del gate')
 copia=None
 if backup and rs:
  BACKUPS.mkdir(parents=True,exist_ok=True);copia=BACKUPS/f"boe_paso54_limpieza_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}.db";shutil.copy2(DB,copia)
  if sha(copia)!=antes['sha256']:raise RuntimeError('Backup no verificable')
  x=sqlite3.connect(copia)
  try:
   if x.execute('pragma integrity_check').fetchone()[0]!='ok':raise RuntimeError('Backup no legible')
  finally:x.close()
 mut=0
 if rs:
  c=sqlite3.connect(DB)
  try:
   c.execute('BEGIN IMMEDIATE')
   for r in rs:mut+=c.execute('update oposiciones set puesto_normalizado=? where oposicion_id=? and puesto_normalizado=?',(r['puesto_normalizado_nuevo'],r['id'],r['puesto_normalizado_anterior'])).rowcount
   if mut!=len(rs):c.rollback();raise RuntimeError('rowcount distinto')
   if c.execute('pragma integrity_check').fetchone()[0]!='ok' or list(c.execute('pragma foreign_key_check')):c.rollback();raise RuntimeError('SQLite inválida')
   c.execute("update metadata set valor=? where clave='data_version'",(str(int(antes['data_version'])+1),));c.commit()
  finally:c.close()
 despues=state();return {'antes':antes,'backup':{'ruta':str(copia),'sha256':sha(copia),'tamano':copia.stat().st_size,'data_version':antes['data_version'],'integrity_check':'ok'} if copia else None,'plan':rs,'mutaciones':mut,'plazas_mutadas':sum(r['plazas']or 0 for r in rs),'despues':despues}
def main():
 g=json.loads(Path('/tmp/fase8_paso53_gate.json').read_text());antes,rs=state(),plan()
 OUT53.write_text(json.dumps({'version':'fase8-paso53-v1','modo':'normalizador_sin_sqlite','reglas_implementadas':sorted(CANONES),'cobertura_logica_A_global_filas':168,'cobertura_logica_A_global_plazas':385,'filas_que_requieren_update':len(rs),'plazas_que_requieren_update':sum(r['plazas']or 0 for r in rs),'gate_pre_sqlite':g,'sqlite_antes':antes},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 primera=aplicar(esperado=g['cambios_reales_recalculables']['filas']);segunda=aplicar(backup=False)
 OUT54.write_text(json.dumps({'version':'fase8-paso54-v1','generado_utc':datetime.now(timezone.utc).isoformat(),'primera_ejecucion':primera,'segunda_ejecucion':{'mutaciones':segunda['mutaciones'],'data_version':segunda['despues']['data_version']},'gate_final':None},ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'mutaciones':primera['mutaciones'],'segunda':segunda['mutaciones']},ensure_ascii=False))
def finalizar():
 r=json.loads(OUT54.read_text());g=gate(DB);r['gate_final']={k:{'filas':g[k]['filas'],'plazas':g[k]['plazas']}for k in ('cambios_reales_recalculables','discrepancias_contextuales_no_recalculables','discrepancias_no_clasificables_automaticamente')};OUT54.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(r['gate_final'],ensure_ascii=False))
if __name__=='__main__':finalizar() if '--finalizar' in sys.argv else main()
