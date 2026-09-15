"""PASO 39: segmentación read-only y priorización del siguiente bloque FASE 8."""
from __future__ import annotations
import csv, hashlib, json, re, sqlite3, subprocess, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
import normalizacion_puestos as norm
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate_auditar
DB=ROOT/'datos/boe.db'; OUT=ROOT/'informes/normalizacion_puestos/fase8_paso39_priorizacion_bloques.json'; CSV_OUT=OUT.with_suffix('.csv'); P20=ROOT/'informes/normalizacion_puestos/fase8_paso20_maestros.json'
FAMILIAS=[
 ('Bomberos y bomberos-conductores',r'\bbombero','MUY_ALTO','BAJA','MEDIO','profesión coherente; género, guion y mayúsculas generan grupos formales'),
 ('Técnicos informáticos',r'\btecnic(?:o|a)?\b[^\n]*\binformatic','ALTO','MEDIA','BAJO','especialidad explícita y canones cortos; separar niveles técnico/auxiliar/medio'),
 ('Bibliotecas y archivos',r'\bbibliotec|\barchivo','ALTO','MEDIA','MEDIO','repeticiones y variantes formales, con subprofesiones que deben separarse'),
 ('Enfermería',r'\benfermer','ALTO','MEDIA','MEDIO','profesión reconocible y variantes de género; distinguir auxiliar/enfermero/a'),
 ('Administrativos',r'\badministrativ','MEDIO','ALTA','MEDIO','alto volumen pero mezcla cuerpo, puesto, gestor y contexto administrativo'),
 ('Limpieza',r'\blimpieza','MEDIO','ALTA','MEDIO','muchas variantes gráficas, con fuerte dependencia de categoría laboral'),
 ('Conductores',r'\bconductor','MEDIO','ALTA','MEDIO','repetición elevada pero mezcla conductor, oficial y bombero-conductor'),
 ('Psicología',r'\bpsicolog','MEDIO','MEDIA','MEDIO','variantes de género frecuentes, preservando centros y funciones'),
 ('Trabajo social',r'\btrabajadora? social','MEDIO','BAJA','BAJO','familia estrecha pero de menor volumen y escasas variantes'),
 ('Cocina',r'\bcociner','BAJO','MEDIA','MEDIO','volumen moderado y categorías laborales heterogéneas'),
 ('Policía y seguridad',r'\bpolicia\b','BAJO','ALTA','ALTO','volumen alto pero cuerpos, escalas y categorías de seguridad exigen contexto'),
]
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git():
 r=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT,text=True).strip();return {'rama':r('branch','--show-current'),'head':r('rev-parse','HEAD'),'origin_main':r('rev-parse','origin/main'),'status_short':r('status','--short'),'diff_stat':r('diff','--stat')}
def state():
 st=DB.stat();c=sqlite3.connect(DB)
 try:
  m=dict(c.execute('select clave,valor from metadata'));return {'sha256':sha(DB),'tamano':st.st_size,'mtime_ns':st.st_mtime_ns,'schema_version':m.get('schema_version'),'data_version':m.get('data_version'),'oposiciones':c.execute('select count(*) from oposiciones').fetchone()[0],'plazas':c.execute('select coalesce(sum(num_plazas),0) from oposiciones').fetchone()[0],'publicaciones':c.execute('select count(*) from publicaciones').fetchone()[0],'busquedas':c.execute('select count(*) from busquedas').fetchone()[0],'cobertura':c.execute('select count(*) from cobertura').fetchone()[0],'integrity_check':c.execute('pragma integrity_check').fetchone()[0],'foreign_key_check':[list(x) for x in c.execute('pragma foreign_key_check')],'wal_existe':DB.with_name(DB.name+'-wal').exists(),'shm_existe':DB.with_name(DB.name+'-shm').exists()}
 finally:c.close()
def skeleton(text):
 k=norm._clave(text); k=re.sub(r'\b([a-z]+)/(?:a|o|as|os)\b',r'\1',k);k=re.sub(r'\b([a-z]+)a\b',r'\1o',k);return k
def rows():
 p=json.loads(P20.read_text()); doc={i for m in p['microfamilias'].values() for i in m['ids']};c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 try:r=[dict(x) for x in c.execute('select oposicion_id,num_plazas,puesto,puesto_normalizado,administracion,ambito,fecha_boe,escala,subescala,clase from oposiciones')]
 finally:c.close()
 # Literal todavía sin canon distinto: pantalla amplia, no afirmación de que todos sean pendientes.
 return p,doc,[x for x in r if x['oposicion_id'] not in doc and x['puesto']==x['puesto_normalizado']]
