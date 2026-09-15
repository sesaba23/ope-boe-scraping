"""Cierres de los bloques 64-69 y estado honesto del ciclo residual."""
from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.audit.auditar_bomberos_paso8_40 import state,sha
INF=ROOT/'informes/normalizacion_puestos'
def load(n):return json.loads((INF/n).read_text())
def close(nombre,paso_a,paso_r,paso_app,out):
 a,r,x=load(paso_a),load(paso_r),load(paso_app);p=x['primera_ejecucion']
 z={'universo_paso39':a['universo_paso39'],'universo_reconstruido':a['universo_reconstruido'],'reconciliacion_paso39':a['reconciliacion_paso39'],'taxonomia':a['taxonomia'],'clasificacion_A':a['clasificacion_A'],'clasificacion_B':a['clasificacion_B'],'clasificacion_C':a['clasificacion_C'],'clasificacion_D':a['clasificacion_D'],'conjuntos_A':a['conjuntos_A'],'simulaciones_A':a['simulaciones_A'],'reglas_implementadas':r['reglas_implementadas'],'cobertura_logica_A':{'filas':r['cobertura_logica_A_global_filas'],'plazas':r['cobertura_logica_A_global_plazas']},'gate_pre_sqlite':r['gate_pre_sqlite'],'backup_sqlite':p['backup'],'mutaciones':p['mutaciones'],'plazas_mutadas':p['plazas_mutadas'],'data_version_antes':p['antes']['data_version'],'data_version_despues':p['despues']['data_version'],'segunda_ejecucion':x['segunda_ejecucion'],'gate_paso19_final':x['gate_final'],'sqlite_final':p['despues'],'estado_final':f'FASE 8 — {nombre.upper()} CERRADA'}
 (INF/out).write_text(json.dumps(z,ensure_ascii=False,indent=2)+'\n')
 return z
def main():
 ts=close('Trabajo Social','fase8_paso64_trabajo_social.json','fase8_paso65_reglas_trabajo_social.json','fase8_paso66_aplicacion_trabajo_social.json','fase8_cierre_trabajo_social.json');co=close('Cocina','fase8_paso67_cocina.json','fase8_paso68_reglas_cocina.json','fase8_paso69_aplicacion_cocina.json','fase8_cierre_cocina.json');res=load('fase8_paso70_puestos_residuales.json');final=state()
 g={'baseline_git':ts.get('baseline_git'),'sqlite_inicial':ts['sqlite_final'],'sqlite_final':final,'normalizador_final':{'sha256':sha(ROOT/'normalizacion_puestos.py')},'trabajo_social':ts,'cocina':co,'auditoria_residual_inicial':res['universo_residual_inicial'],'ranking_familias_residuales':res['ranking_familias_residuales_completo'],'familias_residuales_auditadas':[],'conjuntos_A_pendientes_finales':res['conjuntos_A_seguros_pendientes'],'mutaciones_totales_fase_ejecucion':ts['mutaciones']+co['mutaciones'],'plazas_totales_afectadas':ts['plazas_mutadas']+co['plazas_mutadas'],'backups_creados':[ts['backup_sqlite'],co['backup_sqlite']],'evolucion_data_version':['57→58 Trabajo Social','58→59 Cocina'],'gate_paso19_final':co['gate_paso19_final'],'sqlite_integrity':final['integrity_check'],'sqlite_foreign_keys':final['foreign_key_check'],'estado_fase8':'ABIERTA: el inventario residual no acredita todavía A seguros pendientes = 0'}
 (INF/'fase8_cierre_global.json').write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'trabajo_social':ts['mutaciones'],'cocina':co['mutaciones'],'estado':g['estado_fase8']},ensure_ascii=False))
if __name__=='__main__':main()
