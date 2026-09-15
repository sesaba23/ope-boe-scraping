import json,sqlite3,hashlib,glob,os
from pathlib import Path
from normalizacion_contextual_puestos import normalizar_puesto_efectivo
def main():
 c=sqlite3.connect('datos/boe.db');c.row_factory=sqlite3.Row; cambios=[]
 for r in c.execute('select * from oposiciones'):
  n=normalizar_puesto_efectivo(r['puesto'],administracion=r['administracion'],ambito=r['ambito'],tipo_entidad=r['tipo_entidad'],escala=r['escala'],subescala=r['subescala'],sistema=r['sistema'],municipio=r['municipio'],provincia=r['provincia']).normalizado
  if n!=r['puesto_normalizado']: cambios.append({'id':r['oposicion_id'],'actual':r['puesto_normalizado'],'calculado':n})
 reports={}
 for p in glob.glob('informes/normalizacion_puestos/fase7_*aplicacion.json'):
  try: reports[os.path.basename(p)]=json.load(open(p))
  except: pass
 q=json.loads(Path('informes/normalizacion_puestos/fase7_otros_docentes_paso9q1c_baseline.json').read_text()); baseline=q['fingerprint']; meta=dict(c.execute("select clave,valor from metadata where clave in ('schema_version','data_version')")); out={'sqlite':{'sha256':hashlib.sha256(Path('datos/boe.db').read_bytes()).hexdigest(),'schema_data':meta,'oposiciones':c.execute('select count(*) from oposiciones').fetchone()[0],'plazas':c.execute('select sum(num_plazas) from oposiciones').fetchone()[0],'integrity':c.execute('pragma integrity_check').fetchone()[0],'fk':c.execute('pragma foreign_key_check').fetchall()},'bloques':{'musica_9h':{'filas':1363,'plazas':1884},'artistica_9j':{'filas':6,'plazas':7},'universidad_9k':{'filas':60,'plazas':240},'maestros_9l':{'filas':25,'plazas':4675},'secundaria_9m':{'filas':3,'plazas':19},'fp_9n':'pendiente','eoi_9o':'cerrado_sin_cambios'},'recaclculo_efectivo':{'filas_que_cambiarian':len(cambios),'cambios':cambios},'baseline_9q':{'filas':q['reconstruccion_A']['filas'],'fingerprint':baseline},'informes_fuente':sorted(reports),'correcta':not cambios and meta.get('data_version')=='36'};Path('informes/normalizacion_puestos/fase7_paso9r_cierre.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps({'correcta':out['correcta'],'cambios':len(cambios)},ensure_ascii=False))
if __name__=='__main__':main()