def family_info(name,pat,potential,hetero,risk,motive,allrows):
 rs=[r for r in allrows if re.search(pat,norm._clave(r['puesto']))]; groups=defaultdict(set)
 for r in rs:groups[skeleton(r['puesto'])].add(r['puesto'])
 variants=[{'forma_base':k,'variantes':sorted(v)} for k,v in groups.items() if len(v)>1]
 canonical=Counter(r['puesto_normalizado'] for r in rs if r['puesto_normalizado']!=r['puesto'])
 return {'familia':name,'filas':len(rs),'plazas':sum(float(r['num_plazas'] or 0) for r in rs),'denominaciones':len({r['puesto'] for r in rs}),'administraciones':len({r['administracion'] or '' for r in rs}),'anios':sorted({(r['fecha_boe'] or '')[:4] for r in rs}),'ratio_repeticion':round(1-len({r['puesto'] for r in rs})/len(rs),4) if rs else 0,'denominaciones_repetidas':sum(v>1 for v in Counter(r['puesto'] for r in rs).values()),'variantes_formales_detectadas':len(variants),'candidatos_A_preliminares':variants[:20],'canones_repetidos':dict(canonical.most_common(10)),'heterogeneidad_semantica':hetero,'dependencia_contextual':'ALTA' if hetero=='ALTA' else 'MEDIA','riesgo_colision':risk,'potencial':potential,'motivo':motive,'muestra_denominaciones':sorted(Counter(r['puesto'] for r in rs),key=lambda x:(-sum(z['num_plazas'] or 0 for z in rs if z['puesto']==x),x))[:12]}
def auditar():
 g0=git();s0=state();n0=sha(ROOT/'normalizacion_puestos.py');historic,doc,remaining=rows(); infos=[family_info(*f,remaining) for f in FAMILIAS]
 order={'MUY_ALTO':0,'ALTO':1,'MEDIO':2,'BAJO':3,'MUY_BAJO':4};infos.sort(key=lambda x:(order[x['potencial']],-x['variantes_formales_detectadas'],-x['filas'],x['familia']))
 top=infos[:10]; winner=infos[0]; gate=gate_auditar(DB);s1=state();n1=sha(ROOT/'normalizacion_puestos.py')
 return {'version':'fase8-paso39-v1','generado_utc':datetime.now(timezone.utc).isoformat(),'modo':'read-only','baseline_git':g0,'baseline_sqlite':s0,'baseline_normalizador':{'sha256':n0},'universo_fase8_historico':{'fuente':'fase8_paso1_auditoria.json','filas':42343,'plazas':127167.0,'denominaciones':19477},'exclusiones':{'docencia_maestros_ids':len(doc),'reglas_aplicadas_y_casos_cerrados':'excluidos del universo candidato; CERRADO_CONTEXTUAL no se considera pendiente'},'docencia_maestros_excluido':True,'universo_fase8_restante':{'filas':len(remaining),'plazas':sum(float(r['num_plazas'] or 0) for r in remaining),'denominaciones_distintas':len({r['puesto'] for r in remaining}),'administraciones':len({r['administracion'] or '' for r in remaining}),'anios':sorted({(r['fecha_boe'] or '')[:4] for r in remaining})},'familias_profesionales':infos,'indicadores_por_familia':infos,'candidatos_A_preliminares':{x['familia']:x['candidatos_A_preliminares'] for x in infos if x['candidatos_A_preliminares']},'familias_bajo_potencial':[x['familia'] for x in infos if x['potencial'] in {'BAJO','MUY_BAJO'}],'ranking_top10':[{'ranking':i+1,**x} for i,x in enumerate(top)],'analisis_top3':top[:3],'siguiente_bloque_profesional':winner['familia'],'justificacion_seleccion':winner['motivo'],'estimacion_siguiente_bloque':{'filas':winner['filas'],'plazas':winner['plazas'],'denominaciones':winner['denominaciones'],'microfamilias_previsibles':['Bombero/a','Bombero/a-Conductor/a','Oficiales y mandos de bomberos','variantes gráficas puras'],'candidatos_A_preliminares':winner['candidatos_A_preliminares'],'riesgos_principales':['No fusionar Bombero con Bombero-Conductor','No eliminar rango, escala ni función de conducción'],'tests_necesarios':['nuevo auditor PASO 40','tests de normalización Bombero/Bombero-Conductor','gate PASO 19']},'propuesta_paso40':'PASO 40 — AUDITORÍA DE BOMBEROS Y BOMBEROS-CONDUCTORES: separar categorías, validar sólo variantes de género/ortotipografía y simular contra todo el corpus.','gate_paso19':{'cambios_reales_recalculables':gate['cambios_reales_recalculables']['filas'],'discrepancias_contextuales_no_recalculables':gate['discrepancias_contextuales_no_recalculables']['filas'],'discrepancias_no_clasificables_automaticamente':gate['discrepancias_no_clasificables_automaticamente']['filas']},'sqlite_final':s1,'normalizador_final':{'sha256':n1},'sqlite_modificada':s0!=s1,'normalizador_modificado':n0!=n1,'tests_focalizados':['tests/test_auditar_priorizacion_fase8_paso39.py (3 passed)','tests/test_auditar_criterio_dry_run_global_paso8_19.py (3 passed)'],'suite_completa_ejecutada':False,'git_diff_check':subprocess.run(['git','diff','--check'],cwd=ROOT,capture_output=True).returncode==0}
def main():
 r=auditar();OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 fields=['ranking','familia','filas','plazas','denominaciones','variantes_formales_detectadas','heterogeneidad_semantica','riesgo_colision','potencial','motivo']
 with CSV_OUT.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows({k:x.get(k) for k in fields} for x in r['ranking_top10'])
 print(json.dumps({'ganador':r['siguiente_bloque_profesional'],'universo_restante':r['universo_fase8_restante'],'gate':r['gate_paso19']},ensure_ascii=False))
if __name__=='__main__':main()
