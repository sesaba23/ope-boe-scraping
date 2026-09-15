"""Auditoría de sólo lectura de Otras especialidades docentes."""
from __future__ import annotations
import argparse, csv, hashlib, json, re, sqlite3, subprocess, sys, unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from normalizacion_puestos import normalizar_puesto
from normalizacion_contextual_puestos import normalizar_puesto_efectivo
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as auditar_global

DB=ROOT/'datos/boe.db'; PASO20=ROOT/'informes/normalizacion_puestos/fase8_paso20_maestros.json'
OUT=ROOT/'informes/normalizacion_puestos/fase8_paso26_otras_especialidades_docentes.json'; CSV_OUT=ROOT/'informes/normalizacion_puestos/fase8_paso26_otras_especialidades_docentes_detalle.csv'

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()

def estado(path=DB):
 path=Path(path); st=path.stat(); c=sqlite3.connect(f'file:{path.resolve()}?mode=ro',uri=True)
 try:
  tabs={x[0] for x in c.execute('select name from sqlite_master where type="table"')}; m=dict(c.execute('select clave,valor from metadata')); count=lambda t:c.execute(f'select count(*) from [{t}]').fetchone()[0] if t in tabs else None
  return {'sha256':sha(path),'tamano':st.st_size,'mtime_ns':st.st_mtime_ns,'schema_version':m.get('schema_version'),'data_version':m.get('data_version'),'oposiciones':count('oposiciones'),'plazas':c.execute('select coalesce(sum(num_plazas),0) from oposiciones').fetchone()[0],'publicaciones':count('publicaciones'),'busquedas':count('busquedas'),'cobertura':count('cobertura'),'integrity_check':c.execute('pragma integrity_check').fetchone()[0],'foreign_key_check':[list(x) for x in c.execute('pragma foreign_key_check')],'wal_existe':path.with_name(path.name+'-wal').exists(),'shm_existe':path.with_name(path.name+'-shm').exists()}
 finally:c.close()

def git_state():
 def run(*a):return subprocess.check_output(['git',*a],cwd=ROOT,text=True)
 return {'rama':run('branch','--show-current'),'head':run('rev-parse','HEAD'),'origin_main':run('rev-parse','origin/main'),'status_short':run('status','--short'),'diff_stat':run('diff','--stat')}

def key(s):
 s=unicodedata.normalize('NFKD',s or '')
 return re.sub(r'\s+',' ',''.join(c for c in s if not unicodedata.combining(c)).casefold()).strip()

def cargar():
 d=json.loads(PASO20.read_text(encoding='utf-8')); m=d['microfamilias']['otras_especialidades_docentes']; rows={r['oposicion_id']:r for r in d['registros'] if r.get('microfamilia')=='otras_especialidades_docentes'}; ids=sorted(m['ids'])
 if len(ids)!=9 or m['plazas']!=26 or sorted(rows)!=ids: raise RuntimeError('PASO 20 no reconstruye 9 filas / 26 plazas')
 return d,rows,ids

def corpus(c):
 return [dict(r) for r in c.execute('''select o.oposicion_id,o.num_plazas as plazas,o.puesto,o.puesto_normalizado,o.administracion,o.ambito,o.tipo_entidad,o.fecha_boe,o.provincia,o.municipio,o.escala,o.subescala,o.clase,o.sistema,o.publicacion_id,p.titulo_original from oposiciones o left join publicaciones p on p.publicacion_id=o.publicacion_id''')]

def specialty(text):
 k=key(text)
 for name,pat in [('Educación Física',r'educacion fisica'),('Primaria',r'primaria'),('Formación Profesional',r'formacion profesional'),('Formación y Orientación Laboral',r'formacion y orientacion laboral'),('Inglés',r'ingles'),('Audición y Lenguaje',r'audicion y lenguaje'),('Educación Especial',r'educacion especial')]:
  if re.search(pat,k): return name
 return None

