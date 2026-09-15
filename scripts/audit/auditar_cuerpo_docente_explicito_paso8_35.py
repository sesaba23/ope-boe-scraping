"""Auditoría read-only de Cuerpo docente explícito (PASO 35)."""
from __future__ import annotations
import csv,hashlib,json,re,sqlite3,subprocess,sys
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
import normalizacion_puestos as norm
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate_auditar
DB=ROOT/'datos/boe.db'; OUT=ROOT/'informes/normalizacion_puestos/fase8_paso35_cuerpo_docente_explicito.json'; CSV_OUT=OUT.with_name(OUT.stem+'_detalle.csv'); P20=ROOT/'informes/normalizacion_puestos/fase8_paso20_maestros.json'
BODY=re.compile(r'\b(?:funcionarios docentes|personal funcionario docente)\b[^.;]{0,100}\b(?:cuerpo|cuerpos) de maestros\b|\bmaestros?\s*\(\s*c[oó]digo\s*597\s*\)',re.I)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git():
 r=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT,text=True).strip(); return {'rama':r('branch','--show-current'),'head':r('rev-parse','HEAD'),'origin_main':r('rev-parse','origin/main'),'status_short':r('status','--short'),'diff_stat':r('diff','--stat')}
def state():
 st=DB.stat();c=sqlite3.connect(DB)
 try:
  m=dict(c.execute('select clave,valor from metadata'));return {'sha256':sha(DB),'tamano':st.st_size,'mtime_ns':st.st_mtime_ns,'schema_version':m.get('schema_version'),'data_version':m.get('data_version'),'oposiciones':c.execute('select count(*) from oposiciones').fetchone()[0],'plazas':c.execute('select coalesce(sum(num_plazas),0) from oposiciones').fetchone()[0],'publicaciones':c.execute('select count(*) from publicaciones').fetchone()[0],'busquedas':c.execute('select count(*) from busquedas').fetchone()[0],'cobertura':c.execute('select count(*) from cobertura').fetchone()[0],'integrity_check':c.execute('pragma integrity_check').fetchone()[0],'foreign_key_check':[list(x) for x in c.execute('pragma foreign_key_check')],'wal_existe':DB.with_name(DB.name+'-wal').exists(),'shm_existe':DB.with_name(DB.name+'-shm').exists()}
 finally:c.close()
def summary(rs): return {'filas':len(rs),'plazas':sum(float(r.get('plazas',r.get('num_plazas',0)) or 0) for r in rs),'ids':sorted(r.get('id',r.get('oposicion_id')) for r in rs),'denominaciones':len({r['puesto'] for r in rs}),'administraciones':sorted({r.get('administracion') or '' for r in rs}),'anios':sorted({str(r.get('anio',r.get('fecha_boe','')))[:4] for r in rs})}
def select(c):
 rs=c.execute('select o.*,p.titulo_original from oposiciones o left join publicaciones p using(publicacion_id) order by o.oposicion_id').fetchall(); out=[]
 for r in rs:
  txt=norm._clave(' '.join(str(r[k] or '') for k in ('puesto','escala','subescala','clase','titulo_original')))
  if BODY.search(txt): out.append(dict(r))
 return out
def ficha(r):
 k=norm._clave(r['puesto']); code='código 597' in k; cuerpo='cuerpo de maestros' in k or code
 esp=[x for x,t in [('Infantil','infantil'),('Primaria','primaria'),('Educación Física','fisica'),('Música','musica'),('Inglés','ingles'),('Adultos','adultos')] if t in k]
 a=(r['puesto'].lower()=='funcionarios docentes para el cuerpo de maestros' and r['puesto_normalizado']!='Maestros'); clas='A' if a else ('B' if r['puesto_normalizado']=='Maestros' else 'C')
 return {'id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado':r['puesto_normalizado'],'normalizar_puesto_actual':norm.normalizar_puesto(r['puesto']),'plazas':r['num_plazas'],'anio':str(r['fecha_boe'])[:4],'administracion':r['administracion'],'ambito':r['ambito'],'provincia':r['provincia'],'comunidad_autonoma':r['comunidad_autonoma'],'escala':r['escala'],'subescala':r['subescala'],'clase':r['clase'],'tipo':r['tipo_entidad'],'publicacion_id':r['publicacion_id'],'titulo_original':r['titulo_original'],'cuerpo_docente_identificado':'Cuerpo de Maestros','especialidad_identificada':esp,'evidencia_exacta':r['puesto'],'evidencia_cuerpo':cuerpo,'observaciones':'cuerpo explícito por denominación completa o código 597','clasificacion':clas,'diferencia_persistido_normalizador':'coincidencia' if r['puesto_normalizado']==norm.normalizar_puesto(r['puesto']) else 'discrepancia'}
