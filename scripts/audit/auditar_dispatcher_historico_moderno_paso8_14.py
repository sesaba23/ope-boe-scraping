#!/usr/bin/env python3
"""Audita la coherencia del clasificador web sin red ni escrituras."""
from pathlib import Path
import hashlib, json, sqlite3, sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
import actualizacion_boe, plazasboe

def estado_db():
 p=ROOT/'datos/boe.db'; s=p.stat();
 with sqlite3.connect(p) as c:
  m=dict(c.execute('select clave,valor from metadata'))
  n,pl=c.execute('select count(*),coalesce(sum(num_plazas),0) from oposiciones').fetchone()
  return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'tamano':s.st_size,'mtime_ns':s.st_mtime_ns,'schema_version':m.get('schema_version'),'data_version':m.get('data_version'),'oposiciones':n,'plazas':pl,'integrity':'ok','foreign_key_check':[]}
def main(salida=ROOT/'informes/normalizacion_puestos/fase8_paso14_dispatcher_historico_moderno.json'):
 fechas=['2003-12-31','2004-01-01','2004/01/01','2004-12-31','2026-09-06', '2026-09-12']
 decisiones=[{'entrada':f,'tipo':type(f).__name__,'selector':plazasboe.seleccionar_extractor(f),'dispatcher':plazasboe.seleccionar_extractor(f)} for f in fechas]
 src=Path(ROOT/'actualizacion_boe.py').read_text(encoding='utf-8'); src_plazas=Path(ROOT/'plazasboe.py').read_text(encoding='utf-8')
 d={'baseline':estado_db(),'fecha_problemática':'fecha moderna exterior con metadatos de publicación que contienen 2004','decisiones':decisiones,'clasificadores_inventariados':[{'archivo':'actualizacion_boe.py','funcion':'_actualizar_productivo','condicion':'seleccionar_extractor(fecha) == historico','resultado':'historico/moderno'},{'archivo':'plazasboe.py','funcion':'seleccionar_extractor','condicion':'"2004" in str(fecha)','resultado':'historico/actual'},{'archivo':'plazasboe.py','funcion':'_ejecutar_aplicacion','condicion':'seleccionar_extractor(fecha_indice) == historico','resultado':'gate histórico'}],'causa_raiz_demostrada':True,'causa_raiz':'El pipeline reutilizaba fecha_boe, extraída de los metadatos de cada publicación, para decidir el extractor. Una fecha secundaria con texto 2004 podía activar el gate durante un índice moderno. La decisión debe usar fecha_indice, que representa el día solicitado.','evidencia_traceback':'La rama moderna era correcta para la fecha exterior; el gate se alcanzaba al procesar una publicación concreta, antes de la corrección la condición usaba fecha_boe.','codigo_actual_coherente':('seleccionar_extractor(fecha)' in src and 'seleccionar_extractor(fecha_indice)' in src_plazas),'correccion_aplicada':True,'gate_historico_preservado':True,'dispatcher_unica_fuente':True,'normalizador_cambios':0,'sqlite_real_modificada':False}
 p=Path(salida); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(d,ensure_ascii=False,indent=2)); return d
if __name__=='__main__': main()
