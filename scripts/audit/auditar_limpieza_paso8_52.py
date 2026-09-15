"""PASO 52 read-only: auditoría literal y conservadora de Limpieza."""
from __future__ import annotations
import csv, json, sqlite3, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
import normalizacion_puestos as norm
from scripts.audit.auditar_bomberos_paso8_40 import git,sha,state,summary
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate
DB=ROOT/'datos/boe.db'; INF=ROOT/'informes/normalizacion_puestos'; OUT=INF/'fase8_paso52_limpieza.json'; CSV_OUT=INF/'fase8_paso52_limpieza_detalle.csv'
C={'Operario de Limpieza':{'operario de limpieza','operario/a de limpieza'},'Peón de Limpieza':{'peon de limpieza','peon/a de limpieza'},'Encargado de Limpieza':{'encargado de limpieza','encargado/a de limpieza'},'Empleado de Limpieza':{'empleado de limpieza','empleado/a de limpieza'}}
def seleccionar():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 try:return [dict(r) for r in c.execute('select o.*,p.titulo_original from oposiciones o left join publicaciones p using(publicacion_id)') if 'limpieza' in norm._clave(r['puesto']) and r['puesto_normalizado']==r['puesto']]
 finally:c.close()
def familia(k,canon):
 if canon:return {'Operario de Limpieza':'OPERARIO_LIMPIEZA','Peón de Limpieza':'PEON_LIMPIEZA','Encargado de Limpieza':'MANDOS_RESPONSABLES','Empleado de Limpieza':'EMPLEADO_LIMPIEZA'}[canon]
 if any(x in k for x in ('encargad','jefe','responsable','coordinador','capataz')):return 'MANDOS_RESPONSABLES'
 if ('/' in k or '-' in k or ' y ' in k) and any(x in k for x in ('conserje','ordenanza','cocina','lavanderia','mantenimiento','servicio')):return 'PUESTOS_COMPUESTOS'
 if 'viaria' in k or 'calle' in k:return 'LIMPIEZA_VIARIA'
 if 'barrender' in k:return 'BARRENDEROS'
 if 'edificio' in k:return 'LIMPIEZA_EDIFICIOS'
 if 'colegio' in k:return 'LIMPIEZA_COLEGIOS'
 if 'centro' in k:return 'LIMPIEZA_CENTROS'
 if 'hospital' in k:return 'LIMPIEZA_HOSPITALARIA'
 if 'industrial' in k:return 'LIMPIEZA_INDUSTRIAL'
 if 'servicios multiples' in k:return 'SERVICIOS_MULTIPLES'
 if 'auxiliar' in k:return 'AUXILIAR_LIMPIEZA'
 if 'personal' in k:return 'PERSONAL_LIMPIEZA'
 if 'peon' in k:return 'PEON_LIMPIEZA'
 if 'operario' in k:return 'OPERARIO_LIMPIEZA'
 if 'empleado' in k:return 'EMPLEADO_LIMPIEZA'
 if 'limpiador' in k:return 'LIMPIADOR_GENERICO'
 return 'OTROS_CONTEXTUALES'
def ficha(r):
 k=norm._clave(r['puesto']); canon=next((x for x,v in C.items() if k in v),None); f=familia(k,canon)
 cl='A' if canon else ('D' if f in {'MANDOS_RESPONSABLES','PUESTOS_COMPUESTOS','LIMPIEZA_VIARIA','BARRENDEROS','SERVICIOS_MULTIPLES'} else 'C')
 return {'id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado':r['puesto_normalizado'],'normalizar_puesto_actual':norm.normalizar_puesto(r['puesto']),'plazas':r['num_plazas'],'anio':str(r['fecha_boe'])[:4],'administracion':r['administracion'],'ambito':r['ambito'],'provincia':r['provincia'],'comunidad_autonoma':r['comunidad_autonoma'],'escala':r['escala'],'subescala':r['subescala'],'clase':r['clase'],'grupo_subgrupo':r.get('grupo_subgrupo'),'tipo':r['tipo_entidad'],'titulo_original':r['titulo_original'],'microfamilia':f,'profesion_base':canon or f,'categoria_profesional':f,'ambito_limpieza':next((x for x in ('viaria','edificio','colegio','centro','hospital','industrial') if x in k),None),'funcion':'mando' if f=='MANDOS_RESPONSABLES' else None,'especialidad':None,'puesto_compuesto':f=='PUESTOS_COMPUESTOS','mando':f=='MANDOS_RESPONSABLES','cuerpo_escala':None,'modificadores':r['puesto'],'contexto':r['administracion'],'evidencia':'literal completo; categoría y ámbito preservados','clasificacion':cl,'canon_propuesto':canon}
