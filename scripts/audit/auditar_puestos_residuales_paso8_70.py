"""PASO 70: inventario reproducible del universo residual, sin mutaciones."""
from __future__ import annotations
import csv,json,sqlite3,sys
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from normalizacion_puestos import _clave
from scripts.audit.auditar_bomberos_paso8_40 import state,sha,git
DB=ROOT/'datos/boe.db';INF=ROOT/'informes/normalizacion_puestos';OUT=INF/'fase8_paso70_puestos_residuales.json';CSV=INF/'fase8_paso70_puestos_residuales_detalle.csv'
CERRADAS=('docencia_maestros','bomberos','bibliotecas_archivos','tecnicos_informaticos','enfermeria','limpieza','conductores','administrativos','psicologia','trabajo_social','cocina')
def plazas(valor):
 try:return float(valor or 0)
 except (TypeError,ValueError):return 0.0
def familia(puesto):
 k=_clave(puesto)
 if not k:return 'SIN_DENOMINACION'
 if any(x in k for x in ('cuerpo','escala','subescala')):return 'CUERPOS_ESCALAS'
 if any(x in k for x in ('jefe','director','coordinador','responsable')):return 'MANDOS'
 if '-' in k or ' y ' in k:return 'PUESTOS_COMPUESTOS'
 return k.split()[0].capitalize()
def auditar():
 g,s,n=git(),state(),sha(ROOT/'normalizacion_puestos.py');c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 try:rs=[dict(r) for r in c.execute('select oposicion_id,puesto,puesto_normalizado,num_plazas,fecha_boe,administracion from oposiciones')]
 finally:c.close()
 grupos=defaultdict(list)
 for r in rs:grupos[familia(r['puesto'])].append(r)
 ranking=[]
 for f,v in grupos.items():
  den=Counter(x['puesto'] for x in v);repetidas=sum(n>1 for n in den.values());pot='SIN_POTENCIAL' if len(den)==1 else ('MEDIO' if repetidas else 'BAJO')
  ranking.append({'familia':f,'filas':len(v),'plazas':sum(plazas(x['num_plazas']) for x in v),'denominaciones':len(den),'variantes_repetidas':repetidas,'potencial_inicial':pot,'estado':'REQUIERE_AUDITORIA_SEMANTICA' if pot!='SIN_POTENCIAL' else 'SIN_VARIANTES'})
 ranking.sort(key=lambda x:(-x['filas'],-x['plazas'],x['familia']))
 detalle=[{'id':x['oposicion_id'],'puesto':x['puesto'],'puesto_normalizado':x['puesto_normalizado'],'plazas':x['num_plazas'],'anio':str(x['fecha_boe'])[:4],'administracion':x['administracion'],'familia':familia(x['puesto'])} for x in rs]
 return {'version':'fase8-paso70-v1','generado_utc':datetime.now(timezone.utc).isoformat(),'modo':'read-only','baseline_git':g,'sqlite':s,'normalizador':{'sha256':n},'universo_residual_inicial':{'filas':len(rs),'plazas':sum(plazas(x['num_plazas']) for x in rs),'denominaciones':len({x['puesto'] for x in rs}),'familias':len(ranking)},'familias_cerradas_conocidas':CERRADAS,'ranking_familias_residuales_completo':ranking,'filas':detalle,'conjuntos_A_seguros_pendientes':'NO_DETERMINADO: el ranking léxico no sustituye auditoría semántica por familia','estado':'AUDITORIA_INVENTARIO_COMPLETADA; NO AUTORIZA CIERRE GLOBAL'}
def main():
 r=auditar();OUT.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');
 with CSV.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=list(r['filas'][0]));w.writeheader();w.writerows(r['filas'])
 print(json.dumps(r['universo_residual_inicial'],ensure_ascii=False))
if __name__=='__main__':main()
