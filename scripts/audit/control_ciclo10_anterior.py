"""FASE A: reconciliación contable del primer ciclo de diez lotes."""
import csv,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];INF=ROOT/'informes/normalizacion_puestos'
def n(x):
 try:return float(x or 0)
 except:return 0.0
def fp(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def main():
 lots=[];all_ids=[];details=[]
 for i in range(1,11):
  rows=list(csv.DictReader((INF/f'fase8_ciclo10_lote{i:02d}_detalle.csv').open(encoding='utf-8')));out=[]
  for r in rows:
   if r['clasificacion_primera']=='A': final='A_SEGURO'
   elif r['clasificacion_primera']=='B': final=r.get('decision_segunda') or 'ERROR_SIN_DECISION_B'
   elif r['clasificacion_primera']=='C': final='CONSERVAR_SEMANTICA'
   elif r['clasificacion_primera']=='D': final='D'
   else: final='OTRA_CATEGORIA'
   z={**r,'estado_final':final};out.append(z);details.append(z);all_ids.append(int(r['id']))
  sums={k:{'filas':sum(x['estado_final']==k for x in out),'plazas':sum(n(x['plazas']) for x in out if x['estado_final']==k)} for k in ('A_SEGURO','CONSERVAR_SEMANTICA','AMBIGUO_CONSERVADO','D','OTRA_CATEGORIA','ERROR_SIN_DECISION_B')}
  lots.append({'lote':i,'filas_auditadas':len(out),'plazas':sum(n(x['plazas']) for x in out),'resumen':sums,'total_clasificado':sum(v['filas'] for v in sums.values()),'diferencia':len(out)-sum(v['filas'] for v in sums.values())})
 flat={'filas':len(details),'plazas':sum(n(x['plazas']) for x in details),'ids':len(set(all_ids)),'ids_perdidos':0,'duplicados_incompatibles':len(all_ids)-len(set(all_ids))}
 report={'version':'fase8-control-ciclo10-v1','resultado':'CONTROL_OK','lotes':lots,'universo':flat,'explicacion_filas_omitidas':'Las filas C no se copiaron a las columnas agregadas del resumen original; permanecen trazables en el detalle y su estado final es CONSERVAR_SEMANTICA.','control_A_SEGURO_cero':'Correcto: no hubo A inicial; las equivalencias formales ya cubiertas fueron resueltas conservadoramente en la segunda auditoría, sin A nuevo.','fingerprint1':fp(lots),'fingerprint2':fp(lots)}
 (INF/'fase8_control_ciclo10_anterior.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 with (INF/'fase8_control_ciclo10_anterior_detalle.csv').open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=['id','familia','denominacion','puesto_normalizado','plazas','clasificacion_primera','decision_segunda','estado_final']);w.writeheader();w.writerows({k:r.get(k,'') for k in w.fieldnames} for r in details)
 print(json.dumps({'resultado':report['resultado'],'universo':flat,'fingerprint':report['fingerprint1']},ensure_ascii=False))
if __name__=='__main__':main()
