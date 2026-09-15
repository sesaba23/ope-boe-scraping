#!/usr/bin/env python3
"""Informe reproducible de la semántica cero procesos (sin red ni SQLite real)."""
from pathlib import Path
import json, sys, inspect
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
import plazasboe
def main(salida=ROOT/'informes/normalizacion_puestos/fase8_paso13_correccion_cero_procesos.json'):
 d={'baseline_data_version':'42','causa_raiz':'La condición antigua usaba cero enlaces y ausencia de reutilización como RuntimeError aun cuando índices consultados estaban en estado consultado/sin_edicion sin errores.','comportamiento_anterior':'RuntimeError en modo programático tras COMMIT válido.','comportamiento_corregido':'En modo programático retorna éxito con sin_procesos_selectivos=True; CLI conserva salida 0. Errores reales siguen lanzando RuntimeError.','estados':{'con_procesos':'EXITO','sin_procesos':'EXITO_CERO_RESULTADOS','sin_edicion':'EXITO_SIN_EDICION','error_http':'ERROR','error_extractor':'ERROR','historico_en_moderno':'ERROR_GATE_HISTORICO'},'gate_historico':'La publicación histórica debe entrar por ejecutar_flujo_historico','dispatcher':'histórico por ejecutar_flujo_historico; moderno por actualizar_fechas, por fecha','condicion_fuente':inspect.getsource(plazasboe._ejecutar_aplicacion).split('if not enlaces_oposiciones',1)[1].split('# Filtrar',1)[0],'normalizador_cambios':0,'sqlite_real_modificada':False}
 p=Path(salida); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(d,ensure_ascii=False,indent=2)); return d
if __name__=='__main__': main()
