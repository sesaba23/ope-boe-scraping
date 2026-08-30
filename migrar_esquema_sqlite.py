"""Migra explícitamente una base BOE de schema_version 2 a 3."""

import argparse
import json
from pathlib import Path
import time

import base_datos
from normalizacion_puestos import normalizar_puesto
from resolucion_geografica import resolver_administracion_geografia


def _estado(ruta_bd):
    conexion = base_datos.conectar(ruta_bd, readonly=True)
    try:
        metadata = dict(conexion.execute("SELECT clave, valor FROM metadata"))
        columnas = [fila[1] for fila in conexion.execute("PRAGMA table_info(oposiciones)")]
        return metadata, columnas
    finally:
        conexion.close()


def migrar_v2_v3(ruta_bd="datos/boe.db", directorio_backup="backups/sqlite"):
    ruta_bd = Path(ruta_bd)
    if not ruta_bd.is_file():
        raise FileNotFoundError(f"No existe la base SQLite: {ruta_bd}")
    metadata, columnas = _estado(ruta_bd)
    if metadata.get("schema_version") == "3":
        if "puesto_normalizado" not in columnas:
            raise RuntimeError("Metadata v3 sin columna puesto_normalizado")
        return {"actualizada": False, "schema_version": "3", "data_version": metadata["data_version"]}
    if metadata.get("schema_version") != "2" or "puesto_normalizado" in columnas:
        raise RuntimeError("La base no es un esquema v2 migrable")

    backup = base_datos.crear_backup(ruta_bd, directorio_backup)
    inicio = time.perf_counter()
    conexion = base_datos.conectar(ruta_bd)
    try:
        version_anterior = int(metadata["data_version"])
        with base_datos.transaccion(conexion):
            conexion.execute(
                "ALTER TABLE oposiciones ADD COLUMN puesto_normalizado TEXT"
            )
            filas = conexion.execute(
                "SELECT oposicion_id, puesto FROM oposiciones"
            ).fetchall()
            conexion.executemany(
                "UPDATE oposiciones SET puesto_normalizado=? WHERE oposicion_id=?",
                ((normalizar_puesto(puesto), oposicion_id) for oposicion_id, puesto in filas),
            )
            # La migración histórica conserva semántica v3 aunque el código
            # actual ya sepa crear v4.
            base_datos.guardar_metadata(conexion, data_version=version_anterior + 1)
            conexion.execute("UPDATE metadata SET valor='3' WHERE clave='schema_version'")
            if base_datos.integrity_check(conexion) != ["ok"]:
                raise RuntimeError("La base migrada no supera integrity_check")
            if base_datos.foreign_key_check(conexion):
                raise RuntimeError("La base migrada no supera foreign_key_check")
            sin_normalizar = conexion.execute(
                """SELECT count(*) FROM oposiciones
                   WHERE puesto IS NOT NULL AND trim(puesto)<>''
                     AND puesto_normalizado IS NULL"""
            ).fetchone()[0]
            if sin_normalizar:
                raise RuntimeError(f"Quedan {sin_normalizar} puestos sin normalizar")
    except Exception:
        conexion.close()
        raise
    else:
        conexion.close()

    verificacion = base_datos.conectar(ruta_bd, readonly=True)
    try:
        metadata_final = dict(verificacion.execute("SELECT clave, valor FROM metadata"))
        auditoria = {
            "integrity_check": base_datos.integrity_check(verificacion),
            "foreign_key_check": base_datos.foreign_key_check(verificacion),
            "filas": verificacion.execute("SELECT count(*) FROM oposiciones").fetchone()[0],
            "puestos_distintos": verificacion.execute("SELECT count(DISTINCT puesto) FROM oposiciones").fetchone()[0],
            "normalizados_distintos": verificacion.execute("SELECT count(DISTINCT puesto_normalizado) FROM oposiciones").fetchone()[0],
            "filas_cambiadas_logicamente": verificacion.execute("SELECT count(*) FROM oposiciones WHERE puesto_normalizado<>puesto").fetchone()[0],
        }
    finally:
        verificacion.close()
    return {
        "actualizada": True,
        "backup": str(backup),
        "schema_version": metadata_final["schema_version"],
        "data_version": metadata_final["data_version"],
        "segundos": time.perf_counter() - inicio,
        "auditoria": auditoria,
    }


def migrar_v3_v4(ruta_bd="datos/boe.db", directorio_backup="backups/sqlite"):
    """Añade dimensiones geográficas sin sobrescribir los textos históricos."""
    ruta_bd = Path(ruta_bd)
    metadata, columnas = _estado(ruta_bd)
    nuevas = ("administracion_normalizada", "ambito", "tipo_entidad", "comunidad_autonoma",
              "confianza_geografica", "evidencia_geografica", "version_resolutor")
    if metadata.get("schema_version") == "4":
        if not set(nuevas) <= set(columnas): raise RuntimeError("Metadata v4 sin columnas geográficas")
        return {"actualizada": False, "schema_version": "4", "data_version": metadata["data_version"]}
    if metadata.get("schema_version") != "3" or any(x in columnas for x in nuevas):
        raise RuntimeError("La base no es un esquema v3 migrable a v4")
    backup = base_datos.crear_backup(ruta_bd, directorio_backup); inicio=time.perf_counter()
    con=base_datos.conectar(ruta_bd)
    try:
        with base_datos.transaccion(con):
            for columna in nuevas: con.execute(f"ALTER TABLE oposiciones ADD COLUMN {columna} TEXT")
            filas=con.execute("SELECT oposicion_id,administracion,puesto FROM oposiciones").fetchall()
            con.executemany("""UPDATE oposiciones SET administracion_normalizada=?,ambito=?,tipo_entidad=?,municipio=COALESCE(?,municipio),provincia=COALESCE(?,provincia),comunidad_autonoma=?,confianza_geografica=?,evidencia_geografica=?,version_resolutor=? WHERE oposicion_id=?""",
                ((r.administracion_normalizada,r.ambito,r.tipo_entidad,r.municipio or None,r.provincia or None,r.comunidad_autonoma or None,r.confianza,r.evidencia,r.version_catalogo,oid)
                 for oid,admin,puesto in filas for r in (resolver_administracion_geografia(admin,puesto),)))
            base_datos.guardar_metadata(con,data_version=int(metadata["data_version"])+1)
            if base_datos.integrity_check(con) != ["ok"] or base_datos.foreign_key_check(con): raise RuntimeError("La base migrada no supera integridad")
    finally: con.close()
    return {"actualizada":True,"backup":str(backup),"schema_version":"4","data_version":str(int(metadata["data_version"])+1),"segundos":time.perf_counter()-inicio}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-datos", default="datos/boe.db")
    parser.add_argument("--directorio-backup", default="backups/sqlite")
    args = parser.parse_args(argv)
    print(json.dumps(
        migrar_v3_v4(args.base_datos, args.directorio_backup) if _estado(args.base_datos)[0].get("schema_version") == "3" else migrar_v2_v3(args.base_datos, args.directorio_backup),
        ensure_ascii=False, indent=2,
    ))


if __name__ == "__main__":
    main()
