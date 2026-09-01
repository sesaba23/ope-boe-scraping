"""Recálculo auditable de geografía v4; usar --dry-run antes de escribir."""
import argparse, json
from collections import Counter
from pathlib import Path
import base_datos
from resolucion_geografica import resolver_administracion_geografia
from migrar_esquema_sqlite import (
    normalizar_referencias_administrativas,
    relaciones_territoriales_seguras_pendientes,
)

CAMPOS=("administracion_normalizada","ambito","tipo_entidad","municipio","provincia","comunidad_autonoma","confianza_geografica","evidencia_geografica","version_resolutor")
def propuestas_universidades(con):
    """Usa sólo nombres exactos del catálogo y propaga por publicación única."""
    from resolucion_universidades import catalogo, detectar
    datos, indice = catalogo()
    ids = dict(con.execute("SELECT nombre,universidad_id FROM universidades"))
    filas=list(con.execute("SELECT oposicion_id,publicacion_id,puesto,escala,universidad_id,ambito,tipo_entidad,municipio,municipio_codigo_ine,provincia,provincia_id,comunidad_autonoma,comunidad_id,confianza_geografica,evidencia_geografica FROM oposiciones WHERE administracion='Universidades'"))
    por={}
    for _,pid,puesto,escala,*_ in filas:
        u=detectar((puesto or '')+' '+(escala or ''),indice)
        if u: por.setdefault(pid,set()).add(u)
    resultado=[]
    for oid,pid,puesto,escala,uid,*actual in filas:
        u=detectar((puesto or '')+' '+(escala or ''),indice); evidencia='UNIVERSIDAD_TEXTO_EXPLICITO' if u else ''
        if not u and len(por.get(pid,set()))==1: u=next(iter(por[pid])); evidencia='UNIVERSIDAD_PROPAGADA_PUBLICACION'
        if not u: continue
        codigo=con.execute("SELECT municipio_codigo_ine FROM universidades WHERE universidad_id=?",(ids[u],)).fetchone()[0]
        if codigo:
            m=con.execute("SELECT nombre,provincia_id,comunidad_id FROM municipios WHERE codigo_ine=?",(codigo,)).fetchone(); p=con.execute("SELECT nombre FROM provincias WHERE provincia_id=?",(m[1],)).fetchone()[0]; ca=con.execute("SELECT nombre FROM comunidades_autonomas WHERE comunidad_id=?",(m[2],)).fetchone()[0]
            nuevo=(ids[u],'UNIVERSITARIO','UNIVERSIDAD',m[0],codigo,p,m[1],ca,m[2],'ALTA',evidencia)
        else: nuevo=(ids[u],'UNIVERSITARIO','UNIVERSIDAD',None,None,None,None,None,None,'ALTA',evidencia)
        nombres=('universidad_id','ambito','tipo_entidad','municipio','municipio_codigo_ine','provincia','provincia_id','comunidad_autonoma','comunidad_id','confianza_geografica','evidencia_geografica')
        cambios={n:v for n,v,a in zip(nombres,nuevo,(uid,*actual)) if v != a}
        if cambios: resultado.append((oid,cambios,evidencia))
    return resultado
