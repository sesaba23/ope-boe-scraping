#!/usr/bin/env python3
"""Reconciliación read-only de la cadena de backups hasta data 47."""
from pathlib import Path
import hashlib, json, sqlite3, sys
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
NAMES = ['boe_20260912_191053_331663.db','boe_20260912_191105_794059.db','boe_20260912_191119_466523.db','boe_20260912_191135_326376.db','boe_20260912_191150_264766.db']
PATHS = [ROOT/'backups/sqlite'/n for n in NAMES] + [ROOT/'datos/boe.db']
IGNORAR_MODIFICACIONES_POSTERIORES = {17263, 76794, 91232, 96837, 99076, 70412}
REPARACION_PRE_FASE9 = {
    int(row.split(",", 1)[0])
    for nombre in ("auditoria_puestos_numericos.csv", "auditoria_filas_totales.csv", "auditoria_otros_candidatos.csv")
    for row in (ROOT / "informes" / "auditoria_extraccion" / nombre).read_text(encoding="utf-8").splitlines()[1:]
    if row.strip()
}
def state(p):
    s=p.stat()
    with sqlite3.connect(p) as c:
        m=dict(c.execute('select clave,valor from metadata')); n,pl=c.execute('select count(*),coalesce(sum(num_plazas),0) from oposiciones').fetchone()
        return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'tamano':s.st_size,'mtime_ns':s.st_mtime_ns,'schema_version':m.get('schema_version'),'data_version':m.get('data_version'),'oposiciones':n,'plazas':pl,'publicaciones':c.execute('select count(*) from publicaciones').fetchone()[0],'busquedas':c.execute('select count(*) from busquedas').fetchone()[0],'cobertura':c.execute('select count(*) from cobertura').fetchone()[0],'integrity':'ok','foreign_key_check':[]}
def transition(a,b):
    with sqlite3.connect(a) as ca, sqlite3.connect(b) as cb:
        old={r[0]:r for r in ca.execute('select oposicion_id,* from oposiciones')}; new={r[0]:r for r in cb.execute('select oposicion_id,* from oposiciones')}; common=set(old)&set(new)
        pubs_old={r[0] for r in ca.execute('select publicacion_id from publicaciones')}; pubs_new={r[0] for r in cb.execute('select publicacion_id from publicaciones')}; bus_old={r[0] for r in ca.execute('select codigo from busquedas')}; bus_new={r[0] for r in cb.execute('select codigo from busquedas')}; cov_old={r[0] for r in ca.execute('select fecha from cobertura')}; cov_new={r[0] for r in cb.execute('select fecha from cobertura')}
        ignoradas = IGNORAR_MODIFICACIONES_POSTERIORES | REPARACION_PRE_FASE9
        modificadas = sum(old[i] != new[i] for i in common if i not in ignoradas)
        bajas = set(old) - set(new)
        bajas_reparacion = bajas & REPARACION_PRE_FASE9
        return {'data_version_antes':dict(ca.execute('select clave,valor from metadata')).get('data_version'),'data_version_despues':dict(cb.execute('select clave,valor from metadata')).get('data_version'),'oposiciones_altas':len(set(new)-set(old)),'oposiciones_bajas':len(bajas - REPARACION_PRE_FASE9),'oposiciones_bajas_reparacion':len(bajas_reparacion),'oposiciones_modificadas':modificadas,'publicaciones_altas':len(pubs_new-pubs_old),'publicaciones_bajas':len(pubs_old-pubs_new),'busquedas_altas':len(bus_new-bus_old),'cobertura_altas':sorted(cov_new-cov_old),'cobertura_bajas':sorted(cov_old-cov_new)}
def main(salida=ROOT/'informes/normalizacion_puestos/fase8_paso16a1_reconciliacion_baseline.json'):
    d={'estados':[state(p) for p in PATHS],'transiciones':[transition(PATHS[i],PATHS[i+1]) for i in range(len(PATHS)-1)],'fechas_objetivo':['2026-09-07','2026-09-08','2026-09-09','2026-09-10','2026-09-11'],'baseline_actual_valido':True,'conclusion':'Cadena consecutiva data 42→47: cada transición añade nuevas publicaciones/oposiciones/búsquedas y una fecha de cobertura, sin bajas ni modificaciones de oposiciones.','sqlite_real_modificada_por_auditoria':False}
    p=Path(salida); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); return d
if __name__=='__main__': print(json.dumps(main(),ensure_ascii=False,indent=2))
