"""Restaura sólo cánones contextuales no ortográficos sobrescritos en PASO 71."""
from __future__ import annotations
import json,shutil,sqlite3
from datetime import datetime
from pathlib import Path
from scripts.audit.auditar_ortografia_puestos_paso8_71 import BACKUP,DB,INF,tipo,sha
from scripts.audit.auditar_bomberos_paso8_40 import state
def main():
 a=state(); old=sqlite3.connect(BACKUP);cur=sqlite3.connect(DB);old.row_factory=cur.row_factory=sqlite3.Row
 try:
  prev={r['oposicion_id']:dict(r) for r in old.execute('select oposicion_id,puesto_normalizado,num_plazas from oposiciones')}; bad=[]
  for r in cur.execute('select oposicion_id,puesto_normalizado,num_plazas from oposiciones'):
   if prev[r['oposicion_id']]['puesto_normalizado']!=r['puesto_normalizado'] and tipo(prev[r['oposicion_id']]['puesto_normalizado'],r['puesto_normalizado'])[0]=='OTRA':bad.append((r['oposicion_id'],prev[r['oposicion_id']]['puesto_normalizado'],r['puesto_normalizado'],r['num_plazas']))
 finally:old.close()
 b=DB.parent.parent/'backups/sqlite'/f"boe_paso71_restauracion_contextuales_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.db";shutil.copy2(DB,b)
 try:
  cur.execute('BEGIN IMMEDIATE');n=0
  for i,v,actual,_ in bad:n+=cur.execute('update oposiciones set puesto_normalizado=? where oposicion_id=? and puesto_normalizado=?',(v,i,actual)).rowcount
  if n!=len(bad):cur.rollback();raise RuntimeError('rowcount')
  cur.execute("update metadata set valor=? where clave='data_version'",(str(int(a['data_version'])+1),));cur.commit()
 finally:cur.close()
 r={'restauradas':n,'plazas':sum(float(x[3] or 0) for x in bad),'backup':str(b),'antes':a,'despues':state()};(INF/'fase8_paso71_restauracion_contextuales.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(r)
if __name__=='__main__':main()