def propuestas(con):
    resultado=[]
    es_v5 = "municipio_codigo_ine" in {x[1] for x in con.execute("PRAGMA table_info(oposiciones)")}
    for oid,admin,puesto,*actual in con.execute("SELECT oposicion_id,administracion,puesto,"+",".join(CAMPOS)+" FROM oposiciones"):
        if es_v5 and admin == "Universidades" and "universidades" in {x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
            continue
        r=resolver_administracion_geografia(admin,puesto)
        # La ausencia de evidencia nueva nunca borra una ubicación histórica.
        municipio = r.municipio or actual[3]
        provincia = r.provincia or actual[4]
        comunidad = r.comunidad_autonoma or actual[5]
        if es_v5:
            _, provincia, comunidad, _, _ = normalizar_referencias_administrativas(
                con, municipio, provincia, comunidad,
            )
        geo = (municipio, provincia, comunidad)
        valores=(r.administracion_normalizada,r.ambito,r.tipo_entidad,*geo,r.confianza,r.evidencia,r.version_catalogo)
        cambios={c:v for c,v,a in zip(CAMPOS,valores,actual) if v != a}
        if cambios: resultado.append((oid,cambios,r))
    return resultado
def recalcular(ruta_bd="datos/boe.db",directorio_backup="backups/sqlite",dry_run=False):
    ruta=Path(ruta_bd); con=base_datos.conectar(ruta,readonly=True)
    try:
        meta=dict(con.execute("SELECT clave,valor FROM metadata"))
        if meta.get("schema_version") not in {"4", "5"}: raise RuntimeError("El recálculo requiere schema_version 4 o 5")
        cambios=propuestas(con)
        universitarios=propuestas_universidades(con) if meta.get("schema_version") == "5" and "universidades" in {x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")} else []
        cambios += universitarios
        enlaces = relaciones_territoriales_seguras_pendientes(con) if meta.get("schema_version") == "5" else []
    finally: con.close()
    resumen={"dry_run":dry_run,"filas_cambiadas":len(cambios),"por_campo":dict(Counter(c for _,x,_ in cambios for c in x)),"por_confianza":dict(Counter(getattr(r,'confianza','ALTA') for _,_,r in cambios)),"por_evidencia":dict(Counter(getattr(r,'evidencia',r) for _,_,r in cambios)),"conflictos":sum(getattr(r,'confianza','')=="AMBIGUA" for _,_,r in cambios),"relaciones_territorios_nuevas":len(enlaces),"universidades_directas":sum(r=='UNIVERSIDAD_TEXTO_EXPLICITO' for _,_,r in universitarios),"universidades_propagadas":sum(r=='UNIVERSIDAD_PROPAGADA_PUBLICACION' for _,_,r in universitarios)}
    if dry_run or not (cambios or enlaces): return {**resumen,"backup":None,"data_version":meta["data_version"]}
    backup=base_datos.crear_backup(ruta,directorio_backup); con=base_datos.conectar(ruta)
    try:
        with base_datos.transaccion(con):
            for oid,cam,_ in cambios:
                con.execute("UPDATE oposiciones SET "+",".join(f"{c}=?" for c in cam)+" WHERE oposicion_id=?",(*cam.values(),oid))
            if meta.get("schema_version") == "5":
                for oid,admin,puesto,mun,prov,com in con.execute("SELECT oposicion_id,administracion,puesto,municipio,provincia,comunidad_autonoma FROM oposiciones"):
                    refs=normalizar_referencias_administrativas(con,mun,prov,com)
                    codigo, provincia, comunidad, provincia_id, comunidad_id = refs
                    con.execute("""UPDATE oposiciones SET municipio_codigo_ine=?,provincia=?,comunidad_autonoma=?,
                                   provincia_id=?,comunidad_id=? WHERE oposicion_id=?""",
                                (codigo,provincia,comunidad,provincia_id,comunidad_id,oid))
                con.executemany("INSERT OR IGNORE INTO oposiciones_territorios_insulares VALUES (?,?,?,?)", enlaces)
            base_datos.guardar_metadata(con,data_version=int(meta["data_version"])+1)
            if base_datos.integrity_check(con)!=["ok"] or base_datos.foreign_key_check(con): raise RuntimeError("Falla integridad")
    finally: con.close()
    return {**resumen,"backup":str(backup),"data_version":str(int(meta["data_version"])+1)}
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--base-datos",default="datos/boe.db");p.add_argument("--directorio-backup",default="backups/sqlite");p.add_argument("--dry-run",action="store_true");a=p.parse_args(argv);print(json.dumps(recalcular(a.base_datos,a.directorio_backup,a.dry_run),ensure_ascii=False,indent=2))
if __name__=="__main__": main()
