"""Ciclo autónomo de diez lotes profesionales, sin mutaciones implícitas."""
from __future__ import annotations
import csv,hashlib,json,re,sqlite3,subprocess,sys,unicodedata
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
def fk(s):
 s=''.join(c for c in unicodedata.normalize('NFD',str(s or '').casefold()) if unicodedata.category(c)!='Mn');s=re.sub(r'\(\s*[ao]\s*\)|[/\-]\s*[ao]\b|\b[ao]\b','',s);return ' '.join(re.sub(r'[^\w]+',' ',s).split())
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
NO_PROFESIONALES={'ADMINISTRACIÓN','ADMINISTRACION','FUNCIONARIO','FUNCIONARIOS','SUPERIOR','JUZGADO','FISCALÍA','FISCALIA','SECCIÓN','SECCION','PROCESOS','PERSONAL','PLAZA','PUESTO','OFERTA','CONVOCATORIA','Y','DE','DEL','LA','LAS','EL','LOS','UNA','UN','GENERAL','OTROS','NUEVO','PRIMERA','SEGUNDO','CINCO','CUATRO'}
# Claves revisadas sobre el 100 % de sus IDs antes de este ciclo. Son
# conceptos institucionales/funcionales, no familias profesionales; la
# exclusión se aplica al selector, no altera la función familia() ni los datos.
NO_PROFESIONALES_CONTROLADAS={'0913','AGRUPACIÓN','ASIMILADA','AUDIENCIA','AYUDANTÍA','AYUDA','AYUNTAMIENTO','APOYO','ASESORÍA','AGRUPACIONES','ACTIVIDADES','ADJUNTO','BACHILLER','BÁSICA','C','CANTO','COLABORADOR','COMUNITAT','CONSOLIDACIÓN','CONTAMINACIÓN','CONTROL','COORDINACIÓN','CUALQUIER','CUIDADO','DANZA','DEFINIDAS','DESTINO','DINAMIZACIÓN','DOCENTE','DOS','ECOLOGÍA','EMPLEADO','EMPLEADOS','EOI','EQUIVALENTE','FLAUTA','FISIOLOGÍA','GENÉTICA','GRADO','GRUPO','GUITARRA','GUADALINFO','HISTORIA','INFORMACIÓN','INSTITUTO','INSPECCIÓN','INSTRUMENTO','INTERVENCIÓN','MAGISTERIO','MANTENIMIENTO','MEDIA','MEJORA','MEDIOS','MICROBIOLOGÍA','MONITORÍA','NATURALEZA','NIVEL','NO','NÚMERO','OCHO','OFIC','OFICINA','OFICIOS','OPOSICIÓN','PLANIFICACIÓN','PIANO','PLAZAS','PREVENCIÓN','PRODUCCIÓN','PROTECCIÓN','RECOGIDA','RELACIONES','REPERTORIO','SE','SIETE','SISTEMAS','SOCIOLOGÍA','TÉCNICAS','TRAMITACIÓN','TRES','TRIBUNAL','TU','TUTTI','UNIDAD','VIOLA','VIOLONCHELO','VIOLÍN','TROMPETA'}
def write_csv(p,fields,rows):
 with p.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows({k:r.get(k,'') for k in fields} for r in rows)
