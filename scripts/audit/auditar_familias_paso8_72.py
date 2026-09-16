"""PASO 72: primera auditoría read-only de las cinco familias prioritarias."""
from __future__ import annotations
import csv,hashlib,json,sqlite3,sys,unicodedata
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.audit.clasificar_residual_paso8_71b import ids_auditados
from scripts.audit.auditar_bomberos_paso8_40 import state,sha,git
INF=ROOT/'informes/normalizacion_puestos';RANK=INF/'fase8_paso71_ranking_familias.json';OUT=INF/'fase8_paso72_auditoria.json';CSV=INF/'fase8_paso72_detalle.csv'
SELECCION=('TÉCNICO','OFICIAL','AUXILIAR','AGENTE','CUERPOS_ESCALAS')
def n(x):
 try:return float(x or 0)
 except:return 0.0
def base(s):
 s=''.join(c for c in unicodedata.normalize('NFD',str(s or '').casefold()) if unicodedata.category(c)!='Mn')
 return ' '.join(s.replace('/a','').replace('/o','').replace('-a','').split())
def clas(r):
 k=base(r['puesto']); f=r['familia']
 if k==f.casefold():return 'A'
 if any(x in k for x in ('superior','medio','auxiliar','especialista','industrial','informatic','administracion especial','escala','cuerpo')):return 'D'
 if any(x in k for x in ('plantilla','servicios','municipal','provincial','centro','residencia','coordinador','jefe')):return 'C'
 return 'B'
def main():
 ranking=json.loads(RANK.read_text()); top=[x for x in ranking if x['estado']=='PENDIENTE_AUDITORIA' and x['familia'] in SELECCION]; top.sort(key=lambda x:SELECCION.index(x['familia']))
 ids=ids_auditados();c=sqlite3.connect(ROOT/'datos/boe.db');c.row_factory=sqlite3.Row
 try:rs=[dict(x) for x in c.execute('select oposicion_id,puesto,puesto_normalizado,num_plazas,fecha_boe,administracion from oposiciones') if x['oposicion_id'] not in ids]
 finally:c.close()
 filas=[]
 for r in rs:
  k=base(r['puesto'])
  f='CUERPOS_ESCALAS' if any(x in k for x in ('cuerpo','escala','subescala')) else next((x for x in SELECCION if k.startswith(base(x))),None)
  if f: filas.append({'id':r['oposicion_id'],'familia':f,'denominacion':r['puesto'],'puesto_normalizado':r['puesto_normalizado'],'plazas':r['num_plazas'],'anio':str(r['fecha_boe'] or '')[:4],'administracion':r['administracion'],'clasificacion':clas({**r,'familia':f})})
 por=defaultdict(list)
 for x in filas:por[x['familia']].append(x)
 resumen=[];conj=[]
 for f in SELECCION:
  v=por[f];cl={z:[x for x in v if x['clasificacion']==z] for z in 'ABCD'};resumen.append({'familia':f,'filas':len(v),'plazas':sum(n(x['plazas']) for x in v),'denominaciones':len({x['denominacion'] for x in v}),**{z:{'filas':len(cl[z]),'plazas':sum(n(x['plazas']) for x in cl[z]),'denominaciones':len({x['denominacion'] for x in cl[z]})} for z in 'ABCD'}})
 for f in SELECCION:
  groups=defaultdict(list)
  for x in por[f]:
   if x['clasificacion']=='A':groups[base(x['denominacion'])].append(x)
  conj += [{'id':'A'+str(i),'familia':f,'variantes':sorted({x['denominacion'] for x in v}),'canon_propuesto':v[0]['denominacion'],'filas':len(v),'plazas':sum(n(x['plazas']) for x in v)} for i,(k,v) in enumerate(sorted(groups.items()),1) if len(v)>1]
 out={'version':'fase8-paso72-v1','generado_utc':datetime.now(timezone.utc).isoformat(),'modo':'read-only','baseline_git':git(),'sqlite':state(),'ranking_fingerprint':hashlib.sha256(RANK.read_bytes()).hexdigest(),'familias_seleccionadas':top,'resumen':resumen,'conjuntos_A':conj,'casos_B':[x for x in filas if x['clasificacion']=='B'],'casos_C':[x for x in filas if x['clasificacion']=='C'],'casos_D':[x for x in filas if x['clasificacion']=='D'],'filas':filas,'cobertura':{'sin_clasificar':0,'solapamientos':0,'filas':len(filas),'clasificadas':sum(len(v) for v in por.values())},'decisiones_solicitadas_al_usuario':{'B':'decidir política; no se implementa','C':'decidir conservación de dimensiones; no se implementa','D':'decidir si se mantiene separado; no se implementa'}}
 OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');
 with CSV.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=list(filas[0]));w.writeheader();w.writerows(filas)
 print(json.dumps({'familias':SELECCION,'filas':len(filas),'resumen':resumen,'A':len(conj)},ensure_ascii=False))
if __name__=='__main__':main()
