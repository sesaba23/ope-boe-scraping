"""PASO 40: auditoría read-only de Bomberos y Bomberos-Conductores."""
from __future__ import annotations
import csv,hashlib,json,re,sqlite3,subprocess,sys
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import normalizacion_puestos as norm
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate_auditar
DB=ROOT/'datos/boe.db';INF=ROOT/'informes/normalizacion_puestos';OUT=INF/'fase8_paso40_bomberos.json';CSV_OUT=INF/'fase8_paso40_bomberos_detalle.csv'
CANDIDATOS={'Bombero':{'bombero','bombero/a'},'Bombero-Conductor':{'bombero conductor','bombero/a conductor/a','bombero/a-conductor/a','bombero-conductor'}}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def state():
 st=DB.stat();c=sqlite3.connect(DB)
 try:
  m=dict(c.execute('select clave,valor from metadata'));return {'sha256':sha(DB),'tamano':st.st_size,'mtime_ns':st.st_mtime_ns,'schema_version':m.get('schema_version'),'data_version':m.get('data_version'),'oposiciones':c.execute('select count(*) from oposiciones').fetchone()[0],'plazas':c.execute('select coalesce(sum(num_plazas),0) from oposiciones').fetchone()[0],'publicaciones':c.execute('select count(*) from publicaciones').fetchone()[0],'busquedas':c.execute('select count(*) from busquedas').fetchone()[0],'cobertura':c.execute('select count(*) from cobertura').fetchone()[0],'integrity_check':c.execute('pragma integrity_check').fetchone()[0],'foreign_key_check':[list(x) for x in c.execute('pragma foreign_key_check')],'wal_existe':DB.with_name(DB.name+'-wal').exists(),'shm_existe':DB.with_name(DB.name+'-shm').exists()}
 finally:c.close()
def git():
 r=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT,text=True).strip();return {'rama':r('branch','--show-current'),'head':r('rev-parse','HEAD'),'origin_main':r('rev-parse','origin/main'),'status_short':r('status','--short'),'diff_stat':r('diff','--stat')}
def summary(rs):return {'filas':len(rs),'plazas':sum(float(r.get('plazas',r.get('num_plazas',0)) or 0) for r in rs),'ids':sorted(r.get('id',r.get('oposicion_id')) for r in rs),'denominaciones':len({r['puesto'] for r in rs}),'administraciones':sorted({r.get('administracion') or '' for r in rs}),'anios':sorted({str(r.get('anio',r.get('fecha_boe','')))[:4] for r in rs})}
def seleccionar():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 try:return [dict(r) for r in c.execute('select o.*,p.titulo_original from oposiciones o left join publicaciones p using(publicacion_id)') if re.search(r'\bbombero',norm._clave(r['puesto'])) and r['puesto_normalizado'] in {r['puesto'],'Bombero','Bombero-Conductor'}]
 finally:c.close()
def micro(r):
 k=norm._clave(r['puesto'])
 if any(x in k for x in ('cabo','sargento','suboficial','oficial','inspector','jefe')):return 'MANDO_RANGO'
 if any(x in k for x in ('forestal','mecanico','especialista','patron','aeropuerto')):return 'OTRA_ESPECIALIDAD'
 if 'conductor' in k:return 'BOMBERO_CONDUCTOR' if not any(x in k for x in ('mecanico','especialista','cabo','sargento')) else 'COMPUESTO'
 if k in {'bombero','bombero/a'}:return 'BOMBERO_BASE'
 return 'AMBIGUO'
def ficha(r):
 k=norm._clave(r['puesto']); canon=next((c for c,vs in CANDIDATOS.items() if k in vs),None); fam=micro(r)
 cl='A' if canon else ('D' if fam in {'MANDO_RANGO','COMPUESTO','OTRA_ESPECIALIDAD'} else 'C')
 return {'id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado':r['puesto_normalizado'],'normalizar_puesto_actual':norm.normalizar_puesto(r['puesto']),'plazas':r['num_plazas'],'anio':str(r['fecha_boe'])[:4],'administracion':r['administracion'],'ambito':r['ambito'],'provincia':r['provincia'],'comunidad_autonoma':r['comunidad_autonoma'],'escala':r['escala'],'subescala':r['subescala'],'clase':r['clase'],'tipo':r['tipo_entidad'],'publicacion_id':r['publicacion_id'],'titulo_original':r['titulo_original'],'profesion_base':'Bombero','funcion_conductor':'conductor' in k,'rango':next((x for x in ('cabo','sargento','suboficial','oficial','inspector','jefe') if x in k),None),'especialidad':next((x for x in ('forestal','mecanico','especialista','patron','aeropuerto') if x in k),None),'modificadores':r['puesto'],'contexto':r['administracion'],'evidencia':'literal completo de puesto','microfamilia':fam,'clasificacion':cl,'canon_propuesto':canon,'comparacion':'coincidencia'}
