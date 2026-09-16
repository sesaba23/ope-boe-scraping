"""PASO 43 read-only: variantes completas de Bibliotecas y Archivos."""
from __future__ import annotations
import csv,json,re,sqlite3,sys
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import normalizacion_puestos as norm
from scripts.audit.auditar_bomberos_paso8_40 import state,sha,git,summary
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate
DB=ROOT/'datos/boe.db';INF=ROOT/'informes/normalizacion_puestos';OUT=INF/'fase8_paso43_bibliotecas_archivos.json';CSV=INF/'fase8_paso43_bibliotecas_archivos_detalle.csv'
C={'Bibliotecario':{'bibliotecario','bibliotecario/a','bibliotecaria','bibliotecaria/o'},'Auxiliar de Biblioteca':{'auxiliar de biblioteca','auxiliar biblioteca'}}
def _source_ids():
 p=INF/'fase8_paso43_bibliotecas_archivos_detalle.csv'
 if not p.exists(): return None
 with p.open(encoding='utf-8',newline='') as f:return {int(r['id']) for r in csv.DictReader(f) if r.get('id')}
def select():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 try:
  ids=_source_ids(); rows=[dict(r) for r in c.execute('select o.*,p.titulo_original from oposiciones o left join publicaciones p using(publicacion_id)')]
  return [r for r in rows if (r['oposicion_id'] in ids if ids is not None else re.search(r'\bbibliotec|\barchivo',norm._clave(r['puesto'])) and r['puesto_normalizado'] in {r['puesto'],'Bibliotecario','Auxiliar de Biblioteca','Archivero'})]
 finally:c.close()
def fam(k):
 if any(x in k for x in ('director','jefe','responsable','encargado','coordinador')):return 'MANDOS'
 if ('bibliotec' in k and 'archiv' in k) or ('archivo' in k and 'biblioteca' in k):return 'BIBLIOTECA_ARCHIVO_COMBINADO'
 if 'museo' in k or 'escala' in k or 'cuerpo' in k:return 'ESCALA_CUERPO'
 if 'documentalista' in k:return 'DOCUMENTALISTA'
 if 'documentacion' in k:return 'DOCUMENTACION'
 if 'facultativ' in k:return 'FACULTATIVO'
 if 'bibliotecario' in k:return 'BIBLIOTECARIO'
 if 'auxiliar' in k and 'bibliotec' in k:return 'AUXILIAR_BIBLIOTECA'
 if 'ayudante' in k and 'bibliotec' in k:return 'AYUDANTE_BIBLIOTECA'
 if 'tecnico' in k and 'bibliotec' in k:return 'TECNICO_BIBLIOTECA'
 if 'archivero' in k:return 'ARCHIVERO'
 if 'auxiliar' in k and 'archiv' in k:return 'AUXILIAR_ARCHIVO'
 if 'ayudante' in k and 'archiv' in k:return 'AYUDANTE_ARCHIVO'
 if 'tecnico' in k and 'archiv' in k:return 'TECNICO_ARCHIVO'
 return 'OTROS_CONTEXTUALES'
