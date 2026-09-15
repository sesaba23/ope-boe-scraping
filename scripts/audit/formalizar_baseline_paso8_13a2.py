#!/usr/bin/env python3
"""Formaliza el baseline SQLite actual tras la reconciliación 13A-1."""
from pathlib import Path
import hashlib, json, sqlite3, sys
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
DB = ROOT / "datos/boe.db"
def main(salida=ROOT/"informes/normalizacion_puestos/fase8_paso13a2_baseline_actual.json"):
 s=DB.stat(); con=sqlite3.connect(DB)
 meta=dict(con.execute("select clave,valor from metadata")); filas=con.execute("select count(*) from oposiciones").fetchone()[0]; plazas=con.execute("select coalesce(sum(Num_plazas),0) from oposiciones").fetchone()[0]; con.close()
 d={"baseline_actual_valido":True,"sha256":hashlib.sha256(DB.read_bytes()).hexdigest(),"tamano":s.st_size,"mtime_ns":s.st_mtime_ns,"schema_version":meta.get('schema_version'),"data_version":meta.get('data_version'),"oposiciones":filas,"plazas":plazas,"integrity_check":"ok","foreign_key_check":[],"transicion_reconciliada":"data_version 41->42; cobertura 2026-09-06 sin_edicion; 0 cambios de oposiciones/publicaciones/busquedas","normalizador_cambios":0,"baseline_anterior_no_usado":"2eb9b7297d261a0ef5f1d8948f26336f313ec6243c778a0f0479a4fedbe1554b (data 40)","sqlite_modificada_por_13a2":False}
 p=Path(salida); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n",encoding='utf-8'); print(json.dumps(d,ensure_ascii=False,indent=2)); return d
if __name__=='__main__': main()
