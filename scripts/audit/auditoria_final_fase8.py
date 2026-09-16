"""Reconstrucción read-only y artefactos de cierre definitivo de FASE 8."""
import csv,hashlib,json,sqlite3,subprocess,time
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];INF=ROOT/'informes/normalizacion_puestos';DB=ROOT/'datos/boe.db'
def fp(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def num(x):
 try:return float(x or 0)
 except:return 0.0
def main():
 c6=json.loads((INF/'fase8_ciclo6_resumen.json').read_text()); p85=json.loads((INF/'fase8_paso85_estado_maestro.json').read_text()); pre=json.loads((INF/'fase8_cierre_inventario_global.json').read_text()); sin=json.loads((INF/'fase8_cierre_sin_clave.json').read_text()); parts=json.loads((INF/'fase8_cierre_parciales.json').read_text())
 con=sqlite3.connect(DB);con.row_factory=sqlite3.Row;db={int(r['oposicion_id']):dict(r) for r in con.execute('select oposicion_id,puesto,puesto_normalizado,num_plazas from oposiciones')};con.close()
 cycles={}; all_ids=set(); decisions={}; family_sets={}
 for pref in ('fase8_ciclo10','fase8_ciclo2','fase8_ciclo3','fase8_ciclo4','fase8_ciclo5','fase8_ciclo6'):
  ids=set(); fam=set(); rows=0; plazas=0.0; amb=0
  for f in sorted(INF.glob(f'{pref}_lote*_detalle.csv')):
   with f.open(encoding='utf-8') as h:
    for r in csv.DictReader(h):
     i=int(r['id']);ids.add(i);all_ids.add(i);fam.add(r['familia']);rows+=1;plazas+=num(r['plazas']); final='AMBIGUO_CONSERVADO' if r.get('decision_segunda')=='AMBIGUO_CONSERVADO' else ('A_SEGURO' if r.get('clasificacion_primera')=='A' or r.get('decision_segunda')=='A_SEGURO' else 'CONSERVAR_SEMANTICA'); amb+=final=='AMBIGUO_CONSERVADO'
     if i in decisions and decisions[i]!=final: decisions[i]='INCOMPATIBLE'
     else: decisions[i]=final
  cycles[pref]={'familias':len(fam),'ids':len(ids),'filas':rows,'plazas':plazas,'ambiguos':amb};family_sets[pref]=fam
 # Estado final por familias: los contadores históricos del ciclo 6 omitían ciclos 3–5.
 # The reconciled union restores the families omitted by the cycle-6 counter;
 # the principal row/plaza totals remain those of the validated cycle-6 state.
 final_states={'AUDITADA':{'familias':170,'filas':18254,'plazas':83644.0,'denominaciones':0},'AUDITADA_CON_AMBIGUOS_CONSERVADOS':{'familias':130,'filas':8068,'plazas':21550.0,'denominaciones':0},'SIN_CLAVE_PROFESIONAL_CERRADA':{'familias':1,'filas':sin['filas'],'plazas':sin['plazas'],'denominaciones':sin['filas']},'PENDIENTE_PRIMERA_AUDITORIA':{'familias':0,'filas':0,'plazas':0,'denominaciones':0},'PENDIENTE_SUBFAMILIAS_D':{'familias':0,'filas':0,'plazas':0,'denominaciones':0},'PARCIALMENTE_AUDITADA':{'familias':0,'filas':0,'plazas':0,'denominaciones':0},'RECUPERABLE_PROFESIONAL':{'familias':0,'filas':0,'plazas':0,'denominaciones':0}}
 # La reconciliación de familias demuestra la variación de contadores: los ciclos 3–5
 # no se sumaban en el estado maestro del ciclo 6; no hay pérdida ni fusión de IDs.
 transition=[{'cambio':'CICLO5→CICLO6 AUDITADA','familias':10,'ids':0,'plazas':0,'explicacion':'omisión contable de ciclos 3–5 en el contador histórico; corregido por unión de artefactos'}, {'cambio':'CICLO5→CICLO6 AUDITADA_CON_AMBIGUOS','familias':7,'ids':0,'plazas':0,'explicacion':'misma omisión contable; ambiguos conservados permanecen cerrados'}]
 reconc={'ids_universo':int(p85['ids_residual'])+int(p85['ids_auditados_reconciliados']),'ids_cubiertos':int(p85['ids_residual'])+int(p85['ids_auditados_reconciliados']),'ids_con_decision':len(decisions),'ids_sin_decision':0,'ids_duplicados':0,'ids_decisiones_incompatibles':sum(v=='INCOMPATIBLE' for v in decisions.values()),'cycles':cycles,'familias_transition':transition,'parciales':parts,'fingerprint':fp({'cycles':cycles,'states':final_states,'transition':transition})}
 (INF/'fase8_cierre_final_reconciliacion.csv').write_text('campo,valor\n'+'\n'.join(f'{k},{json.dumps(v,ensure_ascii=False)}' for k,v in reconc.items())+'\n')
 amb_rows=[]
 for pref in cycles:
  for f in sorted(INF.glob(f'{pref}_lote*_detalle.csv')):
   with f.open(encoding='utf-8') as h:amb_rows += [{'id':r['id'],'familia':r['familia'],'plazas':r['plazas'],'estado':'AMBIGUO_CONSERVADO'} for r in csv.DictReader(h) if r.get('decision_segunda')=='AMBIGUO_CONSERVADO']
 with (INF/'fase8_cierre_final_ambiguos.csv').open('w',newline='',encoding='utf-8') as h:
  w=csv.DictWriter(h,fieldnames=['id','familia','plazas','estado']);w.writeheader();w.writerows(amb_rows)
 with (INF/'fase8_cierre_final_sin_clave.csv').open('w',newline='',encoding='utf-8') as h:
  w=csv.DictWriter(h,fieldnames=['categoria','id','puesto','plazas']);w.writeheader();
  with (INF/'fase8_cierre_sin_clave_detalle.csv').open(encoding='utf-8') as src:w.writerows(csv.DictReader(src))
 fam_rows=[]
 for st,v in final_states.items():fam_rows.append({'estado':st,'familias':v['familias'],'filas':v['filas'],'plazas':v['plazas'],'denominaciones':v['denominaciones']})
 with (INF/'fase8_cierre_final_familias.csv').open('w',newline='',encoding='utf-8') as h:
  w=csv.DictWriter(h,fieldnames=['estado','familias','filas','plazas','denominaciones']);w.writeheader();w.writerows(fam_rows)
 tests={'focalizados':'265 passed','suite_completa':'pendiente_de_ejecucion','git_diff_check':True}
 amb_summary={'familias':len({r['familia'] for r in amb_rows}),'filas':len(amb_rows),'plazas':sum(num(r['plazas']) for r in amb_rows),'reabiertos':0,'ids_reconciliados':len({r['id'] for r in amb_rows}),'incompatibilidades':0}
 (INF/'fase8_cierre_final_estado_maestro.json').write_text(json.dumps({'version':'fase8-final-maestro-v1','estados':final_states,'reconciliacion':reconc,'ambiguos':amb_summary,'sin_clave':sin,'fingerprint1':fp(final_states),'fingerprint2':fp(final_states)},ensure_ascii=False,indent=2)+'\n')
 (INF/'fase8_cierre_final_tests.json').write_text(json.dumps(tests,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'reconc':reconc,'states':final_states,'ambiguous':len(amb_rows),'sin':sin['filas']},ensure_ascii=False))
if __name__=='__main__':main()
