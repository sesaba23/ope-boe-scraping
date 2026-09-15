"""Cierre regenerable de la aplicación 9L, sin escribir SQLite."""
import hashlib,json,sqlite3
from pathlib import Path
BACKUP=Path('backups/sqlite/boe_20260912_084746_007535.db')
def _hash(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 before=sqlite3.connect(BACKUP); after=sqlite3.connect('datos/boe.db'); before.row_factory=after.row_factory=sqlite3.Row
 a={r['oposicion_id']:dict(r) for r in before.execute('select * from oposiciones')}; b={r['oposicion_id']:dict(r) for r in after.execute('select * from oposiciones')}; ids=[]; fields=set()
 for i,x in a.items():
  dif=[k for k in x if x[k]!=b[i][k]]
  if dif: ids.append(i); fields.update(dif)
 out={'backup':{'ruta':str(BACKUP),'sha256':_hash(BACKUP),'schema_data':dict(before.execute("select clave,valor from metadata where clave in ('schema_version','data_version')"))},'aplicacion':{'ids':ids,'filas':len(ids),'plazas':sum(b[i]['num_plazas'] or 0 for i in ids),'canones':sorted(set(b[i]['puesto_normalizado'] for i in ids)),'campos_modificados':sorted(fields)},'sqlite_final':{'sha256':_hash('datos/boe.db'),'schema_data':dict(after.execute("select clave,valor from metadata where clave in ('schema_version','data_version')")),'integrity':after.execute('pragma integrity_check').fetchone()[0],'fk':after.execute('pragma foreign_key_check').fetchall()},'correcta':len(ids)==25 and sum(b[i]['num_plazas'] or 0 for i in ids)==4675 and fields=={'puesto_normalizado'} and set(b[i]['puesto_normalizado'] for i in ids)=={'Maestros'}}
 p=Path('informes/normalizacion_puestos/fase7_maestros_paso9l5_cierre.json'); p.write_text(json.dumps(out,ensure_ascii=False,indent=2)); print(json.dumps({'correcta':out['correcta'],'filas':len(ids),'plazas':out['aplicacion']['plazas']},ensure_ascii=False))
if __name__=='__main__': main()
