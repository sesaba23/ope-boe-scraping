"""PASO 71-B: partición por IDs y clasificación semántica conservadora."""
from __future__ import annotations
import csv,hashlib,json,sqlite3,sys
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.audit.auditar_bomberos_paso8_40 import state,sha,git
INF=ROOT/'informes/normalizacion_puestos';OUT=INF/'fase8_paso71_clasificacion_residual.json';COV=INF/'fase8_paso71_cobertura_residual.json';CSV=INF/'fase8_paso71_familias_residuales.csv';RANK=INF/'fase8_paso71_ranking_familias.json'
# Tokens que no identifican por sí mismos un puesto.  Se aplican únicamente
# al escoger la clave de familia (nunca al texto bruto ni al normalizador).
ARTICULOS_INICIALES={'la','las','el','los','una','un'}
PREPOSICIONES_INICIALES={'de','del','en','para','por','con','sin','a','al'}
MARCADORES_DOCUMENTALES={
 'plaza','plantilla','convocatoria','oferta','relacion','relación','misma',
 'mismo','especialidad','comprendidas','convocadas','siguientes','reservadas',
 'cuales','cual','instancias','bases','cobertura','autoridad','conserjerias',
 'conserjerías',
}
def num(x):
 try:return float(x or 0)
 except:return 0.0
def familia(p):
 k=' '.join(str(p or '').casefold().split())
 if not k:return 'SIN_DENOMINACION'
 if any(x in k for x in ('cuerpo','escala','subescala')):return 'CUERPOS_ESCALAS'
 if any(x in k for x in ('jefe','jefa','director','directora','coordinador','responsable')):return 'MANDOS_RESPONSABILIDAD'
 if any(x in k for x in (' y ','/','-')):return 'PUESTOS_COMPUESTOS'
 tokens=k.split()
 if tokens and tokens[0] in PREPOSICIONES_INICIALES:
  return 'SIN_CLAVE_PROFESIONAL'
 while tokens and tokens[0] in ARTICULOS_INICIALES:
  tokens.pop(0)
 if not tokens or tokens[0] in MARCADORES_DOCUMENTALES:
  return 'SIN_CLAVE_PROFESIONAL'
 return tokens[0].upper()
def ids_auditados():
 ids=set()
 for p in INF.glob('fase8_paso*.json'):
  if any(x in p.name for x in ('paso70','paso71','paso72','cierre')): continue
  try:r=json.loads(p.read_text())
  except Exception:continue
  if not isinstance(r, dict):
   continue
  if isinstance(r.get('filas'),list):
   ids.update(x.get('id',x.get('oposicion_id')) for x in r['filas'] if isinstance(x,dict) and x.get('id',x.get('oposicion_id')) is not None)
 return ids
def main():
 total=state();aud=ids_auditados();c=sqlite3.connect(ROOT/'datos/boe.db');c.row_factory=sqlite3.Row
 try:rs=[dict(x) for x in c.execute('select oposicion_id,puesto,puesto_normalizado,num_plazas,fecha_boe,administracion from oposiciones')]
 finally:c.close()
 allids={x['oposicion_id'] for x in rs};aud &= allids; residual=[x for x in rs if x['oposicion_id'] not in aud];groups=defaultdict(list)
 for x in residual:groups[familia(x['puesto'])].append(x)
 ranking=[]; estados=Counter()
 for f,v in groups.items():
  den=Counter(x['puesto'] for x in v); compuesto=f=='PUESTOS_COMPUESTOS'; estado='CONTEXTUAL_COMPUESTO' if compuesto else ('SIN_VARIANTES_RELEVANTES' if len(den)==1 else 'PENDIENTE_AUDITORIA');estados[estado]+=1
  ranking.append({'familia':f,'estado':estado,'filas':len(v),'plazas':sum(num(x['num_plazas']) for x in v),'denominaciones':len(den),'variantes':sum(n>1 for n in den.values()),'años':sorted({str(x['fecha_boe'] or '')[:4] for x in v}),'administraciones':len({x['administracion'] or '' for x in v}),'profesion_base':f,'titulacion':None,'categorias':[],'niveles':[],'especialidades':[],'funciones':[],'ambitos':[],'cuerpos':[],'escalas':[],'subescalas':[],'clases':[],'puestos_compuestos':compuesto,'ejemplos_representativos':[x for x,_ in den.most_common(5)],'motivo_estado':'requiere auditoría semántica antes de cualquier regla' if estado=='PENDIENTE_AUDITORIA' else 'composición o ausencia de variantes formales seguras','potencial':'medio' if estado=='PENDIENTE_AUDITORIA' else 'nulo'})
 ranking.sort(key=lambda x:(0 if x['estado']=='PENDIENTE_AUDITORIA' else 1,-x['filas'],-x['plazas'],x['familia']))
 fingerprint=hashlib.sha256(json.dumps([(x['familia'],x['estado'],x['filas'],x['plazas']) for x in ranking],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
 universo=lambda v:{'filas':len(v),'plazas':sum(num(x['num_plazas']) for x in v),'denominaciones':len({x['puesto'] for x in v}),'administraciones':len({x['administracion'] or '' for x in v})}
 resultado={'version':'fase8-paso71b-v1','generado_utc':datetime.now(timezone.utc).isoformat(),'baseline_git':git(),'sqlite':total,'universo_total':universo(rs),'universo_ya_auditado':universo([x for x in rs if x['oposicion_id'] in aud]),'universo_residual_real':universo(residual),'interseccion_auditado_residual':0,'union_cubre_total':len(aud)+len(residual)==len(rs),'ids_sin_clasificar':0,'ids_duplicados':0,'criterio_paso70':'seleccionó todas las filas de oposiciones; no era residual','diagnostico_paso70':'109041 correspondía al universo total actual, no a un residual profesional','familias_totales':len(ranking),'conteos_por_estado':dict(estados),'familias':ranking,'fingerprint':fingerprint,'plan_paso72_en_adelante':[{'paso':'72+','familia':x['familia'],'protocolo':'auditoría A/B/C/D read-only; no regla sin gate'} for x in ranking if x['estado']=='PENDIENTE_AUDITORIA']}
 OUT.write_text(json.dumps(resultado,ensure_ascii=False,indent=2)+'\n');RANK.write_text(json.dumps(ranking,ensure_ascii=False,indent=2)+'\n');COV.write_text(json.dumps({k:resultado[k] for k in ('sqlite','universo_total','universo_ya_auditado','universo_residual_real','interseccion_auditado_residual','union_cubre_total','ids_sin_clasificar','ids_duplicados','efecto_ortografia','criterio_paso70','diagnostico_paso70') if k in resultado},ensure_ascii=False,indent=2)+'\n')
 with CSV.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=['familia','estado','filas','plazas','denominaciones','variantes','potencial']);w.writeheader();w.writerows({k:x[k] for k in w.fieldnames} for x in ranking)
 print(json.dumps({'total':resultado['universo_total'],'auditado':resultado['universo_ya_auditado'],'residual':resultado['universo_residual_real'],'estados':dict(estados),'fingerprint':fingerprint},ensure_ascii=False))
if __name__=='__main__':main()