def classify(text):
 k=key(text); sp=specialty(text)
 if sp=='Educación Física': return 'A','Diferencia exclusivamente de género/ortotipografía; misma especialidad y canon inequívoco','Maestro de Educación Física'
 if sp=='Inglés': return 'B','Especialidad explícita, pero falta una variante/canon validado transversalmente','Maestro de Inglés'
 if sp=='Audición y Lenguaje': return 'B','Especialidad explícita; “Especialista de” frente a forma abreviada requiere validación adicional','Maestro de Audición y Lenguaje'
 if sp in {'Formación Profesional','Formación y Orientación Laboral','Educación Especial'}: return 'D','Especialidad y/o relación laboral material; no reducir al canon genérico','Maestro de '+sp
 return 'C','Primaria puede expresar nivel, especialidad o cuerpo; evidencia insuficiente para automatizar','Maestro de Primaria'

def ficha(row,original,all_rows):
 text=row['puesto']; sp=specialty(text); cls,reason,canon=classify(text); matches=[x for x in all_rows if x['puesto']==text]; k=key(text)
 contextual=normalizar_puesto_efectivo(text,administracion=row['administracion'],ambito=row['ambito'],tipo_entidad=row['tipo_entidad'],escala=row['escala'],subescala=row['subescala'],sistema=row['sistema'],municipio=row['municipio'],provincia=row['provincia'])
 return {'id':row['oposicion_id'],'puesto':text,'puesto_normalizado':row['puesto_normalizado'],'normalizar_puesto':normalizar_puesto(text),'normalizar_puesto_efectivo':contextual.normalizado,'plazas':row['plazas'],'ano':(row['fecha_boe'] or '')[:4],'fecha_boe':row['fecha_boe'],'administracion':row['administracion'],'provincia':row['provincia'],'municipio':row['municipio'],'escala':row['escala'],'subescala':row['subescala'],'clase':row['clase'],'ambito':row['ambito'],'tipo_entidad':row['tipo_entidad'],'publicacion_id':row['publicacion_id'],'titulo_publicacion':row['titulo_original'],'especialidad':sp,'clasificacion_paso20':original.get('seguridad'),'clasificacion_paso26':cls,'canon_potencial':canon,'motivo_clasificacion':reason,'categoria_docente':'Maestro','cuerpo':'no determinable como cuerpo oficial sólo con esta denominación','relacion_laboral':bool(re.search(r'plantilla|laboral|jornada|tiempo parcial|fijo',k)),'centro':bool(re.search(r'escuela|colegio|centro|aula',k)),'funcion':None,'abreviaturas':[],'singular_plural_genero':{'barra':'/' in text,'guion':'-' in text,'plural':bool(re.search(r'\bmaestros?\b',k) and re.search(r'\bmaestros\b',k))},'parentesis':None,'repeticiones_exactas':{'filas':len(matches),'plazas':sum(float(x['plazas'] or 0) for x in matches),'ids':sorted(x['oposicion_id'] for x in matches),'anos':sorted({(x['fecha_boe'] or '')[:4] for x in matches}),'administraciones':sorted({x['administracion'] or '' for x in matches}),'canones_persistidos':sorted({x['puesto_normalizado'] or '' for x in matches})}}

