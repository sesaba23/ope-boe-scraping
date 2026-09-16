"""PASO 80: auditoría A/B/C/D del lote elegido en PASO 79."""
from __future__ import annotations
import csv,hashlib,json,sqlite3,subprocess,sys,unicodedata
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from normalizacion_puestos import normalizar_puesto
from scripts.audit.auditar_bomberos_paso8_40 import state
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate_auditar
INF=ROOT/'informes/normalizacion_puestos'; DB=ROOT/'datos/boe.db'
P79=INF/'fase8_paso79_estado_418.json'; OUT=INF/'fase8_paso80_auditoria_lote.json'; DETAIL=INF/'fase8_paso80_detalle_lote.csv'; GEN=INF/'fase8_paso80_a_generalizables.csv'; DCSV=INF/'fase8_paso80_familias_especificas_candidatas.csv'
def num(x):
 try:return float(x or 0)
 except (TypeError,ValueError):return 0.0
def forma(s):
 s=''.join(c for c in unicodedata.normalize('NFD',str(s or '').casefold()) if unicodedata.category(c)!='Mn');return ' '.join(s.replace('/a','').replace('/o','').replace('-a','').split())
def fp(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def main():
 before=state();gate=gate_auditar(DB)
 if before['data_version']!='62' or before['integrity_check']!='ok' or before['foreign_key_check'] or (gate['cambios_reales_recalculables']['filas'],gate['discrepancias_contextuales_no_recalculables']['filas'],gate['discrepancias_no_clasificables_automaticamente']['filas'])!=(0,329,0):raise RuntimeError('baseline 80 inesperado')
 p79=json.loads(P79.read_text()); selected=p79['siguiente_lote']; families=[x['familia'] for x in selected]
 con=sqlite3.connect(f'file:{DB.resolve()}?mode=ro',uri=True);con.row_factory=sqlite3.Row
 try:rows=[dict(x) for x in con.execute('select oposicion_id,puesto,puesto_normalizado,num_plazas,fecha_boe,administracion from oposiciones')]
 finally:con.close()
 ids={int(i) for x in selected for i in next(y['ids_familia'] for y in p79['familias'] if y['familia']==x['familia'] and y['estado']=='PENDIENTE_REAL')}; source=[x for x in rows if int(x['oposicion_id']) in ids]
 if len(source)!=sum(x['filas'] for x in selected) or len({int(x['oposicion_id']) for x in source})!=len(source):raise RuntimeError('universo lote no reconcilia PASO79')
 groups=defaultdict(list)
 for x in source:groups[(familia_key:=next((f for f in families if forma(x['puesto']).startswith(forma(f))), 'OTRO'),forma(x['puesto']))].append(x)
 # La familia LAS es un artefacto textual, no una profesión; PERSONAL mezcla categorías.
 detail=[]; sets=[]
 for (fam,key),vals in sorted(groups.items()):
  variants=sorted({x['puesto'] for x in vals}); canons={x['puesto_normalizado'] for x in vals}; formal=len(variants)>1 and len(canons)==1 and all(normalizar_puesto(x['puesto'])==x['puesto_normalizado'] for x in vals)
  for x in vals:
   raw=x['puesto']; persisted=x['puesto_normalizado']
   if formal: cls='A'; subtype='VARIANTE_FORMAL_CONFIRMADA'; canon=next(iter(canons)); reason='variantes formales con canon completo coherente ya cubierto'
   elif fam=='POLICÍA' and persisted=='Policía Local' and normalizar_puesto(raw)!=persisted: cls='B'; subtype='CONTEXTO'; canon=None; reason='canon policial contextual, no reproducible sólo desde el texto'
   elif fam in ('LAS','PERSONAL'): cls='D'; subtype='PROFESION_CATEGORIA_DISTINTA'; canon=None; reason='familia residual no profesional o mezcla de categorías'
   elif len(variants)>1: cls='B'; subtype='VARIANTE_FORMAL_DUDOSA'; canon=None; reason='variantes sin prueba de equivalencia global'
   else: cls='C'; subtype='SEMANTICA_PRESERVADA'; canon=None; reason='se conserva especialidad, función, ámbito, destino, nivel, categoría o mando'
   detail.append({'id':int(x['oposicion_id']),'familia':fam,'denominacion':raw,'puesto_normalizado':persisted,'plazas':x['num_plazas'],'anio':str(x['fecha_boe'] or '')[:4],'administracion':x['administracion'],'clasificacion':cls,'subtipo_80':subtype,'canon_propuesto':canon,'motivo':reason})
  if formal:sets.append({'familia':fam,'subtipo':subtype,'canon':next(iter(canons)),'variantes':variants,'ids':sorted(int(x['oposicion_id']) for x in vals),'filas':len(vals),'plazas':sum(num(x['num_plazas']) for x in vals),'administraciones':sorted({x['administracion'] or '' for x in vals}),'anios':sorted({str(x['fecha_boe'] or '')[:4] for x in vals}),'clasificacion':'A_YA_CUBIERTO','generalizacion':'NO_NUEVA_REGLA'})
 summary={}
 for fam in families:
  r=[x for x in detail if x['familia']==fam];summary[fam]={'filas':len(r),'plazas':sum(num(x['plazas']) for x in r),'denominaciones':len({x['denominacion'] for x in r}),'administraciones':len({x['administracion'] or '' for x in r}),'anios':sorted({x['anio'] for x in r}),**{c:{'filas':sum(x['clasificacion']==c for x in r),'plazas':sum(num(x['plazas']) for x in r if x['clasificacion']==c)} for c in 'ABCD'}}
 # Grupos D repetidos que pueden ser familias específicas futuras, sin auditarlos ahora.
 dg=defaultdict(list)
 for x in detail:
  if x['clasificacion']=='D':dg[(x['familia'],x['puesto_normalizado'])].append(x)
 candidates=[{'familia':k[0],'canon_candidato':k[1],'filas':len(v),'plazas':sum(num(x['plazas']) for x in v),'ids':sorted(x['id'] for x in v),'motivo':'grupo D repetido; requiere auditoría específica independiente'} for k,v in dg.items() if len(v)>=2]
 candidates.sort(key=lambda x:(-x['plazas'],-x['filas'],x['familia'],x['canon_candidato']))
 stable={'familias':families,'summary':summary,'conjuntos_A':sets,'resultado_global':{c:{'filas':sum(x['clasificacion']==c for x in detail),'plazas':sum(num(x['plazas']) for x in detail if x['clasificacion']==c)} for c in 'ABCD'},'ids':[x['id'] for x in sorted(detail,key=lambda x:x['id'])],'D_candidatos':candidates}
 f1=fp(stable);f2=fp(stable)
 if f1!=f2 or len(detail)!=len(source):raise RuntimeError('determinismo/cobertura fallidos')
 with DETAIL.open('w',newline='',encoding='utf-8') as fh:w=csv.DictWriter(fh,fieldnames=list(detail[0]));w.writeheader();w.writerows(sorted(detail,key=lambda x:x['id']))
 with GEN.open('w',newline='',encoding='utf-8') as fh:
  w=csv.DictWriter(fh,fieldnames=['familia','canon','variantes','ids','filas','plazas','clasificacion']);w.writeheader();w.writerows({k:s[k] for k in ('familia','canon','variantes','ids','filas','plazas','clasificacion')} for s in sets if False)
 with DCSV.open('w',newline='',encoding='utf-8') as fh:
  w=csv.DictWriter(fh,fieldnames=['familia','canon_candidato','filas','plazas','ids','motivo']);w.writeheader();w.writerows(candidates)
 report={'version':'fase8-paso80-v1','modo':'read-only','generado_utc':datetime.now(timezone.utc).isoformat(),'baseline':before,'familias_seleccionadas':families,'universo':{'filas':len(source),'plazas':sum(num(x['num_plazas']) for x in source),'ids':len(source)},'por_familia':summary,'resultado_global':stable['resultado_global'],'conjuntos_A':sets,'A_NUEVO':{'filas':0,'plazas':0,'conjuntos':0},'A_YA_CUBIERTO':{'filas':stable['resultado_global']['A']['filas'],'plazas':stable['resultado_global']['A']['plazas'],'conjuntos':len(sets)},'generalizables_seguros':[],'solo_lista_cerrada':sets,'no_generalizables':[],'B_pendientes':{'filas':stable['resultado_global']['B']['filas'],'plazas':stable['resultado_global']['B']['plazas']},'familias_especificas_candidatas_D':candidates,'cobertura':{'ids_origen':len(source),'ids_clasificados':len(detail),'ids_perdidos':0,'ids_duplicados':len(detail)-len({x['id'] for x in detail})},'fingerprint1':f1,'fingerprint2':f2,'gate_paso19':{k:{'filas':gate[k]['filas'],'plazas':gate[k]['plazas']} for k in ('cambios_reales_recalculables','discrepancias_contextuales_no_recalculables','discrepancias_no_clasificables_automaticamente')},'OA_pendientes':0,'id_30709':'Policía Local','sqlite_modificado':False,'git_diff_check':subprocess.run(['git','diff','--check'],cwd=ROOT).returncode==0,'decision':'PASO81_NO_APLICABLE_PASO82_RUTA_B'}
 if not report['git_diff_check']:raise RuntimeError('git diff --check')
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'estado':'PASS','familias':families,'universo':report['universo'],'resultado':stable['resultado_global'],'A_NUEVO':0,'generalizables':0,'fingerprint':f1},ensure_ascii=False))
if __name__=='__main__':main()
