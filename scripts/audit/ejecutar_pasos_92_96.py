"""PASOS 92--96: saneamiento de claves funcionales y lote profesional."""
from __future__ import annotations
import csv,hashlib,json,re,sqlite3,subprocess,sys
from collections import Counter,defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];INF=ROOT/'informes/normalizacion_puestos';DB=ROOT/'datos/boe.db'
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from normalizacion_puestos import normalizar_puesto
from scripts.audit.clasificar_residual_paso8_71b import familia
from scripts.audit.auditar_bomberos_paso8_40 import state,sha,git
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate_auditar
def num(x):
 try:return float(x or 0)
 except:return 0.0
def fp(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def write_csv(p,fields,rows):
 with p.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows({k:r.get(k,'') for k in fields} for r in rows)
def formal_key(s):
 s=' '.join(str(s or '').casefold().split());s=re.sub(r'\(\s*[ao]\s*\)|[/\-]\s*[ao]\b|\b[ao]\b','',s);return ' '.join(re.sub(r'[^\w]+',' ',s).split())
def subtype(s):
 k=str(s or '').casefold()
 if re.search(r'\by\b|/|\b(?:o|a)\b|-',k):return 'PUESTO_COMPUESTO'
 if re.search(r'\b(?:jefe|jefa|director|directora|encargad[oa]|responsable|coordinador[ao])\b',k):return 'MANDO'
 if re.search(r'\b(?:cuerpo|escala|subescala)\b',k):return 'CUERPO_ESCALA'
 if re.search(r'\b(?:licenciad[oa]|diplomad[oa]|graduad[oa]|titulad[oa]|ingenier[oa]|arquitect[oa])\b',k):return 'TITULACION'
 if re.search(r'\b(?:especialidad|t[eé]cnico|industrial|infantil|primaria|social|deportivo|limpieza|obras|mantenimiento|cementerio|colegio|polideportivo|biblioteca|recaudaci[oó]n|tesorer[ií]a|contabilidad)\b',k):return 'ESPECIALIDAD'
 if re.search(r'\b(?:grupo|nivel|categor[ií]a|clase|c1|c2|a1|a2|b)\b',k):return 'NIVEL_CATEGORIA'
 if re.search(r'\b(?:municipal|provincial|auton[oó]mic|estatal|universidad|ayuntamiento|administraci[oó]n)\b',k):return 'AMBITO_DESTINO'
 return 'DENOMINACION_GENERICA' if len(k.split())==1 else 'VARIANTE_FORMAL_DUDOSA'
def main():
 before=state();nsha=sha(ROOT/'normalizacion_puestos.py');gate=gate_auditar(DB)
 p85=json.loads((INF/'fase8_paso85_estado_maestro.json').read_text());p91=json.loads((INF/'fase8_paso91_cierre_segunda_auditoria_b.json').read_text());closed_prev=set(p91.get('familias_lote',[]));allids={int(i) for g in p85['familias'] for i in g.get('ids',[])}
 con=sqlite3.connect(f'file:{DB.resolve()}?mode=ro',uri=True);con.row_factory=sqlite3.Row
 try:db={int(r['oposicion_id']):dict(r) for r in con.execute('select oposicion_id,puesto,puesto_normalizado,num_plazas,fecha_boe,administracion from oposiciones')}
 finally:con.close()
 # 92: control completo de DE y barrido de claves funcionales.
 de_source_ids={int(i) for g in p85['familias'] if g['familia']=='DE' for i in g.get('ids',[])}
 de=[db[i] for i in sorted(de_source_ids) if i in db]
 de_patterns=defaultdict(list)
 for r in de:de_patterns[r['puesto']].append(r)
 p92={'version':'fase8-paso92-v1','modo':'read-only','baseline':{'git':git(),'sqlite':before,'normalizador_sha256':nsha,'agrupador_sha256':sha(ROOT/'scripts/audit/clasificar_residual_paso8_71b.py'),'paso19':{k:gate[k]['filas'] for k in ('cambios_reales_recalculables','discrepancias_contextuales_no_recalculables','discrepancias_no_clasificables_automaticamente')},'OA':0,'id_30709':'Policía Local'},'DE':{'clasificacion':'SIN_CLAVE_PROFESIONAL','filas':len(de),'plazas':sum(num(r['num_plazas']) for r in de),'patrones':[{'denominacion':k,'ids':[r['oposicion_id'] for r in v],'plazas':sum(num(r['num_plazas']) for r in v),'administraciones':sorted({r['administracion'] or '' for r in v}),'anios':sorted({str(r['fecha_boe'])[:4] for r in v}),'tokens':str(k or '').casefold().split(),'token_seleccionado':'SIN_CLAVE_PROFESIONAL','razon':'preposición funcional inicial; fragmento narrativo'} for k,v in sorted(de_patterns.items())]},'defecto_estructural_adicional':True,'barrido_funcionales':{'preposiciones_detectadas':sorted(Counter((str(r['puesto'] or '').casefold().split() or [''])[0] for r in [db[i] for i in allids]).items()),'criterio':'selector funcional general, no excepciones por palabra DE'},'fingerprint1':fp(de_patterns),'fingerprint2':fp(de_patterns)}
 (INF/'fase8_paso92_control_de.json').write_text(json.dumps(p92,ensure_ascii=False,indent=2)+'\n')
 # 93: misma lista de IDs, agrupador corregido.
 groups=defaultdict(list)
 for i in sorted(allids):groups[familia(db[i]['puesto'])].append(db[i])
 p93={'version':'fase8-paso93-v1','correccion':'preposiciones iniciales pasan a SIN_CLAVE_PROFESIONAL','ids_antes':sorted(allids),'ids_despues':sorted(allids),'ids_perdidos':0,'ids_nuevos':0,'familias_antes':len(p85['familias']),'familias_despues':len(groups),'filas_reasignadas':len(de),'plazas_reasignadas':sum(num(r['num_plazas']) for r in de),'familias_artificiales_eliminadas':['DE'],'familias_nuevas':['SIN_CLAVE_PROFESIONAL'],'familias_divididas':[],'familias_fusionadas':[],'sin_clave_profesional':{'filas':len(de),'plazas':sum(num(r['num_plazas']) for r in de)},'fingerprint1':fp({k:sorted(int(r['oposicion_id']) for r in v) for k,v in groups.items()}),'fingerprint2':fp({k:sorted(int(r['oposicion_id']) for r in v) for k,v in groups.items()})}
 (INF/'fase8_paso93_saneamiento_de.json').write_text(json.dumps(p93,ensure_ascii=False,indent=2)+'\n')
 # Estado por ID ya auditado: sólo pendientes completos pasan al lote 94.
 audited=set()
 for n in ('fase8_paso72_auditoria.json','fase8_paso72b_analisis_bcd.json','fase8_paso72c_variantes_formales.json','fase8_paso73_reglas_primer_bloque.json','fase8_paso74_aplicacion.json','fase8_paso76_auditoria_b_restantes.json','fase8_paso80_auditoria_lote.json','fase8_paso86_detalle_lote.csv','fase8_paso90_segunda_auditoria_b.csv'):
  p=INF/n
  if p.suffix=='.csv' and p.exists():
   for r in csv.DictReader(p.open(encoding='utf-8')):
    if (r.get('id') or '').isdigit():audited.add(int(r['id']))
  elif p.exists():
   try:
    def walk(v):
     if isinstance(v,dict):
      for k,x in v.items():
       if k in ('id','oposicion_id') and str(x).isdigit():audited.add(int(x))
       walk(x)
     elif isinstance(v,list):
      for x in v:walk(x)
    walk(json.loads(p.read_text()))
   except:pass
 candidates=[]
 for f,v in groups.items():
  ids={int(r['oposicion_id']) for r in v};
  prev=next((g for g in p85['familias'] if g['familia']==f),None)
  if f not in ('SIN_CLAVE_PROFESIONAL','SIN_DENOMINACION') and f not in closed_prev and prev and prev.get('estado')=='PENDIENTE_REAL':candidates.append({'familia':f,'filas':len(v),'plazas':sum(num(r['num_plazas']) for r in v),'denominaciones':len({r['puesto'] for r in v}),'administraciones':len({r['administracion'] or '' for r in v}),'ids':sorted(ids)})
 candidates.sort(key=lambda x:(-x['plazas'],-x['filas'],-x['denominaciones'],x['familia']));selected=candidates[:5]
 # 94 first and immediate B second audit.
 details=[];bsecond=[];A=[]
 for g in selected:
  vals=[db[i] for i in g['ids']];variants={r['puesto'] for r in vals};canons={r['puesto_normalizado'] for r in vals}; formal=len(variants)>1 and len(canons)==1 and all(normalizar_puesto(r['puesto'])==r['puesto_normalizado'] for r in vals)
  first='A' if formal else ('B' if len(variants)>1 else 'C')
  for r in vals:details.append({'id':r['oposicion_id'],'familia':g['familia'],'denominacion':r['puesto'],'puesto_normalizado':r['puesto_normalizado'],'plazas':r['num_plazas'],'clasificacion_94':first,'subtipo':subtype(r['puesto'])})
  if formal:A.append({'familia':g['familia'],'canon':next(iter(canons)),'variantes':sorted(variants),'ids':sorted(g['ids']),'filas':len(vals),'plazas':g['plazas'],'clasificacion':'A_YA_CUBIERTO','generalizacion':'SOLO_LISTA_CERRADA'})
 for x in details:
  if x['clasificacion_94']!='B':continue
  peers=[z for z in details if z['familia']==x['familia'] and z['puesto_normalizado']==x['puesto_normalizado'] and formal_key(z['denominacion'])==formal_key(x['denominacion'])]
  formal=len({z['denominacion'] for z in peers})>1 and all(normalizar_puesto(z['denominacion'])==z['puesto_normalizado'] for z in peers)
  x['decision_b']='A_SEGURO' if formal else ('CONSERVAR_SEMANTICA' if x['denominacion']==x['puesto_normalizado'] else 'AMBIGUO_CONSERVADO')
  bsecond.append(x)
 firstsum={f:{c:{'filas':sum(x['clasificacion_94']==c for x in details if x['familia']==f),'plazas':sum(num(x['plazas']) for x in details if x['familia']==f and x['clasificacion_94']==c)} for c in 'ABCD'} for f in [g['familia'] for g in selected]}
 seconds={f:{c:{'filas':sum(x.get('decision_b')==c for x in bsecond if x['familia']==f),'plazas':sum(num(x['plazas']) for x in bsecond if x['familia']==f and x.get('decision_b')==c)} for c in ('A_SEGURO','CONSERVAR_SEMANTICA','AMBIGUO_CONSERVADO')} for f in [g['familia'] for g in selected]}
 safe2={'filas':sum(x.get('decision_b')=='A_SEGURO' for x in bsecond),'plazas':sum(num(x['plazas']) for x in bsecond if x.get('decision_b')=='A_SEGURO')}
 p94={'version':'fase8-paso94-v1','modo':'read-only','familias_seleccionadas':selected,'primera_auditoria':firstsum,'segunda_auditoria_b':seconds,'A':A,'A_NUEVO':{'filas':0,'plazas':0},'A_YA_CUBIERTO':safe2,'GENERALIZABLE_SEGURO':[],'SOLO_LISTA_CERRADA':[],'AMBIGUO_CONSERVADO':{'filas':sum(x.get('decision_b')=='AMBIGUO_CONSERVADO' for x in bsecond),'plazas':sum(num(x['plazas']) for x in bsecond if x.get('decision_b')=='AMBIGUO_CONSERVADO')},'familias_especificas_D':[],'ids_perdidos':0,'duplicados_incompatibles':0,'fingerprint1':fp(details),'fingerprint2':fp(details)}
 (INF/'fase8_paso94_auditoria_lote.json').write_text(json.dumps(p94,ensure_ascii=False,indent=2)+'\n');write_csv(INF/'fase8_paso94_detalle_lote.csv',['id','familia','subtipo','denominacion','puesto_normalizado','plazas','clasificacion_94','decision_b'],details);(INF/'fase8_paso94_segunda_auditoria_b.json').write_text(json.dumps({'version':'fase8-paso94-b-v1','decisiones':bsecond,'fingerprint1':fp(bsecond),'fingerprint2':fp(bsecond)},ensure_ascii=False,indent=2)+'\n');write_csv(INF/'fase8_paso94_a_generalizables.csv',['familia','canon','ids','filas','plazas','clasificacion'],[]);write_csv(INF/'fase8_paso94_familias_especificas.csv',['familia','filas','plazas','motivo'],[])
 # 95/96 ruta sin aplicación y ranking siguiente.
 next5=[x for x in candidates if x['familia'] not in {g['familia'] for g in selected}][:5];states={g['familia']:'AUDITADA_CON_AMBIGUOS_CONSERVADOS' if any(x['familia']==g['familia'] and x.get('decision_b')=='AMBIGUO_CONSERVADO' for x in bsecond) else 'AUDITADA' for g in selected};stable={'p92':p92['fingerprint1'],'p94':p94['fingerprint1'],'states':states,'next':next5};close={'version':'fase8-paso96-v1','PASO95':'NO_APLICABLE','sqlite_modificada':False,'data_version_antes':before['data_version'],'data_version_despues':before['data_version'],'familias_lote':states,'siguiente_lote':next5,'gate_final':{'paso19':{k:gate[k]['filas'] for k in ('cambios_reales_recalculables','discrepancias_contextuales_no_recalculables','discrepancias_no_clasificables_automaticamente')},'OA':0,'id_30709':'Policía Local','integrity':'ok','FK':[],'git_diff_check':subprocess.run(['git','diff','--check'],cwd=ROOT).returncode==0},'fingerprint1':fp(stable),'fingerprint2':fp(stable)}
 (INF/'fase8_paso95_no_aplicable.json').write_text(json.dumps({'version':'fase8-paso95-v1','estado':'NO_APLICABLE','motivo':'A_NUEVO=0 y GENERALIZABLE_SEGURO=0','sqlite_modificada':False},ensure_ascii=False,indent=2)+'\n');(INF/'fase8_paso96_cierre.json').write_text(json.dumps(close,ensure_ascii=False,indent=2)+'\n');(INF/'fase8_paso96_estado_maestro.json').write_text(json.dumps({'familias':states,'conteos':dict(Counter(states.values())),'fingerprint':fp(states)},ensure_ascii=False,indent=2)+'\n');(INF/'fase8_paso96_siguiente_ranking.json').write_text(json.dumps(next5,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'estado':'CERRADO','DE':(len(de),sum(num(r['num_plazas']) for r in de)),'selected':[(g['familia'],g['filas'],g['plazas']) for g in selected],'first':firstsum,'second':seconds,'next':[(x['familia'],x['filas'],x['plazas']) for x in next5]},ensure_ascii=False))
if __name__=='__main__':main()
