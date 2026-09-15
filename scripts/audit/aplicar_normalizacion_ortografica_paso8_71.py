"""PASO 71-A: plan y aplicación transaccional de la capa ortográfica OA."""
from __future__ import annotations
import hashlib,json,shutil,sqlite3,sys
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from normalizacion_puestos import normalizar_puesto,TILDES_ORTOGRAFICAS_SEGURAS
from scripts.audit.auditar_bomberos_paso8_40 import state
DB=ROOT/'datos/boe.db';INF=ROOT/'informes/normalizacion_puestos';BACK=ROOT/'backups/sqlite';OUT=INF/'fase8_paso71_ortografia.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def plan():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 try:return [{'id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado_antes':r['puesto_normalizado'],'puesto_normalizado_despues':normalizar_puesto(r['puesto']),'plazas':r['num_plazas']} for r in c.execute('select oposicion_id,puesto,puesto_normalizado,num_plazas from oposiciones') if normalizar_puesto(r['puesto'])!=r['puesto_normalizado']]
 finally:c.close()
def apply():
 a=state();p=plan();BACK.mkdir(parents=True,exist_ok=True);b=BACK/f"boe_paso71_ortografia_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.db";shutil.copy2(DB,b);c=sqlite3.connect(DB);n=0
 try:
  c.execute('BEGIN IMMEDIATE')
  for r in p:n+=c.execute('update oposiciones set puesto_normalizado=? where oposicion_id=? and puesto_normalizado=?',(r['puesto_normalizado_despues'],r['id'],r['puesto_normalizado_antes'])).rowcount
  if n!=len(p) or c.execute('pragma integrity_check').fetchone()[0]!='ok' or list(c.execute('pragma foreign_key_check')):c.rollback();raise RuntimeError('validacion')
  if n:c.execute("update metadata set valor=? where clave='data_version'",(str(int(a['data_version'])+1),))
  c.commit()
 finally:c.close()
 d=state();r={'baseline_sqlite':a,'catalogo_OA':TILDES_ORTOGRAFICAS_SEGURAS,'plan':p,'backup':{'ruta':str(b),'sha256':sha(b),'data_version':a['data_version']},'mutaciones_sqlite':n,'plazas_afectadas':sum(x['plazas'] or 0 for x in p),'sqlite_final':d,'segunda_ejecucion':{'mutaciones':len(plan()),'data_version':d['data_version']}}
 OUT.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(n)
if __name__=='__main__':apply()