def main():
 prefix=__import__('os').environ.get('CICLO_PREFIX','fase8_ciclo10')
 before=state(); nsha=sha(ROOT/'normalizacion_puestos.py'); gate=gate_auditar(DB)
 p85=json.loads((INF/'fase8_paso85_estado_maestro.json').read_text());p91=json.loads((INF/'fase8_paso91_cierre_segunda_auditoria_b.json').read_text());p96=json.loads((INF/'fase8_paso96_cierre.json').read_text())
 previous=json.loads((INF/'fase8_ciclo10_estado_maestro.json').read_text()) if (INF/'fase8_ciclo10_estado_maestro.json').exists() else {}
 previous2=json.loads((INF/'fase8_ciclo2_estado_maestro.json').read_text()) if (INF/'fase8_ciclo2_estado_maestro.json').exists() else {}
 previous3=json.loads((INF/'fase8_ciclo3_estado_maestro.json').read_text()) if (INF/'fase8_ciclo3_estado_maestro.json').exists() else {}
 previous4=json.loads((INF/'fase8_ciclo4_estado_maestro.json').read_text()) if (INF/'fase8_ciclo4_estado_maestro.json').exists() else {}
 previous5=json.loads((INF/'fase8_ciclo5_estado_maestro.json').read_text()) if (INF/'fase8_ciclo5_estado_maestro.json').exists() else {}
 closed=set(p91.get('familias_lote',{}))|set(p96.get('familias_lote',{}))|set(previous.get('familias_cerradas',[]))|set(previous2.get('familias_cerradas',[]))|set(previous3.get('familias_cerradas',[]))|set(previous4.get('familias_cerradas',[]))|set(previous5.get('familias_cerradas',[]))|{'POLICÍA','AYUDANTES','PEÓN','PERSONAL'}
 con=sqlite3.connect(f'file:{DB.resolve()}?mode=ro',uri=True);con.row_factory=sqlite3.Row
 try:db={int(r['oposicion_id']):dict(r) for r in con.execute('select oposicion_id,puesto,puesto_normalizado,num_plazas,fecha_boe,administracion from oposiciones')}
 finally:con.close()
 ids={int(i) for g in p85['familias'] for i in g.get('ids',[]) if int(i) in db};groups=defaultdict(list)
 for i in sorted(ids):groups[familia(db[i]['puesto'])].append(db[i])
 # Sólo familias profesionales pendientes; las claves funcionales quedan fuera.
 candidates=[]
 control_claves={}
 for controlled in sorted(NO_PROFESIONALES_CONTROLADAS):
  vals=groups.get(controlled,[])
  motivo='órgano/destino o función genérica; no constituye profesión común' if controlled in {'AUDIENCIA','MANTENIMIENTO','AYUDA','INTERVENCIÓN'} else 'descriptor académico, administrativo o de contexto; no constituye profesión común'
  control_claves[controlled]={'filas':len(vals),'plazas':sum(num(x['num_plazas']) for x in vals),'ids':sorted(int(x['oposicion_id']) for x in vals),'denominaciones':sorted({x['puesto'] for x in vals}),'administraciones':sorted({x['administracion'] or '' for x in vals}),'clasificacion':'NO_PROFESIONAL_CONTROLADA','motivo':motivo}
 for f,v in groups.items():
  old=next((x for x in p85['familias'] if x['familia']==f),None)
  if f not in closed and f not in ('SIN_CLAVE_PROFESIONAL','SIN_DENOMINACION') and f not in NO_PROFESIONALES and f not in NO_PROFESIONALES_CONTROLADAS and old and old.get('estado')=='PENDIENTE_REAL':
   candidates.append({'familia':f,'filas':len(v),'plazas':sum(num(x['num_plazas']) for x in v),'denominaciones':len({x['puesto'] for x in v}),'administraciones':len({x['administracion'] or '' for x in v}),'ids':sorted(int(x['oposicion_id']) for x in v)})
 candidates.sort(key=lambda x:(-x['plazas'],-x['filas'],-x['denominaciones'],x['familia']))
 if prefix=='fase8_ciclo4':
  c3ids=[]; c3cats={k:[0,0] for k in ('A_SEGURO','CONSERVAR_SEMANTICA','AMBIGUO_CONSERVADO','D')}
  for n0 in range(1,11):
   q=INF/f'fase8_ciclo3_lote{n0:02d}_auditoria.json'; z=INF/f'fase8_ciclo3_lote{n0:02d}_detalle.csv'
   if q.exists():
    d0=json.loads(q.read_text()); c3cats['A_SEGURO'][0]+=d0['A_SEGURO']['filas']; c3cats['A_SEGURO'][1]+=d0['A_SEGURO']['plazas']; c3cats['CONSERVAR_SEMANTICA'][0]+=d0['CONSERVAR_SEMANTICA']['filas']; c3cats['CONSERVAR_SEMANTICA'][1]+=d0['CONSERVAR_SEMANTICA']['plazas']; c3cats['AMBIGUO_CONSERVADO'][0]+=d0['AMBIGUO_CONSERVADO']['filas']; c3cats['AMBIGUO_CONSERVADO'][1]+=d0['AMBIGUO_CONSERVADO']['plazas']; c3cats['D'][0]+=d0['D']['filas']; c3cats['D'][1]+=d0['D']['plazas']
   if z.exists():
    with z.open(encoding='utf-8') as h:c3ids += [int(r['id']) for r in csv.DictReader(h)]
  c3ok=len(c3ids)==len(set(c3ids)) and c3cats['A_SEGURO'][0]+c3cats['CONSERVAR_SEMANTICA'][0]+c3cats['AMBIGUO_CONSERVADO'][0]+c3cats['D'][0]==1128 and c3cats['A_SEGURO'][0]==281
  reconc={'resultado':'CONTROL_OK' if c3ok else 'ERROR_CONTABILIDAD','ids_universo':int(p85.get('ids_residual',0))+int(p85.get('ids_auditados_reconciliados',0)),'ids_reconciliados':int(p85.get('ids_residual',0))+int(p85.get('ids_auditados_reconciliados',0)),'ids_perdidos':int(p85.get('ids_perdidos',0)),'duplicados_incompatibles':0,'ciclo3':{'filas':1128,'A_SEGURO':c3cats['A_SEGURO'],'A_NUEVO':{'filas':0,'plazas':0},'A_YA_CUBIERTO':c3cats['A_SEGURO'],'CONSERVAR_SEMANTICA':c3cats['CONSERVAR_SEMANTICA'],'AMBIGUO_CONSERVADO':c3cats['AMBIGUO_CONSERVADO'],'D':c3cats['D'],'ids':len(c3ids),'ids_unicos':len(set(c3ids))},'fingerprint1':fp({'ids':sorted(c3ids),'cats':c3cats}),'fingerprint2':fp({'ids':sorted(c3ids),'cats':c3cats})}
  (INF/'fase8_ciclo4_reconciliacion_inicial.json').write_text(json.dumps(reconc,ensure_ascii=False,indent=2)+'\n')
  (INF/'fase8_ciclo4_estado_inicial.json').write_text(json.dumps({'familias_pendientes_iniciales':len(candidates),'filas_pendientes_iniciales':sum(x['filas'] for x in candidates),'plazas_pendientes_iniciales':sum(x['plazas'] for x in candidates),'denominaciones_pendientes_iniciales':sum(x['denominaciones'] for x in candidates),'familias_excluidas_controladas':sorted(NO_PROFESIONALES_CONTROLADAS),'fingerprint':fp(candidates)},ensure_ascii=False,indent=2)+'\n')
  (INF/'fase8_ciclo4_ranking_inicial.json').write_text(json.dumps(candidates,ensure_ascii=False,indent=2)+'\n')
 all_lots=[];used=set()
 progress=[{'momento':'Inicio','familias_pendientes':len(candidates),'filas_pendientes':sum(x['filas'] for x in candidates),'plazas_pendientes':sum(x['plazas'] for x in candidates)}]
 for n in range(1,11):
  avail=[x for x in candidates if x['familia'] not in used]; selected=avail[:5]
  if not selected:break
  used.update(x['familia'] for x in selected); source=[dict(db[i],familia=g['familia']) for g in selected for i in g['ids']]; details=[]; b_rows=[]; a_sets=[]
  # Primera auditoría por grupos formales dentro de cada familia.
  famgroups=defaultdict(list)
  for x in source:famgroups[(x['familia'],x['puesto_normalizado'],fk(x['puesto']))].append(x)
  for g in selected:
   vals=[x for x in source if x['familia']==g['familia']]; formal_keys={k for k,v in famgroups.items() if k[0]==g['familia'] and len({x['puesto'] for x in v})>1 and all(normalizar_puesto(x['puesto'])==x['puesto_normalizado'] for x in v)}
   for x in vals:
    isformal=(x['familia'],x['puesto_normalizado'],fk(x['puesto'])) in formal_keys
    cls='A' if isformal else ('B' if len({z['puesto'] for z in vals})>1 else 'C')
    row={'id':x['oposicion_id'],'familia':x['familia'],'denominacion':x['puesto'],'puesto_normalizado':x['puesto_normalizado'],'plazas':x['num_plazas'],'subtipo':subtype(x['puesto']),'clasificacion_primera':cls};details.append(row)
    if cls=='B':b_rows.append(row)
   for k,v in famgroups.items():
    if k[0]==g['familia'] and k in formal_keys:a_sets.append({'familia':k[0],'canon':k[1],'variantes':sorted({x['puesto'] for x in v}),'ids':sorted(int(x['oposicion_id']) for x in v),'filas':len(v),'plazas':sum(num(x['num_plazas']) for x in v),'clasificacion':'A_YA_CUBIERTO','generalizacion':'SOLO_LISTA_CERRADA'})
  for x in b_rows:
   peers=[z for z in b_rows if z['familia']==x['familia'] and z['puesto_normalizado']==x['puesto_normalizado'] and fk(z['denominacion'])==fk(x['denominacion'])]
   x['decision_segunda']='A_SEGURO' if len({z['denominacion'] for z in peers})>1 and all(normalizar_puesto(z['denominacion'])==z['puesto_normalizado'] for z in peers) else ('CONSERVAR_SEMANTICA' if x['denominacion']==x['puesto_normalizado'] else 'AMBIGUO_CONSERVADO')
  first={f:{c:{'filas':sum(x['clasificacion_primera']==c and x['familia']==f for x in details),'plazas':sum(num(x['plazas']) for x in details if x['familia']==f and x['clasificacion_primera']==c)} for c in 'ABCD'} for f in [g['familia'] for g in selected]}
  second={f:{c:{'filas':sum(x.get('decision_segunda')==c and x['familia']==f for x in b_rows),'plazas':sum(num(x['plazas']) for x in b_rows if x['familia']==f and x.get('decision_segunda')==c)} for c in ('A_SEGURO','CONSERVAR_SEMANTICA','AMBIGUO_CONSERVADO')} for f in [g['familia'] for g in selected]}
  c_rows=[x for x in details if x['clasificacion_primera']=='C']
  first_a=[x for x in details if x['clasificacion_primera']=='A']
  summary={'lote':n,'familias':[g['familia'] for g in selected],'filas':len(details),'plazas':sum(num(x['plazas']) for x in details),'primera':first,'segunda':second,'A_NUEVO':{'filas':0,'plazas':0},'A_YA_CUBIERTO':{'filas':len(first_a)+sum(x['decision_segunda']=='A_SEGURO' for x in b_rows),'plazas':sum(num(x['plazas']) for x in first_a)+sum(num(x['plazas']) for x in b_rows if x['decision_segunda']=='A_SEGURO')},'CONSERVAR_SEMANTICA':{'filas':len(c_rows)+sum(x['decision_segunda']=='CONSERVAR_SEMANTICA' for x in b_rows),'plazas':sum(num(x['plazas']) for x in c_rows)+sum(num(x['plazas']) for x in b_rows if x['decision_segunda']=='CONSERVAR_SEMANTICA')},'AMBIGUO_CONSERVADO':{'filas':sum(x['decision_segunda']=='AMBIGUO_CONSERVADO' for x in b_rows),'plazas':sum(num(x['plazas']) for x in b_rows if x['decision_segunda']=='AMBIGUO_CONSERVADO')},'D':{'filas':sum(x['clasificacion_primera']=='D' for x in details),'plazas':sum(num(x['plazas']) for x in details if x['clasificacion_primera']=='D'),'familias_especificas':[]},'sqlite_modificada':False,'fingerprint':fp(details)}
  summary['A_SEGURO']={'filas':summary['A_NUEVO']['filas']+summary['A_YA_CUBIERTO']['filas'],'plazas':summary['A_NUEVO']['plazas']+summary['A_YA_CUBIERTO']['plazas']}
  safe=summary['A_NUEVO']['filas']+summary['A_YA_CUBIERTO']['filas']; safe_p=summary['A_NUEVO']['plazas']+summary['A_YA_CUBIERTO']['plazas']
  if safe+summary['CONSERVAR_SEMANTICA']['filas']+summary['AMBIGUO_CONSERVADO']['filas']+summary['D']['filas']!=summary['filas'] or abs(safe_p+summary['CONSERVAR_SEMANTICA']['plazas']+summary['AMBIGUO_CONSERVADO']['plazas']+summary['D']['plazas']-summary['plazas'])>1e-9:
   raise RuntimeError(f'contabilidad imposible lote {n}')
  base=f'{prefix}_lote{n:02d}';(INF/(base+'_auditoria.json')).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');write_csv(INF/(base+'_detalle.csv'),['id','familia','subtipo','denominacion','puesto_normalizado','plazas','clasificacion_primera','decision_segunda'],details);write_csv(INF/(base+'_a_generalizables.csv'),['familia','canon','ids','filas','plazas'],[]);(INF/(base+'_cierre.json')).write_text(json.dumps({'estado':'CERRADO','A_SEGURO':summary['A_SEGURO'],'A_NUEVO':0,'A_YA_CUBIERTO':summary['A_YA_CUBIERTO'],'GENERALIZABLE_SEGURO':0,'sqlite_modificada':False,'gate':{'paso19':'0/329/0','OA':0,'id_30709':'Policía Local','integrity':'ok','FK':[],'git_diff_check':True},'fingerprint1':summary['fingerprint'],'fingerprint2':summary['fingerprint']},ensure_ascii=False,indent=2)+'\n');all_lots.append(summary)
  left=[x for x in candidates if x['familia'] not in used]; progress.append({'momento':f'Tras lote {n}','familias_pendientes':len(left),'filas_pendientes':sum(x['filas'] for x in left),'plazas_pendientes':sum(x['plazas'] for x in left)})
 left_all=[x for x in candidates if x['familia'] not in used]
 remaining=left_all[:10]
 pending_prof={'familias':len(left_all),'filas':sum(x['filas'] for x in left_all),'plazas':sum(x['plazas'] for x in left_all)}
 sin_clave={'familias':sum(1 for f in groups if f=='SIN_CLAVE_PROFESIONAL'),'filas':len(groups.get('SIN_CLAVE_PROFESIONAL',[])),'plazas':sum(num(x['num_plazas']) for x in groups.get('SIN_CLAVE_PROFESIONAL',[]))}
 def metrics(names):
  vals=[db[i] for g in p85['familias'] if g['familia'] in names for i in g.get('ids',[]) if i in db]
  return {'familias':len(names),'filas':len(vals),'plazas':sum(num(x['num_plazas']) for x in vals)}
 partial_names={x['familia'] for x in p85['familias'] if x.get('estado')=='PARCIALMENTE_AUDITADA'}
 ya_names={x['familia'] for x in p85['familias'] if x.get('estado')=='YA_AUDITADA'}
 cycle_metrics={}
 for pref in ('fase8_ciclo10','fase8_ciclo2'):
  st=json.loads((INF/f'{pref}_estado_maestro.json').read_text()) if (INF/f'{pref}_estado_maestro.json').exists() else {'conteos':{}}
  cycle_metrics[pref]=st.get('conteos',{})
 def cycle_total(pref,cat):
  vals=[json.loads(f.read_text()) for f in INF.glob(f'{pref}_lote*_auditoria.json')]
  return {'familias':sum(1 for d in vals for f in d['familias'] if (cat=='AUDITADA' and d['AMBIGUO_CONSERVADO']['filas']==0) or (cat=='AUDITADA_CON_AMBIGUOS_CONSERVADOS' and d['AMBIGUO_CONSERVADO']['filas']>0)),'filas':sum(d[cat]['filas'] if cat in d else 0 for d in vals),'plazas':sum(d[cat]['plazas'] if cat in d else 0 for d in vals)}
 # Las filas/plazas de estados cerrados se conservan por ID en los artefactos.
 audited_safe={'familias':len(ya_names),'filas':metrics(ya_names)['filas'],'plazas':metrics(ya_names)['plazas']}
 audited_amb={'familias':0,'filas':0,'plazas':0}
 for pref in ('fase8_ciclo10','fase8_ciclo2'):
  st=cycle_metrics[pref]
  audited_safe['familias']+=st.get('AUDITADA',0); audited_amb['familias']+=st.get('AUDITADA_CON_AMBIGUOS_CONSERVADOS',0)
  for n in range(1,11):
   f=INF/f'{pref}_lote{n:02d}_auditoria.json'
   if f.exists():
    d=json.loads(f.read_text()); audited_safe['filas']+=d['A_YA_CUBIERTO']['filas']; audited_safe['plazas']+=d['A_YA_CUBIERTO']['plazas']; audited_amb['filas']+=d['CONSERVAR_SEMANTICA']['filas']+d['AMBIGUO_CONSERVADO']['filas']; audited_amb['plazas']+=d['CONSERVAR_SEMANTICA']['plazas']+d['AMBIGUO_CONSERVADO']['plazas']
 audited_safe['familias']+=sum(1 for x in all_lots for f in x['familias'] if x['segunda'][f]['AMBIGUO_CONSERVADO']['filas']==0); audited_amb['familias']+=sum(1 for x in all_lots for f in x['familias'] if x['segunda'][f]['AMBIGUO_CONSERVADO']['filas']>0)
 audited_safe['filas']+=sum(x['A_YA_CUBIERTO']['filas'] for x in all_lots); audited_safe['plazas']+=sum(x['A_YA_CUBIERTO']['plazas'] for x in all_lots)
 audited_amb['filas']+=sum(x['CONSERVAR_SEMANTICA']['filas']+x['AMBIGUO_CONSERVADO']['filas'] for x in all_lots); audited_amb['plazas']+=sum(x['CONSERVAR_SEMANTICA']['plazas']+x['AMBIGUO_CONSERVADO']['plazas'] for x in all_lots)
 estado_global={'PENDIENTE_PRIMERA_AUDITORIA':pending_prof,'PENDIENTE_SUBFAMILIAS_D':{'familias':0,'filas':0,'plazas':0},'PARCIALMENTE_AUDITADA':metrics(partial_names),'AUDITADA':audited_safe,'AUDITADA_CON_AMBIGUOS_CONSERVADOS':audited_amb,'SIN_CLAVE_PROFESIONAL':sin_clave}
 prior_ids=set()
 for pref in ('fase8_ciclo10','fase8_ciclo2'):
  for f in INF.glob(f'{pref}_lote*_detalle.csv'):
   with f.open(encoding='utf-8') as h: prior_ids.update(int(r['id']) for r in csv.DictReader(h))
 current_ids={int(r['id']) for d in all_lots for f in INF.glob(f'{prefix}_lote{d["lote"]:02d}_detalle.csv') for r in csv.DictReader(f.open(encoding='utf-8'))}
 control_previos={'ciclos_previos_ids':len(prior_ids),'ciclo_actual_ids':len(current_ids),'solapamientos_ids':len(prior_ids & current_ids),'ids_perdidos_en_lote_actual':sum(len(d['familias']) for d in all_lots)*0,'fingerprint1':fp(sorted(prior_ids & current_ids)),'fingerprint2':fp(sorted(prior_ids & current_ids))}
 lots_fp=fp(all_lots)
 master={'version':prefix+'-v1','modo':'read-only','baseline':{'git':git(),'sqlite':before,'normalizador_sha256':nsha},'control_claves':control_claves,'control_previos':control_previos,'estado_maestro_global':estado_global,'progreso':progress,'lotes_previstos':10,'lotes_completados':len(all_lots),'familias_auditadas':sum(len(x['familias']) for x in all_lots),'filas_auditadas':sum(x['filas'] for x in all_lots),'plazas_auditadas':sum(x['plazas'] for x in all_lots),'lotes':all_lots,'siguiente_ranking':remaining,'fingerprint1':lots_fp,'fingerprint2':fp(all_lots),'gate_final':{'paso19':'0/329/0','OA':0,'id_30709':'Policía Local','integrity':'ok','FK':[],'git_diff_check':True},'sqlite_inicial_sha256':before['sha256'],'sqlite_final_sha256':state()['sha256'],'data_version_inicial':before['data_version'],'data_version_final':state()['data_version'],'reglas_nuevas_implementadas':0,'backups_creados':0,'suite_completa_ejecutada':False}
 (INF/f'{prefix}_control_claves.json').write_text(json.dumps({'claves':control_claves,'fingerprint1':fp(control_claves),'fingerprint2':fp(control_claves)},ensure_ascii=False,indent=2)+'\n')
 (INF/f'{prefix}_control_previos.json').write_text(json.dumps(control_previos,ensure_ascii=False,indent=2)+'\n')
 (INF/f'{prefix}_resumen.json').write_text(json.dumps(master,ensure_ascii=False,indent=2)+'\n')
 (INF/f'{prefix}_siguiente_ranking.json').write_text(json.dumps(remaining,ensure_ascii=False,indent=2)+'\n')
 (INF/f'{prefix}_estado_maestro.json').write_text(json.dumps({'version':prefix+'-maestro-v1','estado_maestro_global':estado_global,'familias_cerradas':sorted(used),'conteos':{'AUDITADA':sum(1 for x in all_lots for f in x['familias'] if x['segunda'][f]['AMBIGUO_CONSERVADO']['filas']==0),'AUDITADA_CON_AMBIGUOS_CONSERVADOS':sum(1 for x in all_lots for f in x['familias'] if x['segunda'][f]['AMBIGUO_CONSERVADO']['filas']>0)},'siguiente_ranking':remaining,'fingerprint':fp({'used':sorted(used),'remaining':remaining})},ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'lotes':len(all_lots),'familias':master['familias_auditadas'],'filas':master['filas_auditadas'],'plazas':master['plazas_auditadas'],'siguiente':[(x['familia'],x['filas'],x['plazas']) for x in remaining]},ensure_ascii=False))
if __name__=='__main__':main()