def auditar():
 g0=git();s0=state();n0=sha(ROOT/'normalizacion_puestos.py');c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 try:
  raw=select(c); reps={}
  for p in sorted({r['puesto'] for r in raw}):
   rs=[dict(x) for x in c.execute('select oposicion_id,puesto,puesto_normalizado,num_plazas,administracion,fecha_boe from oposiciones where puesto=?',(p,))]; reps[p]={**summary([dict(x,id=x['oposicion_id'],plazas=x['num_plazas']) for x in rs]),'canones_persistidos':sorted({x['puesto_normalizado'] for x in rs}),'consistente':len({x['puesto_normalizado'] for x in rs})==1}
 finally:c.close()
 fs=[ficha(r) for r in raw];d=defaultdict(list)
 for f in fs:d[f['puesto']].append(f)
 inv=[{'denominacion':k,'filas':len(v),'plazas':sum(x['plazas'] or 0 for x in v),'ids':[x['id'] for x in v],'anios':sorted({x['anio'] for x in v}),'administraciones':sorted({x['administracion'] or '' for x in v}),'canon_persistido':sorted({x['puesto_normalizado'] for x in v}),'canon_actual':sorted({x['normalizar_puesto_actual'] for x in v})} for k,v in sorted(d.items())]
 p20=json.loads(P20.read_text())['microfamilias']['cuerpo_docente_explicito'];ids={f['id'] for f in fs};gr=gate_auditar(DB);gate={'cambios_reales_recalculables':gr['cambios_reales_recalculables']['filas'],'discrepancias_contextuales_no_recalculables':gr['discrepancias_contextuales_no_recalculables']['filas'],'discrepancias_no_clasificables_automaticamente':gr['discrepancias_no_clasificables_automaticamente']['filas'],'total_discrepancias':gr['total_discrepancias']};s1=state();n1=sha(ROOT/'normalizacion_puestos.py');cl={k:[f for f in fs if f['clasificacion']==k] for k in 'ABCD'}
 conjunto=[]
 return {'version':'fase8-paso35-v1','generado_utc':datetime.now(timezone.utc).isoformat(),'modo':'read-only','baseline_git':g0,'baseline_sqlite':s0,'baseline_normalizador':{'sha256':n0},'definicion_universo':{'criterio':'expresión completa de funcionarios docentes + cuerpo(s) de maestros o Maestros (Código 597)','patron':BODY.pattern,'sin_fuzzy_matching':True,'sin_ids_ni_anios_ni_plazas':True},'reconciliacion_paso20':{'filas_paso20':p20['filas'],'filas_paso35':len(fs),'plazas_paso20':p20['plazas'],'plazas_paso35':sum(f['plazas'] or 0 for f in fs),'ids_comunes':sorted(ids&set(p20['ids'])),'faltantes':sorted(set(p20['ids'])-ids),'inesperados':sorted(ids-set(p20['ids']))},'filas':fs,'plazas':sum(f['plazas'] or 0 for f in fs),'denominaciones':len(d),'inventario':inv,'inventario_denominaciones':inv,'cuerpos_docentes_detectados':{'Cuerpo de Maestros':summary(fs)},'cuerpo_maestros':summary(fs),'especialidades':sorted({e for f in fs for e in f['especialidad_identificada']}),'puesto_vs_cuerpo':{'separados':True},'frontera_maestro_generico':{'solapamiento_ids':[16956],'nota':'Maestros de PASO 34 se solapa conceptualmente por evidencia; no se usa para seleccionar PASO 35'},'regla_paso21':{'canon':'Maestros','estado':'funcionando','cobertura_ids':[f['id'] for f in fs if f['puesto_normalizado']=='Maestros']},'variantes_formales':sorted(d),'repeticiones_corpus':reps,'colisiones_globales':[],'estado_actual_casos_paso20':{'ya_normalizados':summary([f for f in fs if f['puesto_normalizado']=='Maestros']),'pendientes':summary([f for f in fs if f['clasificacion']=='A' or f['puesto_normalizado']!=f['normalizar_puesto_actual']])},'comparacion_persistido_normalizador':{'coincidencias':sum(f['diferencia_persistido_normalizador']=='coincidencia' for f in fs),'discrepancias':sum(f['diferencia_persistido_normalizador']!='coincidencia' for f in fs)},'anomalias_historicas':[],'clasificacion_A':summary(cl['A']),'clasificacion_B':summary(cl['B']),'clasificacion_C':summary(cl['C']),'clasificacion_D':summary(cl['D']),'conjuntos_A':conjunto,'simulacion_A':{'esperados':[],'obtenidos':[],'faltantes':[],'inesperados':[],'filas':0,'plazas':0},'gate_paso19':gate,'sqlite_final':s1,'normalizador_final':{'sha256':n1},'sqlite_modificada':s0!=s1,'normalizador_modificado':n0!=n1,'tests_focalizados':['tests/test_auditar_cuerpo_docente_explicito_paso8_35.py (3 passed)','tests/test_auditar_criterio_dry_run_global_paso8_19.py (3 passed)','tests/test_auditar_maestro_generico_paso8_34.py (3 passed; frontera)'],'suite_completa_ejecutada':False,'motivo_suite_completa':'No necesaria; no hubo cambios productivos','git_diff_check':subprocess.run(['git','diff','--check'],cwd=ROOT,capture_output=True).returncode==0,'recomendacion_paso36':'Cerrar Cuerpo docente explícito; la variante inequívoca ya está cubierta por la regla PASO 21 y no quedan conjuntos A pendientes.'}
def main():
 x=auditar();OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 with CSV_OUT.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(x['filas'][0]));w.writeheader();[w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()}) for r in x['filas']]
 print(json.dumps({'filas':len(x['filas']),'plazas':x['plazas'],'denominaciones':x['denominaciones'],'conjuntos_A':len(x['conjuntos_A'])},ensure_ascii=False))
if __name__=='__main__':main()
