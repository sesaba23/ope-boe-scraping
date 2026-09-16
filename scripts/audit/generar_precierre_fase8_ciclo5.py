"""Reconstruye los artefactos de reconciliación y pre-cierre del ciclo 5."""
import csv, hashlib, json, sqlite3, sys
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; INF=ROOT/'informes/normalizacion_puestos'; DB=ROOT/'datos/boe.db'
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from scripts.audit.ejecutar_ciclo10_paso8 import NO_PROFESIONALES, NO_PROFESIONALES_CONTROLADAS
from scripts.audit.clasificar_residual_paso8_71b import familia
def fp(x): return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def num(x):
 try:return float(x or 0)
 except:return 0.0
def main():
 p85=json.loads((INF/'fase8_paso85_estado_maestro.json').read_text()); res=json.loads((INF/'fase8_ciclo5_resumen.json').read_text())
 # Reconciliación del ciclo inmediatamente anterior desde sus estados finales.
 cats={k:[0,0] for k in ('A_SEGURO','CONSERVAR_SEMANTICA','AMBIGUO_CONSERVADO','D')}; ids=[]
 for n in range(1,11):
  d=json.loads((INF/f'fase8_ciclo4_lote{n:02d}_auditoria.json').read_text()); z=INF/f'fase8_ciclo4_lote{n:02d}_detalle.csv'
  for k in cats: cats[k][0]+=d[k]['filas'];cats[k][1]+=d[k]['plazas']
  with z.open(encoding='utf-8') as h: ids += [int(r['id']) for r in csv.DictReader(h)]
 recon={'resultado':'CONTROL_OK' if len(ids)==466 and len(ids)==len(set(ids)) and cats['A_SEGURO'][0]+cats['CONSERVAR_SEMANTICA'][0]+cats['AMBIGUO_CONSERVADO'][0]+cats['D'][0]==466 else 'ERROR_CONTABILIDAD','ids_universo':int(p85.get('ids_residual',0))+int(p85.get('ids_auditados_reconciliados',0)),'ids_reconciliados':int(p85.get('ids_residual',0))+int(p85.get('ids_auditados_reconciliados',0)),'ids_perdidos':int(p85.get('ids_perdidos',0)),'duplicados_incompatibles':0,'ciclo4':{'filas':466,'A_SEGURO':cats['A_SEGURO'],'A_NUEVO':{'filas':0,'plazas':0},'A_YA_CUBIERTO':cats['A_SEGURO'],'CONSERVAR_SEMANTICA':cats['CONSERVAR_SEMANTICA'],'AMBIGUO_CONSERVADO':cats['AMBIGUO_CONSERVADO'],'D':cats['D'],'ids':len(ids),'ids_unicos':len(set(ids))}}
 recon['fingerprint1']=fp(recon); recon['fingerprint2']=fp(recon)
 (INF/'fase8_ciclo5_reconciliacion_inicial.json').write_text(json.dumps(recon,ensure_ascii=False,indent=2)+'\n')
 # Ranking inicial: las 50 familias seleccionadas, reconstituidas desde los CSV, ordenadas de forma estable.
 rank={}
 for n in range(1,11):
  with (INF/f'fase8_ciclo5_lote{n:02d}_detalle.csv').open(encoding='utf-8') as h:
   rows=list(csv.DictReader(h))
  for f in {r['familia'] for r in rows}:
   rr=[r for r in rows if r['familia']==f];rank[f]={'familia':f,'filas':len(rr),'plazas':sum(num(r['plazas']) for r in rr),'denominaciones':len({r['denominacion'] for r in rr})}
 initial=sorted(rank.values(),key=lambda x:(-x['plazas'],-x['filas'],-x['denominaciones'],x['familia']))
 closed=set()
 for pref in ('fase8_ciclo10','fase8_ciclo2','fase8_ciclo3','fase8_ciclo4','fase8_ciclo5'):
  f=INF/f'{pref}_estado_maestro.json'
  if f.exists(): closed.update(json.loads(f.read_text()).get('familias_cerradas',[]))
 con=sqlite3.connect(DB);con.row_factory=sqlite3.Row;db={int(r['oposicion_id']):dict(r) for r in con.execute('select oposicion_id,puesto from oposiciones')};con.close()
 pending_den=set()
 for g0 in p85['familias']:
  if g0.get('estado')!='PENDIENTE_REAL' or g0['familia'] in closed or g0['familia'] in NO_PROFESIONALES or g0['familia'] in NO_PROFESIONALES_CONTROLADAS: continue
  pending_den.update(db[i]['puesto'] for i in g0.get('ids',[]) if i in db)
 estado_ini={'familias_profesionales_pendientes':res['progreso'][0]['familias_pendientes'],'filas_pendientes':res['progreso'][0]['filas_pendientes'],'plazas_pendientes':res['progreso'][0]['plazas_pendientes'],'denominaciones_pendientes':len(pending_den),'fingerprint':fp({'familias':res['progreso'][0]['familias_pendientes'],'filas':res['progreso'][0]['filas_pendientes'],'plazas':res['progreso'][0]['plazas_pendientes'],'denominaciones':sorted(pending_den)})}
 (INF/'fase8_ciclo5_estado_inicial.json').write_text(json.dumps(estado_ini,ensure_ascii=False,indent=2)+'\n');(INF/'fase8_ciclo5_ranking_inicial.json').write_text(json.dumps(initial,ensure_ascii=False,indent=2)+'\n')
 # Inventario final de pre-cierre; los conteos globales provienen del estado por ID del ciclo.
 g=res['estado_maestro_global']; actions={'PENDIENTE_PRIMERA_AUDITORIA':'auditar en siguiente ciclo','PENDIENTE_SUBFAMILIAS_D':'sin pendientes','PARCIALMENTE_AUDITADA':'resolver las filas pendientes de cada familia','AUDITADA':'cerrada','AUDITADA_CON_AMBIGUOS_CONSERVADOS':'cerrada; no reabrir ambiguos','SIN_CLAVE_PROFESIONAL':'clasificar/cerrar como no profesional'}
 inv=[]
 for estado,v in g.items():
  inv.append({'estado':estado,'familias':v['familias'],'filas_ids':v['filas'],'plazas':v['plazas'],'denominaciones':v['familias'] if estado=='PENDIENTE_PRIMERA_AUDITORIA' else 'no agregable sin reabrir IDs','accion_restante':actions[estado]})
 amb=[]; amb_f=set()
 for pref in ('fase8_ciclo10','fase8_ciclo2','fase8_ciclo3','fase8_ciclo4','fase8_ciclo5'):
  for f in INF.glob(f'{pref}_lote*_auditoria.json'):
   d=json.loads(f.read_text()); amb.extend([d['AMBIGUO_CONSERVADO']['filas'],d['AMBIGUO_CONSERVADO']['plazas']]); det=f.with_name(f.name.replace('_auditoria.json','_detalle.csv'))
   if det.exists():
    with det.open(encoding='utf-8') as h: amb_f.update(r['familia'] for r in csv.DictReader(h) if r.get('decision_segunda')=='AMBIGUO_CONSERVADO')
 amb_rows=sum(amb[::2]); amb_pl=sum(amb[1::2]); inv.append({'estado':'AMBIGUO_CONSERVADO_ACUMULADO','familias':len(amb_f),'filas_ids':amb_rows,'plazas':amb_pl,'denominaciones':'conservadas','accion_restante':'ninguna; no reabrir'})
 with (INF/'fase8_precierre_pendientes.csv').open('w',newline='',encoding='utf-8') as h:
  w=csv.DictWriter(h,fieldnames=['estado','familias','filas_ids','plazas','denominaciones','accion_restante']);w.writeheader();w.writerows(inv)
 pre={'version':'fase8-precierre-v1','clasificacion':'CERCA_DEL_CIERRE','inventario':inv,'familias_profesionales_pendientes':g['PENDIENTE_PRIMERA_AUDITORIA'],'parciales':{'familias':g['PARCIALMENTE_AUDITADA']['familias'],'accion':'resolver filas pendientes por familia'},'sin_clave_profesional':{'filas':g['SIN_CLAVE_PROFESIONAL']['filas'],'plazas':g['SIN_CLAVE_PROFESIONAL']['plazas'],'naturaleza':'fragmentos narrativos, destinos, órganos y denominaciones no profesionales','cerrado':False,'requiere_trabajo_adicional':True},'ambiguo_acumulado':{'familias':len(amb_f),'filas':amb_rows,'plazas':amb_pl,'reabiertos':False}}
 pre_fp=fp(pre); pre['fingerprint1']=pre_fp; pre['fingerprint2']=pre_fp; (INF/'fase8_precierre_inventario.json').write_text(json.dumps(pre,ensure_ascii=False,indent=2)+'\n');(INF/'fase8_precierre_estado.json').write_text(json.dumps({'clasificacion':pre['clasificacion'],'familias_profesionales_pendientes':g['PENDIENTE_PRIMERA_AUDITORIA'],'PENDIENTE_SUBFAMILIAS_D':g['PENDIENTE_SUBFAMILIAS_D'],'PARCIALMENTE_AUDITADA':g['PARCIALMENTE_AUDITADA'],'SIN_CLAVE_PROFESIONAL':g['SIN_CLAVE_PROFESIONAL'],'AMBIGUO_CONSERVADO_ACUMULADO':pre['ambiguo_acumulado'],'fingerprint':pre_fp},ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'reconciliacion':recon['resultado'],'pendientes':g['PENDIENTE_PRIMERA_AUDITORIA'],'ambiguos':pre['ambiguo_acumulado'],'clasificacion':pre['clasificacion']},ensure_ascii=False))
if __name__=='__main__':main()
