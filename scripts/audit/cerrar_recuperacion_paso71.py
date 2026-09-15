import json
from pathlib import Path
from scripts.audit.auditar_bomberos_paso8_40 import state,sha
from scripts.audit.auditar_ortografia_puestos_paso8_71 import BACKUP
ROOT=Path(__file__).resolve().parents[2]
INF=ROOT/'informes/normalizacion_puestos'
r=json.loads((INF/'fase8_paso71_ortografia.json').read_text())
out={'backup_pre_paso71':r['backup'],'primera_transaccion':{'data_version_59_60':True,'filas_iniciales':5817,'plazas_iniciales':51432},'contextuales_sobrescritos':329,'plazas_contextuales':2215,'segunda_transaccion':{'data_version_60_61':True,'contextuales_restaurados':329},'id_30709':30709,'puesto_30709':'policía','canon_30709':'Policía Local','causa_discrepancia_30709':'la guarda comparaba presentación literal y no clave semántica','correccion_guarda_semantica':True,'sqlite_modificado_por_correccion_30709':False,'mutaciones_ortograficas_netas':5488,'plazas_ortograficas_netas':49217,'OTRA':r['otras_diferencias'],'gate_final':r.get('gate_paso19'),'sqlite_final':state(),'normalizador_sha':sha(ROOT/'normalizacion_puestos.py')}
(INF/'fase8_paso71_recuperacion.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
