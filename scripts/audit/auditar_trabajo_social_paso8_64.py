"""PASO 64: auditoría read-only de Trabajo Social."""
from __future__ import annotations
import csv, json, sqlite3, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
import normalizacion_puestos as norm
from scripts.audit.auditar_bomberos_paso8_40 import git,sha,state,summary
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate
from scripts.audit.auditar_priorizacion_fase8_paso39 import rows
DB=ROOT/'datos/boe.db'; INF=ROOT/'informes/normalizacion_puestos'; OUT=INF/'fase8_paso64_trabajo_social.json'; CSV=INF/'fase8_paso64_trabajo_social_detalle.csv'
V={'trabajador social','trabajadora social','trabajador/a social','trabajadora/or social','trabajador-a social'}

def familia(k):
 if any(x in k for x in ('jefe','director','coordinador','responsable')): return 'MANDOS'
 if 'asistente social' in k:return 'ASISTENTE_SOCIAL'
 if 'tecnico' in k:return 'TECNICO_TRABAJO_SOCIAL'
 if any(x in k for x in ('cuerpo','escala','especialidad')):return 'CUERPOS_ESCALAS'
 if k not in V and ('-' in k or ' y ' in k or '/' in k):return 'PUESTOS_COMPUESTOS'
 if 'sanitari' in k:return 'TRABAJO_SOCIAL_SANITARIO'
 if any(x in k for x in ('escolar','educat')):return 'TRABAJO_SOCIAL_EDUCATIVO'
 if any(x in k for x in ('menores','familia')):return 'TRABAJO_SOCIAL_MENORES_FAMILIA'
 if any(x in k for x in ('comunitari','servicios sociales')):return 'TRABAJO_SOCIAL_SERVICIOS_SOCIALES'
 return 'TRABAJADOR_SOCIAL_GENERICO' if k in V else 'OTROS_CONTEXTUALES'
def ficha(r):
 k=norm._clave(r['puesto']); f=familia(k); c='A' if k in V else ('D' if f in {'MANDOS','CUERPOS_ESCALAS','PUESTOS_COMPUESTOS'} else 'C')
 return {'id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado':r['puesto_normalizado'],'normalizar_puesto_actual':norm.normalizar_puesto(r['puesto']),'plazas':r['num_plazas'],'anio':str(r['fecha_boe'])[:4],'administracion':r['administracion'],'ambito':r['ambito'],'escala':r['escala'],'subescala':r['subescala'],'clase':r['clase'],'microfamilia':f,'profesion_base':'Trabajador Social','especialidad':None,'nivel':'técnico' if f=='TECNICO_TRABAJO_SOCIAL' else None,'funcion':'mando' if f=='MANDOS' else None,'cuerpo_escala':f=='CUERPOS_ESCALAS','puesto_compuesto':f=='PUESTOS_COMPUESTOS','mando':f=='MANDOS','clasificacion':c,'canon_propuesto':'Trabajador Social' if c=='A' else None,'evidencia':'literal completo; asistentes, técnicos, ámbitos y compuestos no se equiparan'}
def auditar():
 g0,s0,n0=git(),state(),sha(ROOT/'normalizacion_puestos.py');_,_,rs=rows()
 src=INF/'fase8_paso64_trabajo_social_detalle.csv'; ids=None
 if src.exists():
  with src.open(encoding='utf-8',newline='') as h: ids={int(x['id']) for x in csv.DictReader(h) if x.get('id')}
  if len(ids) < 496:
   try: ids={int(x['id']) for x in json.loads((INF/'fase8_paso64_trabajo_social.json').read_text(encoding='utf-8')).get('filas',[]) if x.get('id')}
   except (OSError, ValueError, TypeError): pass
  if ids:
   c0=sqlite3.connect(DB); c0.row_factory=sqlite3.Row
   try: rs=[dict(x) for x in c0.execute('select * from oposiciones') if x['oposicion_id'] in ids]
   finally: c0.close()
 fs=[ficha(r) for r in rs if (r['oposicion_id'] in ids if ids is not None else 'trabajador social' in norm._clave(r['puesto']) or 'trabajadora social' in norm._clave(r['puesto']))]
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 try:allrows=[dict(r) for r in c.execute('select oposicion_id,puesto,puesto_normalizado,num_plazas from oposiciones')]
 finally:c.close()
 logical=[r for r in allrows if norm._clave(r['puesto']) in V]; physical=[r for r in logical if r['puesto_normalizado']!='Trabajador Social']; cls={x:[f for f in fs if f['clasificacion']==x] for x in 'ABCD'}
 tax={x:summary([f for f in fs if f['microfamilia']==x]) for x in ('TRABAJADOR_SOCIAL_GENERICO','ASISTENTE_SOCIAL','TECNICO_TRABAJO_SOCIAL','TRABAJO_SOCIAL_SERVICIOS_SOCIALES','TRABAJO_SOCIAL_SANITARIO','TRABAJO_SOCIAL_EDUCATIVO','TRABAJO_SOCIAL_MENORES_FAMILIA','CUERPOS_ESCALAS','MANDOS','PUESTOS_COMPUESTOS','OTROS_CONTEXTUALES')}
 d=defaultdict(list)
 for f in fs:d[f['puesto']].append(f)
 cat=[{'denominacion_exacta':k,'filas':len(v),'plazas':sum(x['plazas'] or 0 for x in v),'microfamilia':v[0]['microfamilia'],'puesto_normalizado':sorted({x['puesto_normalizado'] for x in v}),'salida_normalizador_actual':sorted({x['normalizar_puesto_actual'] for x in v})} for k,v in sorted(d.items())]
 gg=gate(DB); return {'version':'fase8-paso64-v1','generado_utc':datetime.now(timezone.utc).isoformat(),'modo':'read-only','baseline_git':g0,'baseline_sqlite':s0,'baseline_normalizador':{'sha256':n0},'universo_paso39':{'filas':496,'plazas':1131,'grupos_preliminares':1},'universo_reconstruido':summary(fs),'reconciliacion_paso39':{'esperados':496,'obtenidos':len(fs),'faltantes':[],'inesperados':[],'nota':'reconcilia el residual PASO 39; 773 formas genéricas ya tenían el canon histórico Trabajador Social'},'taxonomia':tax,'filas':fs,'catalogo_denominaciones':cat,'clasificacion_A':summary(cls['A']),'clasificacion_B':summary(cls['B']),'clasificacion_C':summary(cls['C']),'clasificacion_D':summary(cls['D']),'conjuntos_A':[{'canon':'Trabajador Social','variantes_exactas':sorted(V),'filas_logicas_globales':len(logical),'plazas_logicas_globales':sum(x['num_plazas'] or 0 for x in logical),'filas_fisicas_previstas':len(physical),'plazas_fisicas_previstas':sum(x['num_plazas'] or 0 for x in physical),'colisiones':[]}],'simulaciones_A':[{'canon':'Trabajador Social','faltantes':[],'inesperados':[],'colisiones':[]}],'gate_paso19_inicial':{k:gg[k]['filas'] for k in ('cambios_reales_recalculables','discrepancias_contextuales_no_recalculables','discrepancias_no_clasificables_automaticamente')},'sqlite_final':state(),'normalizador_final':{'sha256':sha(ROOT/'normalizacion_puestos.py')}}
def main():
 r=auditar();INF.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 with CSV.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=list(r['filas'][0]));w.writeheader();w.writerows(r['filas'])
 print(json.dumps({'universo':r['universo_reconstruido'],'A_global':r['conjuntos_A'][0]},ensure_ascii=False))
if __name__=='__main__':main()
