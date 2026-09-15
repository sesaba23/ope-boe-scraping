import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
I=ROOT/'informes/normalizacion_puestos'
a=json.loads((I/'fase8_paso71_ortografia.json').read_text())
b=json.loads((I/'fase8_paso71_clasificacion_residual.json').read_text())
out={'paso71a':'CERRADO','paso71b':'CERRADO','diagnostico_paso70':b['diagnostico_paso70'],'universo_total':b['universo_total'],'universo_ya_auditado':b['universo_ya_auditado'],'universo_residual_real':b['universo_residual_real'],'familias_totales':b['familias_totales'],'conteos_por_estado':b['conteos_por_estado'],'familias_pendientes':b['conteos_por_estado'].get('PENDIENTE_AUDITORIA',0),'ranking':b['familias'],'fingerprint':b['fingerprint'],'plan_paso72_en_adelante':b['plan_paso72_en_adelante'],'ortografia':{'mutaciones':a['mutaciones'],'plazas':a['plazas'],'otra':a['otras_diferencias'],'gate':a['gate_paso19'],'data_version':a['data_version']},'sqlite_final':a['sqlite_posterior'],'estado_fase8':'ABIERTA: quedan familias PENDIENTE_AUDITORIA'}
(I/'fase8_cierre_paso71.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
