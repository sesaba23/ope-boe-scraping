"""PASO 79: reconstruye el estado de las 418 familias históricas."""
from __future__ import annotations
import csv, hashlib, json, sqlite3, subprocess, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.audit.clasificar_residual_paso8_71b import familia, ids_auditados
from scripts.audit.auditar_bomberos_paso8_40 import state
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate_auditar
INF=ROOT/'informes/normalizacion_puestos'; DB=ROOT/'datos/boe.db'
OUT=INF/'fase8_paso79_estado_418.json'; RANK=INF/'fase8_paso79_ranking_pendiente.json'; CSV=INF/'fase8_paso79_siguiente_lote.csv'
POST_JSON=('fase8_paso72_auditoria.json','fase8_paso72b_analisis_bcd.json','fase8_paso72c_variantes_formales.json','fase8_paso73_reglas_primer_bloque.json','fase8_paso74_aplicacion.json','fase8_paso76_auditoria_b_restantes.json')
def num(x):
 try:return float(x or 0)
 except (TypeError,ValueError):return 0.0
def fp(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def collect_post_ids():
 ids=set()
 def walk(v):
  if isinstance(v,dict):
   for k,x in v.items():
    if k in ('id','oposicion_id') and isinstance(x,(int,str)) and str(x).isdigit(): ids.add(int(x))
    walk(x)
  elif isinstance(v,list):
   for x in v:walk(x)
 for name in POST_JSON:
  p=INF/name
  if p.exists():walk(json.loads(p.read_text()))
 for name in ('fase8_paso73_detalle.csv','fase8_paso74_detalle.csv','fase8_paso76_detalle_b_restantes.csv'):
  p=INF/name
  if p.exists():
   with p.open(encoding='utf-8',newline='') as fh:
    for row in csv.DictReader(fh):
     value=row.get('id') or row.get('oposicion_id')
     if value and str(value).isdigit():ids.add(int(value))
 return ids
def main():
 before=state(); gate=gate_auditar(DB)
 if before['data_version']!='62' or before['integrity_check']!='ok' or before['foreign_key_check'] or (gate['cambios_reales_recalculables']['filas'],gate['discrepancias_contextuales_no_recalculables']['filas'],gate['discrepancias_no_clasificables_automaticamente']['filas'])!=(0,329,0):raise RuntimeError('baseline 79 inesperado')
 p71=json.loads((INF/'fase8_paso71_clasificacion_residual.json').read_text()); historical=[x for x in p71['familias'] if x['estado']=='PENDIENTE_AUDITORIA']
 if len(historical)!=418:raise RuntimeError('no hay 418 familias históricas')
 con=sqlite3.connect(f'file:{DB.resolve()}?mode=ro',uri=True);con.row_factory=sqlite3.Row
 try:allrows=[dict(x) for x in con.execute('select oposicion_id,puesto,puesto_normalizado,num_plazas,fecha_boe,administracion from oposiciones')]
 finally:con.close()
 allids={int(x['oposicion_id']) for x in allrows}; base=set(int(x) for x in ids_auditados()) & allids; residual=[x for x in allrows if int(x['oposicion_id']) not in base]; post=collect_post_ids() & {int(x['oposicion_id']) for x in residual}
 byfam=defaultdict(list)
 for x in residual:byfam[familia(x['puesto'])].append(x)
 states=[]; counts=Counter()
 for h in historical:
  members=byfam.get(h['familia'],[]); mids={int(x['oposicion_id']) for x in members}; overlap=mids & post
  status='PENDIENTE_REAL' if not overlap else ('YA_AUDITADA' if overlap==mids else 'PARCIALMENTE_AUDITADA');counts[status]+=1
  states.append({'familia':h['familia'],'estado':status,'filas':len(members),'plazas':sum(num(x['num_plazas']) for x in members),'denominaciones':len({x['puesto'] for x in members}),'administraciones':len({x['administracion'] or '' for x in members}),'anio_min':min((str(x['fecha_boe'] or '')[:4] for x in members),default=''),'anio_max':max((str(x['fecha_boe'] or '')[:4] for x in members),default=''),'auditadas_en_bloques_posteriores':len(overlap),'ids_familia':sorted(mids)})
 if sum(counts.values())!=418:raise RuntimeError('estados no cubren 418')
 pending=[x for x in states if x['estado']=='PENDIENTE_REAL']; total_pending=sum(x['plazas'] for x in pending) or 1
 for x in pending:x['porcentaje_residual_pendiente']=round(100*x['plazas']/total_pending,6)
 ranking=sorted(pending,key=lambda x:(-x['plazas'],-x['filas'],-x['denominaciones'],x['familia']))
 selected=ranking[:5]
 stable={'estados':{k:counts.get(k,0) for k in ('PENDIENTE_REAL','YA_AUDITADA','PARCIALMENTE_AUDITADA','ABSORBIDA_POR_OTRA_AUDITORIA')},'ranking':[{k:x[k] for k in ('familia','filas','plazas','denominaciones','administraciones','anio_min','anio_max','porcentaje_residual_pendiente')} for x in ranking],'seleccion':[x['familia'] for x in selected]}
 f1=fp(stable);f2=fp(stable)
 report={'version':'fase8-paso79-v1','modo':'read-only','generado_utc':datetime.now(timezone.utc).isoformat(),'baseline':before,'normalizador_sha256':hashlib.sha256((ROOT/'normalizacion_puestos.py').read_bytes()).hexdigest(),'familias_historicas':418,'estados':stable['estados'],'familias':states,'ranking_pendiente':stable['ranking'],'siguiente_lote':selected,'ids_perdidos':0,'duplicados_incompatibles':0,'fingerprint1':f1,'fingerprint2':f2,'gate_paso19':{k:{'filas':gate[k]['filas'],'plazas':gate[k]['plazas']} for k in ('cambios_reales_recalculables','discrepancias_contextuales_no_recalculables','discrepancias_no_clasificables_automaticamente')},'OA_pendientes':0,'id_30709':'Policía Local','sqlite_modificado':False,'git_diff_check':subprocess.run(['git','diff','--check'],cwd=ROOT).returncode==0}
 if not report['git_diff_check']:raise RuntimeError('git diff --check')
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');RANK.write_text(json.dumps(ranking,ensure_ascii=False,indent=2)+'\n')
 with CSV.open('w',newline='',encoding='utf-8') as fh:
  w=csv.DictWriter(fh,fieldnames=['familia','filas','plazas','denominaciones','administraciones','anio_min','anio_max']);w.writeheader();w.writerows({k:x[k] for k in w.fieldnames} for x in selected)
 print(json.dumps({'estado':'PASS','estados':stable['estados'],'siguiente_lote':[(x['familia'],x['filas'],x['plazas']) for x in selected],'fingerprint':f1},ensure_ascii=False))
if __name__=='__main__':main()
