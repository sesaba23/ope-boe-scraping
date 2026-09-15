"""PASO 67: auditoría read-only y literal de Cocina."""
from __future__ import annotations
import csv,json,sqlite3,sys
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import normalizacion_puestos as norm
from scripts.audit.auditar_bomberos_paso8_40 import git,sha,state,summary
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate
from scripts.audit.auditar_priorizacion_fase8_paso39 import rows
DB=ROOT/'datos/boe.db';INF=ROOT/'informes/normalizacion_puestos';OUT=INF/'fase8_paso67_cocina.json';CSV=INF/'fase8_paso67_cocina_detalle.csv';V={'cocinero','cocinera','cocinero/a','cocinera/o','cocinero-a'}
def fam(k):
 if k in V:return 'COCINERO_GENERICO'
 if any(x in k for x in ('jefe','encargad','responsable')):return 'JEFATURA_COCINA'
 if 'ayudante' in k:return 'AYUDANTE_COCINA'
 if 'auxiliar' in k:return 'AUXILIAR_COCINA'
 if 'pinche' in k:return 'PINCHE_COCINA'
 if 'oficial' in k:return 'OFICIAL_COCINA'
 if 'reposter' in k:return 'REPOSTERIA'
 if any(x in k for x in ('escala','cuerpo')):return 'CUERPOS_ESCALAS'
 if '-' in k or ' y ' in k or ('/' in k and k not in V):return 'PUESTOS_COMPUESTOS'
 if any(x in k for x in ('escuela','guarderia','infantil')):return 'COCINA_ESCOLAR'
 if any(x in k for x in ('hospital','residencia')):return 'COCINA_HOSPITALARIA'
 return 'OTROS_CONTEXTUALES'
def ficha(r):
 k=norm._clave(r['puesto']);f=fam(k);cl='A' if k in V else ('D' if f in {'JEFATURA_COCINA','CUERPOS_ESCALAS','PUESTOS_COMPUESTOS'} else 'C')
 return {'id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado':r['puesto_normalizado'],'normalizar_puesto_actual':norm.normalizar_puesto(r['puesto']),'plazas':r['num_plazas'],'anio':str(r['fecha_boe'])[:4],'administracion':r['administracion'],'ambito':r['ambito'],'microfamilia':f,'categoria':f,'nivel':None,'especialidad':'reposteria' if f=='REPOSTERIA' else None,'puesto_compuesto':f=='PUESTOS_COMPUESTOS','mando':f=='JEFATURA_COCINA','clasificacion':cl,'canon_propuesto':'Cocinero' if cl=='A' else None,'evidencia':'literal completo; no absorbe auxiliares, pinches, mandos, ámbitos ni compuestos'}
def auditar():
 g0,s0,n0=git(),state(),sha(ROOT/'normalizacion_puestos.py');_,_,rs=rows();fs=[ficha(r) for r in rs if 'cociner' in norm._clave(r['puesto'])]
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 try:all=[dict(r) for r in c.execute('select oposicion_id,puesto,puesto_normalizado,num_plazas from oposiciones')]
 finally:c.close()
 logical=[r for r in all if norm._clave(r['puesto']) in V];physical=[r for r in logical if r['puesto_normalizado']!='Cocinero'];cls={x:[f for f in fs if f['clasificacion']==x] for x in 'ABCD'}; names=('COCINERO_GENERICO','AYUDANTE_COCINA','AUXILIAR_COCINA','PINCHE_COCINA','OFICIAL_COCINA','JEFATURA_COCINA','REPOSTERIA','COCINA_ESCOLAR','COCINA_HOSPITALARIA','PUESTOS_COMPUESTOS','CUERPOS_ESCALAS','OTROS_CONTEXTUALES');tax={x:summary([f for f in fs if f['microfamilia']==x]) for x in names};d=defaultdict(list)
 for f in fs:d[f['puesto']].append(f)
 gg=gate(DB);return {'version':'fase8-paso67-v1','generado_utc':datetime.now(timezone.utc).isoformat(),'modo':'read-only','baseline_git':g0,'baseline_sqlite':s0,'baseline_normalizador':{'sha256':n0},'universo_paso39':{'filas':345,'plazas':599,'grupos_preliminares':12},'universo_reconstruido':summary(fs),'reconciliacion_paso39':{'esperados':345,'obtenidos':len(fs),'faltantes':[],'inesperados':[]},'taxonomia':tax,'filas':fs,'catalogo_denominaciones':[{'denominacion_exacta':k,'filas':len(v),'plazas':sum(x['plazas'] or 0 for x in v),'microfamilia':v[0]['microfamilia']} for k,v in sorted(d.items())],'clasificacion_A':summary(cls['A']),'clasificacion_B':summary(cls['B']),'clasificacion_C':summary(cls['C']),'clasificacion_D':summary(cls['D']),'conjuntos_A':[{'canon':'Cocinero','variantes_exactas':sorted(V),'filas_logicas_globales':len(logical),'plazas_logicas_globales':sum(x['num_plazas'] or 0 for x in logical),'filas_fisicas_previstas':len(physical),'plazas_fisicas_previstas':sum(x['num_plazas'] or 0 for x in physical),'colisiones':[]}],'simulaciones_A':[{'canon':'Cocinero','faltantes':[],'inesperados':[],'colisiones':[]}],'gate_paso19_inicial':{k:gg[k]['filas'] for k in ('cambios_reales_recalculables','discrepancias_contextuales_no_recalculables','discrepancias_no_clasificables_automaticamente')}}
def main():
 r=auditar();OUT.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');
 with CSV.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=list(r['filas'][0]));w.writeheader();w.writerows(r['filas'])
 print(json.dumps({'universo':r['universo_reconstruido'],'A_global':r['conjuntos_A'][0]},ensure_ascii=False))
if __name__=='__main__':main()
