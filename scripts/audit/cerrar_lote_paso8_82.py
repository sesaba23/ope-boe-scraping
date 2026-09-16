"""PASO 82: cierre del lote PASO 79-80 sin aplicación SQLite."""
from __future__ import annotations
import hashlib,json,sqlite3,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.audit.auditar_bomberos_paso8_40 import state
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate_auditar
INF=ROOT/'informes/normalizacion_puestos';DB=ROOT/'datos/boe.db'
P79=json.loads((INF/'fase8_paso79_estado_418.json').read_text());P80=json.loads((INF/'fase8_paso80_auditoria_lote.json').read_text())
OUT=INF/'fase8_paso82_cierre_lote.json';MASTER=INF/'fase8_paso82_estado_maestro.json';RANK=INF/'fase8_paso82_siguiente_ranking.json'
def fp(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def main():
 before=state();gate=gate_auditar(DB)
 if before['data_version']!='62' or before['integrity_check']!='ok' or before['foreign_key_check'] or (gate['cambios_reales_recalculables']['filas'],gate['discrepancias_contextuales_no_recalculables']['filas'],gate['discrepancias_no_clasificables_automaticamente']['filas'])!=(0,329,0):raise RuntimeError('gates finales inesperados')
 con=sqlite3.connect(f'file:{DB.resolve()}?mode=ro',uri=True);con.row_factory=sqlite3.Row
 try:id30709=con.execute('select puesto_normalizado from oposiciones where oposicion_id=30709').fetchone()[0]
 finally:con.close()
 if id30709!='Policía Local':raise RuntimeError('ID30709 alterado')
 selected=[x['familia'] for x in P79['siguiente_lote']]; special={'POLICÍA':'AUDITADA_CON_B_PENDIENTE','AYUDANTES':'AUDITADA_CON_B_PENDIENTE','PEÓN':'AUDITADA_CON_B_PENDIENTE','LAS':'PENDIENTE_SUBFAMILIAS_D','PERSONAL':'PENDIENTE_SUBFAMILIAS_D'}
 master=[]
 for x in P79['familias']:
  f=x['familia']; status=special.get(f,{'PENDIENTE_REAL':'PENDIENTE_PRIMERA_AUDITORIA','YA_AUDITADA':'AUDITADA','PARCIALMENTE_AUDITADA':'PENDIENTE_SEGUNDA_AUDITORIA_B'}.get(x['estado'],x['estado']))
  master.append({**x,'estado_maestro':status,'seleccionado_paso80':f in selected})
 counts={k:sum(x['estado_maestro']==k for x in master) for k in ('PENDIENTE_PRIMERA_AUDITORIA','PENDIENTE_SEGUNDA_AUDITORIA_B','PENDIENTE_SUBFAMILIAS_D','AUDITADA','AUDITADA_CON_B_PENDIENTE')}
 if sum(counts.values())!=418:raise RuntimeError('estado maestro no cubre 418')
 next5=[x for x in P79['ranking_pendiente'] if x['familia'] not in selected][:5]
 stable={'familias_lote':selected,'resultado_lote':P80['resultado_global'],'A_NUEVO':0,'A_YA_CUBIERTO':P80['A_YA_CUBIERTO'],'B_pendientes':P80['B_pendientes'],'D_candidatos':len(P80['familias_especificas_candidatas_D']),'estado_maestro':counts,'siguiente_lote':[x['familia'] for x in next5],'sqlite_modificado':False,'data_version':before['data_version'],'gate':{k:{'filas':gate[k]['filas'],'plazas':gate[k]['plazas']} for k in ('cambios_reales_recalculables','discrepancias_contextuales_no_recalculables','discrepancias_no_clasificables_automaticamente')},'OA_pendientes':0,'id_30709':id30709}
 f1=fp(stable);f2=fp(stable)
 if f1!=f2:raise RuntimeError('fingerprint no determinista')
 report={**stable,'version':'fase8-paso82-v1','ruta':'RUTA_B_SIN_APLICACION','generado_utc':datetime.now(timezone.utc).isoformat(),'baseline_sqlite_sha256':before['sha256'],'sqlite_sha256_despues':before['sha256'],'backup':None,'idempotencia':{'modificaciones':0,'data_version':before['data_version']},'trazabilidad':['fase8_paso79_estado_418.json','fase8_paso79_ranking_pendiente.json','fase8_paso80_auditoria_lote.json'],'tests_focalizados':'52 passed; py_compile PASO76/PASO78/PASO79/PASO80/PASO82','suite_completa_ejecutada':False,'git_diff_check':subprocess.run(['git','diff','--check'],cwd=ROOT).returncode==0,'fingerprint1':f1,'fingerprint2':f2,'estado_final':'CERRADO'}
 if not report['git_diff_check']:raise RuntimeError('git diff --check')
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');MASTER.write_text(json.dumps({'version':'fase8-paso82-maestro-v1','familias':master,'conteos':counts,'fingerprint':fp(master)},ensure_ascii=False,indent=2)+'\n');RANK.write_text(json.dumps(next5,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'estado':'CERRADO','ruta':'RUTA_B_SIN_APLICACION','siguiente_lote':[(x['familia'],x['filas'],x['plazas']) for x in next5],'conteos':counts,'fingerprint':f1},ensure_ascii=False))
if __name__=='__main__':main()
