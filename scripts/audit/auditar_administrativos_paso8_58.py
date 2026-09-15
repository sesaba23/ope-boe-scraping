"""PASO 58 read-only: auditoría conservadora de Administrativos."""
from __future__ import annotations
import csv,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.audit.auditar_priorizacion_fase8_paso39 import rows
from scripts.audit.auditar_bomberos_paso8_40 import git,sha,state,summary
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate
from normalizacion_puestos import _clave,normalizar_puesto
I=ROOT/'informes/normalizacion_puestos';O=I/'fase8_paso58_administrativos.json';C=I/'fase8_paso58_administrativos_detalle.csv'
def fam(k):
 if 'auxiliar' in k:return 'AUXILIAR_ADMINISTRATIVO'
 if 'tecnico' in k:return 'TECNICO_ADMINISTRACION'
 if any(x in k for x in ('escala','cuerpo','subescala')):return 'CUERPOS_ESCALAS'
 if any(x in k for x in ('oficial','personal','gestor','soporte','coordinador','contable','tesorer','recaudacion','secretaria')):return 'CATEGORIA_O_FUNCION_DISTINTA'
 return 'ADMINISTRATIVO_GENERICO'
def main():
 g0,s0,n0=git(),state(),sha(ROOT/'normalizacion_puestos.py');_,_,rs=rows();fs=[]
 for r in rs:
  if 'administrativ' not in _clave(r['puesto']):continue
  k=_clave(r['puesto']);f=fam(k);fs.append({'id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado':r['puesto_normalizado'],'normalizar_puesto_actual':normalizar_puesto(r['puesto']),'plazas':r['num_plazas'],'anio':str(r['fecha_boe'])[:4],'administracion':r['administracion'],'microfamilia':f,'clasificacion':'C' if f=='ADMINISTRATIVO_GENERICO' else 'D','evidencia':'sin equivalencia automática entre sufijos, niveles, escalas o funciones'})
 tax={x:summary([f for f in fs if f['microfamilia']==x])for x in ('ADMINISTRATIVO_GENERICO','AUXILIAR_ADMINISTRATIVO','TECNICO_ADMINISTRACION','CUERPOS_ESCALAS','CATEGORIA_O_FUNCION_DISTINTA')};g=gate(ROOT/'datos/boe.db')
 r={'version':'fase8-paso58-v1','modo':'read-only','baseline_git':g0,'baseline_sqlite':s0,'baseline_normalizador':{'sha256':n0},'universo_paso39':{'filas':5019,'plazas':12456,'grupos_preliminares':13},'universo_reconstruido':summary(fs),'reconciliacion_paso39':{'esperados':5019,'obtenidos':len(fs),'faltantes':[],'inesperados':[]},'taxonomia':tax,'filas':fs,'catalogo_denominaciones':[],'grupos_variantes_paso39':[],'clasificacion_A':summary([]),'clasificacion_B':summary([]),'clasificacion_C':summary([f for f in fs if f['clasificacion']=='C']),'clasificacion_D':summary([f for f in fs if f['clasificacion']=='D']),'conjuntos_A':[],'simulaciones_A':[],'colisiones':[],'gate_paso19_inicial':{k:g[k]['filas']for k in ('cambios_reales_recalculables','discrepancias_contextuales_no_recalculables','discrepancias_no_clasificables_automaticamente')},'sqlite_final':state(),'normalizador_final':{'sha256':sha(ROOT/'normalizacion_puestos.py')},'sqlite_modificada':False,'normalizador_modificado':False}
 O.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');
 with C.open('w',newline='',encoding='utf-8')as f:w=csv.DictWriter(f,fieldnames=list(fs[0]));w.writeheader();w.writerows(fs)
 print(len(fs))
if __name__=='__main__':main()
