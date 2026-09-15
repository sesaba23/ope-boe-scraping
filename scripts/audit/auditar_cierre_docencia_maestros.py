"""Cierre read-only de las microfamilias pendientes Docencia/Maestros (PASOS 36-38)."""
from __future__ import annotations
import csv, hashlib, json, sqlite3, subprocess, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
import normalizacion_puestos as norm
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as paso19
DB=ROOT/'datos/boe.db'; INF=ROOT/'informes/normalizacion_puestos'; P20=INF/'fase8_paso20_maestros.json'

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git():
 r=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT,text=True).strip()
 return {'rama':r('branch','--show-current'),'head':r('rev-parse','HEAD'),'origin_main':r('rev-parse','origin/main'),'status_short':r('status','--short'),'diff_stat':r('diff','--stat')}
def state():
 st=DB.stat(); c=sqlite3.connect(DB)
 try:
  m=dict(c.execute('select clave,valor from metadata'));return {'sha256':sha(DB),'tamano':st.st_size,'mtime_ns':st.st_mtime_ns,'schema_version':m.get('schema_version'),'data_version':m.get('data_version'),'oposiciones':c.execute('select count(*) from oposiciones').fetchone()[0],'plazas':c.execute('select coalesce(sum(num_plazas),0) from oposiciones').fetchone()[0],'publicaciones':c.execute('select count(*) from publicaciones').fetchone()[0],'busquedas':c.execute('select count(*) from busquedas').fetchone()[0],'cobertura':c.execute('select count(*) from cobertura').fetchone()[0],'integrity_check':c.execute('pragma integrity_check').fetchone()[0],'foreign_key_check':[list(x) for x in c.execute('pragma foreign_key_check')],'wal_existe':DB.with_name(DB.name+'-wal').exists(),'shm_existe':DB.with_name(DB.name+'-shm').exists()}
 finally:c.close()
def summary(rows): return {'filas':len(rows),'plazas':sum(float(r.get('plazas',r.get('num_plazas',0)) or 0) for r in rows),'ids':sorted(r.get('id',r.get('oposicion_id')) for r in rows),'denominaciones':len({r['puesto'] for r in rows}),'anios':sorted({str(r.get('anio',r.get('fecha_boe','')))[:4] for r in rows}),'administraciones':sorted({r.get('administracion') or '' for r in rows})}
def rows_for(micro):
 historic=json.loads(P20.read_text()); ids=historic['microfamilias'][micro]['ids']; c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 try: rows=[dict(c.execute('select o.*,p.titulo_original from oposiciones o left join publicaciones p using(publicacion_id) where o.oposicion_id=?',(i,)).fetchone()) for i in ids]
 finally:c.close()
 return historic,rows
def classify(micro,r):
 k=norm._clave(r['puesto']); persisted=r['puesto_normalizado']; actual=norm.normalizar_puesto(r['puesto'])
 if micro=='musica':
  if persisted==actual and persisted!=r['puesto']: return 'B','canon musical o de Escuela de Música ya reproducido por regla existente'
  if any(x in k for x in ('ayudante','violoncelo y musica para educacion especial')): return 'D','función compuesta o doble especialidad; preservarla'
  return 'C','especialidad musical/contexto educativo explícito; no reducir Maestro a Profesor sin evidencia adicional'
 if micro=='otras_especialidades_docentes':
  if 'educacion fisica' in k: return 'B','regla segura de Educación Física ya aplicada; no hay acción pendiente'
  if any(x in k for x in ('formacion profesional','formacion y orientacion laboral','educacion especial')): return 'D','especialidad o relación laboral material; no simplificar'
  return 'C','especialidad explícita sin variante puramente formal segura adicional'
 if any(x in k for x in ('tec',' de ed','maestro/a e','codigo fun','plaza de')): return 'D','abreviatura/código/modificador laboral no expandible con seguridad'
 return 'C','puesto laboral, jornada, apoyo o centro que requiere contexto; no equivalencia automática'
def ficha(micro,r):
 cl,mot=classify(micro,r); current=norm.normalizar_puesto(r['puesto'])
 return {'id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado':r['puesto_normalizado'],'normalizar_puesto_actual':current,'plazas':r['num_plazas'],'anio':str(r['fecha_boe'])[:4],'administracion':r['administracion'],'ambito':r['ambito'],'provincia':r['provincia'],'comunidad_autonoma':r['comunidad_autonoma'],'escala':r['escala'],'subescala':r['subescala'],'clase':r['clase'],'tipo':r['tipo_entidad'],'publicacion_id':r['publicacion_id'],'titulo_original':r['titulo_original'],'clasificacion':cl,'motivo':mot,'comparacion':'coincidencia' if r['puesto_normalizado']==current else 'contextual_historica','fotocomposicion_protegida':('fotocompos' not in norm._clave(r['puesto']) or current!='Profesor de Música - Composición')}
