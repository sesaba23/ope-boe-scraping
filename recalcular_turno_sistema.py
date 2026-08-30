"""Recálculo auditable de turno y sistema; no modifica el esquema."""
import argparse
import json
from collections import Counter
from pathlib import Path

import base_datos
from normalizacion_seleccion import normalizar_sistema, normalizar_turno

def propuestas(conexion):
    resultado=[]
    for oid,turno,sistema in conexion.execute("SELECT oposicion_id,turno,sistema FROM oposiciones"):
        cambios={}
        nuevo_turno=normalizar_turno(turno); nuevo_sistema=normalizar_sistema(sistema)
        if nuevo_turno != turno: cambios["turno"]=nuevo_turno
        if nuevo_sistema != sistema: cambios["sistema"]=nuevo_sistema
        if cambios: resultado.append((oid,cambios,(turno,sistema)))
    return resultado

def recalcular(ruta_bd="datos/boe.db", directorio_backup="backups/sqlite", dry_run=False):
    ruta=Path(ruta_bd); con=base_datos.conectar(ruta,readonly=True)
    try:
        meta=dict(con.execute("SELECT clave,valor FROM metadata"))
        if meta.get("schema_version") != "4": raise RuntimeError("El recálculo requiere schema_version 4")
        cambios=propuestas(con)
    finally: con.close()
    transformaciones=Counter((campo, anterior, nuevo) for _,cs,actual in cambios for campo,nuevo in cs.items() for anterior in (actual[0] if campo=="turno" else actual[1],))
    resumen={"dry_run":dry_run,"filas_cambiadas":len(cambios),"por_campo":dict(Counter(c for _,cs,_ in cambios for c in cs)),"transformaciones":[{"campo":c,"original":a,"canon":n,"filas":v} for (c,a,n),v in sorted(transformaciones.items())]}
    if dry_run or not cambios: return {**resumen,"backup":None,"data_version":meta["data_version"]}
    backup=base_datos.crear_backup(ruta,directorio_backup); con=base_datos.conectar(ruta)
    try:
        with base_datos.transaccion(con):
            for oid,cs,_ in cambios:
                con.execute("UPDATE oposiciones SET "+",".join(f"{c}=?" for c in cs)+" WHERE oposicion_id=?",(*cs.values(),oid))
            base_datos.guardar_metadata(con,data_version=int(meta["data_version"])+1)
            if base_datos.integrity_check(con)!=["ok"] or base_datos.foreign_key_check(con): raise RuntimeError("Falla integridad")
    finally: con.close()
    return {**resumen,"backup":str(backup),"data_version":str(int(meta["data_version"])+1)}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--base-datos",default="datos/boe.db"); p.add_argument("--directorio-backup",default="backups/sqlite"); p.add_argument("--dry-run",action="store_true")
    a=p.parse_args(argv); print(json.dumps(recalcular(a.base_datos,a.directorio_backup,a.dry_run),ensure_ascii=False,indent=2))
if __name__ == "__main__": main()