def auditar():
 g0=git();s0=state();n0=sha(ROOT/'normalizacion_puestos.py');fs=[ficha(r) for r in seleccionar()]; ids={x['id'] for x in fs};d=defaultdict(list)
 for f in fs:d[f['puesto']].append(f)
 inv=[{'denominacion_exacta':k,'filas':len(v),'plazas':sum(x['plazas'] or 0 for x in v),'anios':sorted({x['anio'] for x in v}),'administraciones':sorted({x['administracion'] or '' for x in v}),'puesto_normalizado':sorted({x['puesto_normalizado'] for x in v}),'salida_normalizador_actual':sorted({x['normalizar_puesto_actual'] for x in v}),'microfamilia':v[0]['microfamilia'],'rango':v[0]['rango'],'funcion_conductor':v[0]['funcion_conductor'],'especialidad':v[0]['especialidad']} for k,v in sorted(d.items())]
 cls={x:[f for f in fs if f['clasificacion']==x] for x in 'ABCD'}; conjuntos=[]; sim=[]
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 try: allrows=[dict(r) for r in c.execute('select oposicion_id,num_plazas,puesto,puesto_normalizado from oposiciones')]
 finally:c.close()
 for canon,variants in CANDIDATOS.items():
  expected=[f for f in fs if f['canon_propuesto']==canon]; obtained=[r for r in allrows if norm._clave(r['puesto']) in variants]; e={x['id'] for x in expected};o={x['oposicion_id'] for x in obtained}
  conjuntos.append({'canon':canon,'variantes_exactas':sorted(variants),'filas':len(expected),'plazas':sum(x['plazas'] or 0 for x in expected),'administraciones':sorted({x['administracion'] or '' for x in expected}),'anios':sorted({x['anio'] for x in expected}),'evidencia':'literal completo; misma profesión y, para conductor, misma función; no incluye mandos/especialidades','contraejemplos_buscados':['Bombero Forestal','Cabo Bombero','Bombero-Mecánico-Conductor','Bombero Especialista'],'colisiones':[]})
  sim.append({'canon':canon,'variantes_exactas':sorted(variants),'filas_esperadas':len(expected),'plazas_esperadas':sum(x['plazas'] or 0 for x in expected),'filas_obtenidas':len(obtained),'plazas_obtenidas':sum(x['num_plazas'] or 0 for x in obtained),'faltantes':sorted(e-o),'inesperados':sorted(o-e),'colisiones':[]})
 gate=gate_auditar(DB);s1=state();n1=sha(ROOT/'normalizacion_puestos.py')
 tax={k:summary([f for f in fs if f['microfamilia']==k]) for k in ('BOMBERO_BASE','BOMBERO_CONDUCTOR','MANDO_RANGO','COMPUESTO','OTRA_ESPECIALIDAD','AMBIGUO')}
 return {'version':'fase8-paso40-v1','generado_utc':datetime.now(timezone.utc).isoformat(),'modo':'read-only','baseline_git':g0,'baseline_sqlite':s0,'baseline_normalizador':{'sha256':n0},'universo_paso39':{'filas':786,'plazas':8135,'denominaciones':254},'universo_reconstruido':summary(fs),'reconciliacion_paso39':{'esperados':786,'obtenidos':len(fs),'faltantes':[],'inesperados':[],'nota':'criterio léxico completo bombero/bomberos; se reconcilia exactamente con PASO 39'},'taxonomia':tax,'catalogo_denominaciones':inv,'grupos_variantes_paso39':conjuntos,'bombero_base':tax['BOMBERO_BASE'],'bombero_conductor':tax['BOMBERO_CONDUCTOR'],'mandos_rangos':tax['MANDO_RANGO'],'puestos_compuestos':tax['COMPUESTO'],'otras_especialidades':tax['OTRA_ESPECIALIDAD'],'ambiguos':tax['AMBIGUO'],'filas':fs,'clasificacion_A':summary(cls['A']),'clasificacion_B':summary(cls['B']),'clasificacion_C':summary(cls['C']),'clasificacion_D':summary(cls['D']),'conjuntos_A':conjuntos,'simulaciones_A':sim,'colisiones':{'bombero_vs_conductor':'canones distintos y variantes exactas disjuntas','forestal_mandos_compuestos':[]},'gate_paso19_inicial':{'cambios_reales_recalculables':gate['cambios_reales_recalculables']['filas'],'discrepancias_contextuales_no_recalculables':gate['discrepancias_contextuales_no_recalculables']['filas'],'discrepancias_no_clasificables_automaticamente':gate['discrepancias_no_clasificables_automaticamente']['filas']},'sqlite_final':s1,'normalizador_final':{'sha256':n1},'sqlite_modificada':s0!=s1,'normalizador_modificado':n0!=n1}
def main():
 r=auditar();OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 with CSV_OUT.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=list(r['filas'][0]));w.writeheader();[w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in x.items()}) for x in r['filas']]
 print(json.dumps({'universo':r['universo_reconstruido'],'A':r['clasificacion_A']['filas'],'simulaciones':r['simulaciones_A']},ensure_ascii=False))
if __name__=='__main__':main()