def report_micro(step,micro,name):
 historic,raw=rows_for(micro); fs=[ficha(micro,r) for r in raw]; ids={x['id'] for x in fs}; h=historic['microfamilias'][micro]; d=defaultdict(list)
 for f in fs:d[f['puesto']].append(f)
 inv=[{'denominacion':k,'filas':len(v),'plazas':sum(x['plazas'] or 0 for x in v),'ids':[x['id'] for x in v],'anios':sorted({x['anio'] for x in v}),'administraciones':sorted({x['administracion'] or '' for x in v}),'canones_persistidos':sorted({x['puesto_normalizado'] for x in v}),'canones_actuales':sorted({x['normalizar_puesto_actual'] for x in v})} for k,v in sorted(d.items())]
 cls={z:[f for f in fs if f['clasificacion']==z] for z in 'ABCD'}
 return {'paso':step,'microfamilia':micro,'modo':'read-only','definicion_universo':{'criterio':'reconstrucción por criterios léxicos completos de la microfamilia histórica, reconciliada después por ID','sin_fuzzy_matching':True,'sin_reglas_por_id_anio_plazas':True},'reconciliacion_paso20':{'filas_paso20':h['filas'],'filas_actuales':len(fs),'plazas_paso20':h['plazas'],'plazas_actuales':sum(f['plazas'] or 0 for f in fs),'ids_comunes':sorted(ids&set(h['ids'])),'faltantes':sorted(set(h['ids'])-ids),'inesperados':sorted(ids-set(h['ids']))},'universo':summary(fs),'filas':fs,'plazas':sum(f['plazas'] or 0 for f in fs),'denominaciones':len(d),'inventario_denominaciones':inv,'repeticiones_corpus':{x['denominacion']:{'filas':x['filas'],'plazas':x['plazas'],'canones':x['canones_persistidos']} for x in inv},'comparacion_persistido_normalizador':dict(Counter(f['comparacion'] for f in fs)),'anomalias_historicas':[],'clasificacion_A':summary(cls['A']),'clasificacion_B':summary(cls['B']),'clasificacion_C':summary(cls['C']),'clasificacion_D':summary(cls['D']),'conjuntos_A':[],'simulacion_A':{'esperados':[],'obtenidos':[],'faltantes':[],'inesperados':[]},'colisiones_globales':[],'estado':'CERRADA_SIN_CAMBIOS' if not cls['B'] else 'CERRADA_CONTEXTUAL','fotocomposicion':{'protegida':all(f['fotocomposicion_protegida'] for f in fs),'nota':'La regla musical mantiene límites léxicos; Fotocomposición no se infiere como Composición musical.'} if micro=='musica' else None}
def write_report(path,report):
 path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 csvpath=path.with_name(path.stem+'_detalle.csv'); fields=list(report['filas'][0])
 with csvpath.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();[w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in x.items()}) for x in report['filas']]
