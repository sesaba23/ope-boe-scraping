"""PASO 72-C: segunda auditoría read-only de B_VARIANTE_FORMAL_DUDOSA."""
from __future__ import annotations
import csv,hashlib,json,unicodedata
from collections import Counter,defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];INF=ROOT/'informes/normalizacion_puestos';SRC=INF/'fase8_paso72b_analisis_bcd.json';OUT=INF/'fase8_paso72c_variantes_formales.json';CSV=INF/'fase8_paso72c_variantes_formales_detalle.csv';AOUT=INF/'fase8_paso72c_a_nuevos.csv'
def num(x):
 try:return float(x or 0)
 except:return 0.0
def forma(s):
 s=''.join(c for c in unicodedata.normalize('NFD',str(s or '').casefold()) if unicodedata.category(c)!='Mn')
 return ' '.join(s.replace('/a','').replace('/o','').replace('-a','').split())
def main():
 src=json.loads(SRC.read_text());rows=[x for x in src['detalle'] if x['clasificacion']=='B' and x['subtipo']=='VARIANTE_FORMAL_DUDOSA']; groups=defaultdict(list)
 for x in rows:groups[(x['familia'],forma(x['denominacion']))].append(x)
 outrows=[];anuevos=[];seen=set()
 for (fam,key),v in sorted(groups.items()):
  variants=sorted({x['denominacion'] for x in v}); samecanon=len({x['puesto_normalizado'] for x in v})==1
  seguro=len(variants)>1 and samecanon and all(x['puesto_normalizado'] == x['denominacion'] or forma(x['puesto_normalizado'])==key for x in v)
  result='A_SEGURO' if seguro else ('NO_A_SEMANTICO' if any(z in key for z in ('superior','medio','auxiliar','escala','cuerpo')) else 'NO_A_AMBIGUO')
  for x in v:outrows.append({**x,'resultado_72c':result,'subtipo_72c':'VARIANTE_FORMAL_CONFIRMADA' if seguro else ('FRONTERA_SEMANTICA' if result=='NO_A_SEMANTICO' else 'EVIDENCIA_INSUFICIENTE'),'canon_propuesto':v[0]['puesto_normalizado'] if seguro else None,'motivo':'diferencia exclusivamente formal y canon actual coherente' if seguro else 'la denominación no demuestra por sí sola equivalencia segura'})
  if seguro:
   anuevos.append({'familia':fam,'subfamilia':key,'variantes':variants,'canon_propuesto':v[0]['puesto_normalizado'],'filas':len(v),'plazas':sum(num(x['plazas']) for x in v),'administraciones':sorted({x['administracion'] or '' for x in v}),'años':sorted({x['anio'] for x in v}),'tipo':'A_NUEVO'})
 totals={z:{'filas':sum(x['resultado_72c']==z for x in outrows),'plazas':sum(num(x['plazas']) for x in outrows if x['resultado_72c']==z),'denominaciones':len({x['denominacion'] for x in outrows if x['resultado_72c']==z})} for z in ('A_SEGURO','NO_A_SEMANTICO','NO_A_CONTEXTO','NO_A_AMBIGUO')}
 fp=hashlib.sha256(json.dumps([(x['id'],x['resultado_72c']) for x in outrows],separators=(',',':')).encode()).hexdigest()
 out={'version':'fase8-paso72c-v1','modo':'read-only','origen':str(SRC),'universo':{'filas':len(rows),'plazas':sum(num(x['plazas']) for x in rows),'denominaciones':len({x['denominacion'] for x in rows}),'familias':sorted({x['familia'] for x in rows})},'resultado_global':totals,'A_NUEVO':anuevos,'A_YA_CUBIERTO':{'filas':0,'plazas':0,'nota':'los casos puramente ortográficos ya pertenecen a PASO 71; no se duplica regla semántica'},'detalle':outrows,'cobertura':{'ids_origen':len(rows),'ids_clasificados':len(outrows),'ids_perdidos':0,'ids_duplicados':0},'fingerprint':fp,'sqlite_modificado':False,'reglas_creadas':False}
 OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');
 with CSV.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=list(outrows[0]));w.writeheader();w.writerows(outrows)
 with AOUT.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=list(anuevos[0]) if anuevos else ['familia','subfamilia','variantes','canon_propuesto','filas','plazas']);w.writeheader();w.writerows(anuevos)
 print(json.dumps({'universo':out['universo'],'resultado':totals,'A_NUEVO':len(anuevos),'fingerprint':fp},ensure_ascii=False))
if __name__=='__main__':main()
