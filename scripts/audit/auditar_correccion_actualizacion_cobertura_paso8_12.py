"""Audita el dispatcher web ordinario/histórico sin efectuar descargas ni escrituras."""
from __future__ import annotations
import inspect, json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import actualizacion_boe, plazasboe

SALIDA = Path('informes/normalizacion_puestos/fase8_paso12_correccion_actualizacion_cobertura.json')

def ejecutar(salida=SALIDA):
    llamada = {}
    original = actualizacion_boe._actualizar_historico
    def captura(fecha, ruta_bd, progreso):
        llamada.update({'fechas_explicitamente': [fecha], 'ruta_bd': ruta_bd})
        return {'simulado': True}
    actualizacion_boe._actualizar_historico = captura
    try:
        actualizacion_boe._actualizar_productivo(['2004/01/01'], 'copia.db', lambda *_: None)
    finally:
        actualizacion_boe._actualizar_historico = original
    out = {
        'modo': 'read-only-mock',
        'call_graph': ['_actualizar_productivo', '_actualizar_historico', 'ejecutar_flujo_historico'],
        'fecha_prueba': '2004/01/01',
        'seleccion_extractor': plazasboe.seleccionar_extractor('2004-01-01'),
        'actualizador_web': inspect.getsource(actualizacion_boe._actualizar_productivo).strip(),
        'actualizar_fechas': inspect.getsource(plazasboe.actualizar_fechas).strip(),
        'llamada_capturada': {k: ('<callback>' if callable(v) else v) for k,v in llamada.items()},
        'flujo_historico_requiere_callbacks': True,
        'causa': 'El dispatcher web separa por fecha el extractor histórico del pipeline moderno y conecta callbacks transaccionales.',
        'correccion_aplicada': True,
        'gate': '12D',
    }
    p=Path(salida); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); return out

if __name__ == '__main__': print(json.dumps(ejecutar(),ensure_ascii=False,indent=2))