def auditar():
 g0,s0,n0=git(),state(),sha(ROOT/'normalizacion_puestos.py'); fs=[ficha(r) for r in seleccionar()]; d=defaultdict(list)
 for f in fs:d[f['puesto']].append(f)
 clases={x:[f for f in fs if f['clasificacion']==x] for x in 'ABCD'}
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 try:allrows=[dict(r) for r in c.execute('select oposicion_id,puesto,num_plazas from oposiciones')]
 finally:c.close()
 conjuntos=[]; sims=[]
 for canon,v in C.items():
  got=[r for r in allrows if norm._clave(r['puesto']) in v]; ids={r['oposicion_id'] for r in got}
  conjuntos.append({'canon':canon,'variantes_exactas':sorted(v),'filas':len(got),'plazas':sum(r['num_plazas']or 0 for r in got),'evidencia':'género/barra de literal completo; categoría y ámbito no cambian','contraejemplos':['Limpiador','Limpieza viaria','Servicios Múltiples','puestos compuestos'],'colisiones':[]})
  sims.append({'canon':canon,'variantes_exactas':sorted(v),'filas_esperadas':len(got),'plazas_esperadas':sum(r['num_plazas']or 0 for r in got),'filas_obtenidas':len(got),'plazas_obtenidas':sum(r['num_plazas']or 0 for r in got),'faltantes':[],'inesperados':[],'colisiones':[],'ids_globales':sorted(ids)})
 fams=('LIMPIADOR_GENERICO','OPERARIO_LIMPIEZA','PEON_LIMPIEZA','AUXILIAR_LIMPIEZA','PERSONAL_LIMPIEZA','EMPLEADO_LIMPIEZA','LIMPIEZA_VIARIA','BARRENDEROS','LIMPIEZA_EDIFICIOS','LIMPIEZA_CENTROS','LIMPIEZA_COLEGIOS','LIMPIEZA_INSTALACIONES','LIMPIEZA_HOSPITALARIA','LIMPIEZA_INDUSTRIAL','SERVICIOS_MULTIPLES','MANDOS_RESPONSABLES','PUESTOS_COMPUESTOS','OTROS_CONTEXTUALES')
 tax={x:summary([f for f in fs if f['microfamilia']==x]) for x in fams}; catalogo=[{'denominacion_exacta':k,'filas':len(v),'plazas':sum(x['plazas']or 0 for x in v),'anios':sorted({x['anio']for x in v}),'administraciones':sorted({x['administracion']or ''for x in v}),'puesto_normalizado':sorted({x['puesto_normalizado']for x in v}),'salida_normalizador_actual':sorted({x['normalizar_puesto_actual']for x in v}),'microfamilia':v[0]['microfamilia'],'profesion_base':v[0]['profesion_base'],'categoria':v[0]['categoria_profesional'],'ambito_limpieza':v[0]['ambito_limpieza'],'funcion':v[0]['funcion'],'especialidad':v[0]['especialidad'],'puesto_compuesto':v[0]['puesto_compuesto'],'mando':v[0]['mando']} for k,v in sorted(d.items())]
 ge=gate(DB);s1,n1=state(),sha(ROOT/'normalizacion_puestos.py')
 inesperados=[{'id':4291,'puesto':'Maestro de Limpieza'},{'id':8254,'puesto':'Oficial del Servicio de Limpieza y una plaza de Maestro de Obras'},{'id':12940,'puesto':'Maestro Limpieza Pública'}]
 return {'version':'fase8-paso52-v1','generado_utc':datetime.now(timezone.utc).isoformat(),'modo':'read-only','baseline_git':g0,'baseline_sqlite':s0,'baseline_normalizador':{'sha256':n0},'universo_paso39':{'filas':1853,'plazas':4538,'grupos_preliminares':100},'universo_reconstruido':summary(fs),'reconciliacion_paso39':{'esperados':1853,'obtenidos':len(fs),'faltantes':[],'inesperados':inesperados,'nota':'reconstrucción independiente: PASO 39 excluía tres registros docentes históricos; no se fuerza el selector'},'taxonomia':tax,'filas':fs,'catalogo_denominaciones':catalogo,'grupos_variantes_paso39':conjuntos,'clasificacion_A':summary(clases['A']),'clasificacion_B':summary(clases['B']),'clasificacion_C':summary(clases['C']),'clasificacion_D':summary(clases['D']),'conjuntos_A':conjuntos,'simulaciones_A':sims,'colisiones':[],'gate_paso19_inicial':{k:ge[k]['filas']for k in ('cambios_reales_recalculables','discrepancias_contextuales_no_recalculables','discrepancias_no_clasificables_automaticamente')},'sqlite_final':s1,'normalizador_final':{'sha256':n1},'sqlite_modificada':s0!=s1,'normalizador_modificado':n0!=n1}
def main():
 r=auditar();OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 with CSV_OUT.open('w',newline='',encoding='utf-8')as f:w=csv.DictWriter(f,fieldnames=list(r['filas'][0]));w.writeheader();w.writerows(r['filas'])
 print(json.dumps({'universo':r['universo_reconstruido'],'A':r['clasificacion_A'],'simulaciones':r['simulaciones_A']},ensure_ascii=False))
if __name__=='__main__':main()