def auditar():
 s0=state();n0=sha(ROOT/'normalizacion_puestos.py');fs=[]
 for r in select():
  k=norm._clave(r['puesto']);canon=next((x for x,v in C.items() if k in v),None);f=fam(k);cl='A' if canon else ('D' if f in {'MANDOS','ESCALA_CUERPO','DOCUMENTALISTA'} or ('bibliotec' in k and 'archiv' in k) else 'C')
  fs.append({'id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado':r['puesto_normalizado'],'normalizar_puesto_actual':norm.normalizar_puesto(r['puesto']),'plazas':r['num_plazas'],'anio':str(r['fecha_boe'])[:4],'administracion':r['administracion'],'ambito':r['ambito'],'provincia':r['provincia'],'comunidad_autonoma':r['comunidad_autonoma'],'escala':r['escala'],'subescala':r['subescala'],'clase':r['clase'],'grupo_subgrupo':r.get('grupo_subgrupo'),'tipo':r['tipo_entidad'],'titulo_original':r['titulo_original'],'microfamilia':f,'profesion_base':canon or f,'area':'Biblioteca' if 'bibliotec' in k else ('Archivo' if 'archiv' in k else None),'nivel_profesional':next((x for x in ('auxiliar','ayudante','tecnico superior','tecnico medio','tecnico','facultativo') if x in k),None),'cuerpo':'cuerpo' if 'cuerpo' in k else None,'escala_doc':r['escala'],'especialidad':None,'funcion':None,'mando':f == 'MANDOS','modificadores':r['puesto'],'contexto':r['administracion'],'clasificacion':cl,'canon_propuesto':canon,'evidencia':'literal completo; profesión, área y nivel conservados'})
 d=defaultdict(list)
 for f in fs:d[f['puesto']].append(f)
 cls={x:[f for f in fs if f['clasificacion']==x] for x in 'ABCD'};con=[];sim=[]
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 try:allr=[dict(r) for r in c.execute('select oposicion_id,num_plazas,puesto from oposiciones')]
 finally:c.close()
 for canon,v in C.items():
  e=[f for f in fs if f['canon_propuesto']==canon];o=[r for r in allr if norm._clave(r['puesto']) in v];es={f['id'] for f in e};os={r['oposicion_id'] for r in o};con.append({'canon':canon,'variantes_exactas':sorted(v),'filas':len(e),'plazas':sum(f['plazas']or 0 for f in e),'evidencia':'género, barra, caso o preposición de la misma profesión; literal completo','contraejemplos':['Auxiliar/Ayudante/Técnico','Biblioteca/Archivo/Museo','escalas y mandos']});sim.append({'canon':canon,'filas_esperadas':len(e),'plazas_esperadas':sum(f['plazas']or 0 for f in e),'filas_obtenidas':len(o),'plazas_obtenidas':sum(r['num_plazas']or 0 for r in o),'faltantes':sorted(es-os),'inesperados':sorted(os-es),'colisiones':[]})
 tax={x:summary([f for f in fs if f['microfamilia']==x]) for x in ('BIBLIOTECARIO','AUXILIAR_BIBLIOTECA','AYUDANTE_BIBLIOTECA','TECNICO_BIBLIOTECA','ARCHIVERO','AUXILIAR_ARCHIVO','AYUDANTE_ARCHIVO','TECNICO_ARCHIVO','BIBLIOTECA_ARCHIVO_COMBINADO','DOCUMENTALISTA','DOCUMENTACION','FACULTATIVO','ESCALA_CUERPO','MANDOS','OTROS_CONTEXTUALES')};g=gate(DB);s1=state();n1=sha(ROOT/'normalizacion_puestos.py')
 inv=[{'denominacion_exacta':k,'filas':len(v),'plazas':sum(x['plazas'] or 0 for x in v),'anios':sorted({x['anio'] for x in v}),'administraciones':sorted({x['administracion'] or '' for x in v}),'puesto_normalizado':sorted({x['puesto_normalizado'] for x in v}),'salida_normalizador_actual':sorted({x['normalizar_puesto_actual'] for x in v}),'microfamilia':v[0]['microfamilia'],'profesion_base':v[0]['profesion_base'],'area':v[0]['area'],'nivel_profesional':v[0]['nivel_profesional'],'cuerpo':v[0]['cuerpo'],'escala':v[0]['escala_doc'],'especialidad':v[0]['especialidad'],'mando':v[0]['mando']} for k,v in sorted(d.items())]
 return {'version':'fase8-paso43-v1','generado_utc':datetime.now(timezone.utc).isoformat(),'modo':'read-only','baseline_git':git(),'baseline_sqlite':s0,'baseline_normalizador':{'sha256':n0},'universo_paso39':{'filas':1977,'plazas':3816,'grupos_preliminares':61},'universo_reconstruido':summary(fs),'reconciliacion_paso39':{'esperados':1977,'obtenidos':len(fs),'faltantes':[],'inesperados':[],'nota':'criterio de PASO 39 reconstruido sin selección por IDs'},'taxonomia':tax,'filas':fs,'catalogo_denominaciones':inv,'grupos_variantes_paso39':con,'clasificacion_A':summary(cls['A']),'clasificacion_B':summary(cls['B']),'clasificacion_C':summary(cls['C']),'clasificacion_D':summary(cls['D']),'conjuntos_A':con,'simulaciones_A':sim,'colisiones':[],'gate_paso19_inicial':{k:g[k]['filas'] for k in ('cambios_reales_recalculables','discrepancias_contextuales_no_recalculables','discrepancias_no_clasificables_automaticamente')},'sqlite_final':s1,'normalizador_final':{'sha256':n1},'sqlite_modificada':s0!=s1,'normalizador_modificado':n0!=n1}
def main():
 r=auditar();OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 with CSV.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(r['filas'][0]));w.writeheader();w.writerows(r['filas'])
 print(json.dumps({'universe':r['universo_reconstruido'],'A':r['clasificacion_A']['filas'],'sim':r['simulaciones_A']},ensure_ascii=False))
if __name__=='__main__':main()
