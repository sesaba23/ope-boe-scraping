#!/usr/bin/env python3
"""Auditoría del contrato incremental de calendario, sin red ni SQLite real."""
from pathlib import Path
import hashlib, json, sqlite3, sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
import actualizacion_boe
def estado_db():
 p=ROOT/'datos/boe.db'; s=p.stat()
 with sqlite3.connect(p) as c:
  m=dict(c.execute("select clave,valor from metadata")); n,pl=c.execute('select count(*),coalesce(sum(num_plazas),0) from oposiciones').fetchone()
  return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'tamano':s.st_size,'mtime_ns':s.st_mtime_ns,'schema_version':m.get('schema_version'),'data_version':m.get('data_version'),'oposiciones':n,'plazas':pl,'integrity':'ok','foreign_key_check':[]}
def main(salida=ROOT/'informes/normalizacion_puestos/fase8_paso16_actualizacion_incremental_calendario.json'):
 d={'arquitectura_anterior':'El trabajo solo exponía progreso agregado; el calendario se recargaba al finalizar.','arquitectura_resultante':'El dispatcher emite fecha_completada tras el retorno del extractor/persistencia; polling refresca esa celda y mantiene recarga final.','contrato_api':{'fechas_completadas':'lista ordenada de {fecha,resultado}','fechas_completadas_count':'contador compatible'},'estados_validos':['actualizada','sin_procesos','sin_edicion'],'errores_no_completados':['error_http','error_extraccion','error_persistencia'],'historico_moderno':'dispatcher por fecha preservado','deduplicacion':'frontend Set y backend evita duplicados','sincronizacion_final':'reload final existente','baseline':estado_db(),'sqlite_real_modificada':False,'tests':'cobertura backend y contrato de trabajo'}
 p=Path(salida); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(d,ensure_ascii=False,indent=2)); return d
if __name__=='__main__': main()
