"""Reconciliación 9Q-1B; no modifica SQLite."""
import json,sqlite3,hashlib
from pathlib import Path
def main():
 c=sqlite3.connect('datos/boe.db'); c.row_factory=sqlite3.Row
 report=json.loads(Path('informes/normalizacion_puestos/fase7_universo_docente_pendiente_paso9p.json').read_text())
 actual=json.loads(Path('informes/normalizacion_puestos/fase7_otros_docentes_paso9q1.json').read_text())
 out={'sqlite':{'sha256':hashlib.sha256(Path('datos/boe.db').read_bytes()).hexdigest(),'data_version':dict(c.execute("select clave,valor from metadata where clave in ('schema_version','data_version')"))},'conteo_9p_reportado':report.get('familias',{}).get('otros'),'conteo_9q1':actual['universo']['filas'],'conjunto_canonico':None,'diferencia':{'motivo':'El informe 9P solo conserva agregados y no IDS_OTROS_9P; no es posible construir la comparación por ID ni la matriz de transición exigida.'},'reconciliacion_correcta':False}; p=Path('informes/normalizacion_puestos/fase7_otros_docentes_paso9q1b_reconciliacion.json');p.write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()