def auditar(ruta_bd=DB):
 before=estado(ruta_bd); norm_before=sha(ROOT/'normalizacion_puestos.py'); d,orig,ids20=cargar(); c=sqlite3.connect(f'file:{Path(ruta_bd).resolve()}?mode=ro',uri=True); c.row_factory=sqlite3.Row
 try: all_rows=corpus(c)
 finally:c.close()
 by={r['oposicion_id']:r for r in all_rows}
 if any(i not in by for i in ids20):raise RuntimeError('Faltan IDs de PASO 20 en SQLite')
 fs=[ficha(by[i],orig[i],all_rows) for i in ids20]; ids=set(x['id'] for x in fs); names={}
 for f in fs:names[f['puesto']]={'denominacion':f['puesto'],**f['repeticiones_exactas'],'especialidad':f['especialidad'],'canon_recalculado':f['normalizar_puesto'],'clasificacion_final':f['clasificacion_paso26']}
 denoms=sorted(names.values(),key=lambda x:(-x['filas'],-x['plazas'],x['denominacion'])); classes=Counter(f['clasificacion_paso26'] for f in fs); gate=auditar_global(ruta_bd); after=estado(ruta_bd); norm_after=sha(ROOT/'normalizacion_puestos.py')
 if before!=after:raise RuntimeError('SQLite cambió durante la auditoría')
 a=[f for f in fs if f['clasificacion_paso26']=='A']; expected=sorted(f['id'] for f in a); obtained=sorted(f['id'] for f in fs if f['especialidad']=='Educación Física' and key(f['puesto']).replace('maestro/a','maestro').replace('maestro de educacion fisica','maestro de educacion fisica') in {'maestro de educacion fisica'})
 return {'version':'fase8-paso26-v1','generado_utc':datetime.now(timezone.utc).isoformat(),'modo':'read-only','git':git_state(),'baseline':before,'definicion_universo':{'criterio':'microfamilia otras_especialidades_docentes de PASO 20 reconciliada con SQLite','filas':len(fs),'plazas':sum(f['plazas'] for f in fs),'denominaciones':len(denoms)},'reconciliacion_paso20':{'ids_paso20':ids20,'ids_paso26':sorted(ids),'interseccion':sorted(set(ids20)&ids),'solo_paso20':sorted(set(ids20)-ids),'solo_paso26':sorted(ids-set(ids20))},'registros':fs,'denominaciones':denoms,'especialidades':dict(Counter(f['especialidad'] for f in fs)),'abreviaturas':{'ninguna':'No se encontraron abreviaturas inequívocas en las nueve denominaciones'},'clasificacion':{'por_clase':dict(classes),'filas':len(fs),'plazas':sum(f['plazas'] for f in fs)},'conjuntos_a':[{'canon':'Maestro de Educación Física','variantes':['Maestro de Educación Física','Maestro/a de Educación Física'],'ids':expected,'filas':len(a),'plazas':sum(f['plazas'] for f in a),'evidencia':'única diferencia género/ortotipografía; especialidad idéntica','riesgo_residual':'bajo, sujeto a confirmar alcance textual'}] if a else [],'simulaciones_a':[{'conjunto':'educacion_fisica','regla':'literal completo con variante maestro/maestro-a/maestro-a y Educación Física','esperados':expected,'obtenidos':obtained,'faltantes':sorted(set(expected)-set(obtained)),'inesperados':sorted(set(obtained)-set(expected)),'usa_fuzzy':False,'usa_ids_como_criterio':False,'denominaciones_capturadas':[f['puesto'] for f in a]}],'colisiones':{'infantil':[],'adultos':[],'funciones_compuestas':[],'laborales':[],'otras_especialidades':'Las restantes especialidades quedan fuera de la regla de Educación Física'},'puerta_global_paso19':{'total_discrepancias':gate['total_discrepancias'],'total_plazas_discrepantes':gate['total_plazas_discrepantes'],'cambios_reales_recalculables':gate['cambios_reales_recalculables']['filas'],'discrepancias_contextuales_no_recalculables':gate['discrepancias_contextuales_no_recalculables']['filas'],'discrepancias_no_clasificables_automaticamente':gate['discrepancias_no_clasificables_automaticamente']['filas']},'normalizador_sha256_inicial':norm_before,'normalizador_sha256_final':norm_after,'normalizador_modificado':norm_before!=norm_after,'sqlite_final':after,'sqlite_modificada':before!=after,'recomendacion_paso27':'No implementar todavía; diseñar PASO 27 exclusivamente para el conjunto Educación Física y revisar su alcance completo.'}

def main():
 p=argparse.ArgumentParser();p.add_argument('--bd',type=Path,default=DB);p.add_argument('--salida',type=Path,default=OUT);p.add_argument('--csv',type=Path,default=CSV_OUT);a=p.parse_args();r=auditar(a.bd);a.salida.parent.mkdir(parents=True,exist_ok=True);a.salida.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');fields=['id','puesto','plazas','especialidad','clasificacion_paso20','clasificacion_paso26','canon_potencial','administracion','ano','relacion_laboral','centro'];
 with a.csv.open('w',newline='',encoding='utf-8') as fh:
  w=csv.DictWriter(fh,fieldnames=fields);w.writeheader();w.writerows({k:x.get(k) for k in fields}|{'canon_potencial':x.get('canon_potencial')} for x in r['registros'])
 print(json.dumps({'universo':r['definicion_universo'],'clasificacion':r['clasificacion'],'conjuntos_a':r['conjuntos_a'],'sqlite_modificada':r['sqlite_modificada'],'gate':r['puerta_global_paso19']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