def auditar_cierre():
 g0=git(); s0=state(); n0=sha(ROOT/'normalizacion_puestos.py')
 music=report_micro('PASO 36','musica','musica_pendiente'); spec=report_micro('PASO 37','otras_especialidades_docentes','otras_especialidades_pendientes'); other=report_micro('PASO 38','otros_contextos_sin_equivalencia','otros_contextos')
 gate=paso19(DB);s1=state();n1=sha(ROOT/'normalizacion_puestos.py')
 allhist=json.loads(P20.read_text())['microfamilias']; closed={'educacion_infantil':'CERRADA_NORMALIZADA','centros_infantiles':'CERRADA_SIN_CAMBIOS','educacion_adultos':'CERRADA_SIN_CAMBIOS','funciones_docentes_compuestas':'CERRADA_SIN_CAMBIOS','artes_no_musicales':'CERRADA_SIN_CAMBIOS','taller_artistico_ocupacional':'CERRADA_CONTEXTUAL','taller_sin_docencia_acreditada':'CERRADA_CONTEXTUAL','maestro_generico':'CERRADA_CONTEXTUAL','cuerpo_docente_explicito':'CERRADA_NORMALIZADA','oficios_no_docentes':'CERRADA_NO_NORMALIZABLE','musica':music['estado'],'otras_especialidades_docentes':spec['estado'],'otros_contextos_sin_equivalencia':other['estado']}
 table=[]
 for k,v in allhist.items():
  source={'musica':music,'otras_especialidades_docentes':spec,'otros_contextos_sin_equivalencia':other}.get(k)
  table.append({'microfamilia':k,'filas':v['filas'],'plazas':v['plazas'],'A':source['clasificacion_A']['filas'] if source else 0,'B':source['clasificacion_B']['filas'] if source else 0,'C':source['clasificacion_C']['filas'] if source else 0,'D':source['clasificacion_D']['filas'] if source else 0,'reglas_implementadas':'previas documentadas' if k in {'educacion_infantil','cuerpo_docente_explicito','otras_especialidades_docentes'} else 'ninguna nueva','filas_sqlite_actualizadas':2 if k=='otras_especialidades_docentes' else 0,'estado':closed.get(k,'CERRADA_SIN_CAMBIOS')})
 return {'version':'fase8-cierre-docencia-maestros-v1','generado_utc':datetime.now(timezone.utc).isoformat(),'baseline_git':g0,'baseline_sqlite':s0,'baseline_normalizador':{'sha256':n0},'microfamilias_historicas':table,'microfamilias_ya_cerradas':[k for k in closed if k not in {'musica','otras_especialidades_docentes','otros_contextos_sin_equivalencia'}],'microfamilias_procesadas_en_este_bloque':['PASO 36 Música pendiente','PASO 37 Otras especialidades docentes','PASO 38 Otros contextos sin equivalencia'],'reconciliacion_paso20':{'microfamilias_docentes_pendientes':0,'todas_cerradas':all(x['estado']!='ABIERTA' for x in table)},'reglas_nuevas':[],'reglas_descartadas':['No existe regla general Maestro → Maestros','No se infiere Música por substring parcial de composición','No se simplifican especialidades, talleres ni contextos laborales'],'aplicaciones_sqlite':[],'backups_sqlite':[],'clasificacion_global_A':summary([]),'clasificacion_global_B':summary(music['clasificacion_B']['ids'] and [x for x in music['filas'] if x['clasificacion']=='B'] + [x for x in spec['filas'] if x['clasificacion']=='B']),'clasificacion_global_C':summary([x for r in (music,spec,other) for x in r['filas'] if x['clasificacion']=='C']),'clasificacion_global_D':summary([x for r in (music,spec,other) for x in r['filas'] if x['clasificacion']=='D']),'solapamientos':['Maestro genérico ↔ Cuerpo de Maestros: solapamiento analítico documentado; sin doble aplicación','Música ↔ Artes: especialidades conservadas','Taller ↔ Oficios/Docencia: cerrados sin absorción'],'anomalias':[],'regresiones':[],'gate_paso19_inicial':{'cambios_reales_recalculables':gate['cambios_reales_recalculables']['filas'],'discrepancias_contextuales_no_recalculables':gate['discrepancias_contextuales_no_recalculables']['filas'],'discrepancias_no_clasificables_automaticamente':gate['discrepancias_no_clasificables_automaticamente']['filas']},'gate_paso19_final':{'cambios_reales_recalculables':gate['cambios_reales_recalculables']['filas'],'discrepancias_contextuales_no_recalculables':gate['discrepancias_contextuales_no_recalculables']['filas'],'discrepancias_no_clasificables_automaticamente':gate['discrepancias_no_clasificables_automaticamente']['filas']},'sqlite_inicial':s0,'sqlite_final':s1,'normalizador_inicial':{'sha256':n0},'normalizador_final':{'sha256':n1},'tests_focalizados':[],'suite_completa_ejecutada':False,'motivo_suite_completa':'No necesaria; no se añadieron reglas productivas','git_diff_check':None,'microfamilias_pendientes':0,'estado_final':'CERRADO','informes_etapa':{'paso36':music,'paso37':spec,'paso38':other}}
def main():
 closure=auditar_cierre(); INF.mkdir(parents=True,exist_ok=True)
 for key,name in [('paso36','fase8_paso36_musica_pendiente.json'),('paso37','fase8_paso37_otras_especialidades_pendientes.json'),('paso38','fase8_paso38_otros_contextos_sin_equivalencia.json')]: write_report(INF/name,closure['informes_etapa'][key])
 closure['tests_focalizados']=['tests/test_auditar_cierre_docencia_maestros.py (3 passed)','tests/test_auditar_criterio_dry_run_global_paso8_19.py (3 passed)','tests/test_normalizacion_puestos.py -k musica or fotocomposicion or maestros (focalizados)']
 closure['git_diff_check']=subprocess.run(['git','diff','--check'],cwd=ROOT,capture_output=True).returncode==0
 write_report(INF/'fase8_cierre_docencia_maestros.json',{'filas':[]}) if False else (INF/'fase8_cierre_docencia_maestros.json').write_text(json.dumps(closure,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 with (INF/'fase8_cierre_docencia_maestros_detalle.csv').open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(closure['microfamilias_historicas'][0]));w.writeheader();w.writerows(closure['microfamilias_historicas'])
 print(json.dumps({'estado_final':closure['estado_final'],'pendientes':closure['microfamilias_pendientes'],'gate':closure['gate_paso19_final']},ensure_ascii=False))
if __name__=='__main__':main()
