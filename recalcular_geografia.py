"""Recálculo auditable de geografía v4; usar --dry-run antes de escribir."""
import argparse, json
from collections import Counter
from pathlib import Path
import base_datos
from resolucion_geografica import resolver_administracion_geografia

CAMPOS=("administracion_normalizada","ambito","tipo_entidad","municipio","provincia","comunidad_autonoma","confianza_geografica","evidencia_geografica","version_resolutor")
def propuestas(con):
    resultado=[]
    for oid,admin,puesto,*actual in con.execute("SELECT oposicion_id,administracion,puesto,"+",".join(CAMPOS)+" FROM oposiciones"):
        r=resolver_administracion_geografia(admin,puesto)
        # La ausencia de evidencia nueva nunca borra una ubicación histórica.
        geo = (r.municipio or actual[3], r.provincia or actual[4], r.comunidad_autonoma or actual[5])
        valores=(r.administracion_normalizada,r.ambito,r.tipo_entidad,*geo,r.confianza,r.evidencia,r.version_catalogo)
        cambios={c:v for c,v,a in zip(CAMPOS,valores,actual) if v != a}
        if cambios: resultado.append((oid,cambios,r))
    return resultado
def recalcular(ruta_bd="datos/boe.db",directorio_backup="backups/sqlite",dry_run=False):
    ruta=Path(ruta_bd); con=base_datos.conectar(ruta,readonly=True)
    try:
        meta=dict(con.execute("SELECT clave,valor FROM metadata"))
        if meta.get("schema_version")!="4": raise RuntimeError("El recálculo requiere schema_version 4")
        cambios=propuestas(con)
    finally: con.close()
    resumen={"dry_run":dry_run,"filas_cambiadas":len(cambios),"por_campo":dict(Counter(c for _,x,_ in cambios for c in x)),"por_confianza":dict(Counter(r.confianza for _,_,r in cambios)),"por_evidencia":dict(Counter(r.evidencia for _,_,r in cambios)),"conflictos":sum(r.confianza=="AMBIGUA" for _,_,r in cambios)}
    if dry_run or not cambios: return {**resumen,"backup":None,"data_version":meta["data_version"]}
    backup=base_datos.crear_backup(ruta,directorio_backup); con=base_datos.conectar(ruta)
    try:
        with base_datos.transaccion(con):
            for oid,cam,_ in cambios:
                con.execute("UPDATE oposiciones SET "+",".join(f"{c}=?" for c in cam)+" WHERE oposicion_id=?",(*cam.values(),oid))
            base_datos.guardar_metadata(con,data_version=int(meta["data_version"])+1)
            if base_datos.integrity_check(con)!=["ok"] or base_datos.foreign_key_check(con): raise RuntimeError("Falla integridad")
    finally: con.close()
    return {**resumen,"backup":str(backup),"data_version":str(int(meta["data_version"])+1)}
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--base-datos",default="datos/boe.db");p.add_argument("--directorio-backup",default="backups/sqlite");p.add_argument("--dry-run",action="store_true");a=p.parse_args(argv);print(json.dumps(recalcular(a.base_datos,a.directorio_backup,a.dry_run),ensure_ascii=False,indent=2))
if __name__=="__main__": main()
