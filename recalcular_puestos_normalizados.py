"""Recalcula explícitamente Puesto_normalizado en una base SQLite v3."""

import argparse
from collections import Counter
import json
from pathlib import Path

import base_datos
from normalizacion_puestos import normalizar_puesto


def _leer(ruta_bd):
    conexion = base_datos.conectar(ruta_bd, readonly=True)
    try:
        metadata = dict(conexion.execute("SELECT clave,valor FROM metadata"))
        columnas = {fila[1].casefold() for fila in conexion.execute("PRAGMA table_info(oposiciones)")}
        if metadata.get("schema_version") not in {"3", "4"} or "puesto_normalizado" not in columnas:
            raise RuntimeError("El recálculo requiere schema_version 3 o 4 con Puesto_normalizado")
        filas = conexion.execute(
            "SELECT oposicion_id,puesto,puesto_normalizado FROM oposiciones ORDER BY oposicion_id"
        ).fetchall()
        return metadata, filas
    finally:
        conexion.close()


def _plan(filas):
    cambios = []
    antes = Counter()
    despues = Counter()
    for oposicion_id, puesto, actual in filas:
        nuevo = normalizar_puesto(puesto)
        antes[actual] += 1
        despues[nuevo] += 1
        if nuevo != actual:
            cambios.append((nuevo, oposicion_id, puesto, actual))
    frecuencia = Counter(nuevo for nuevo, _, _, _ in cambios)
    return cambios, {
        "filas_examinadas": len(filas),
        "filas_que_cambiarian": len(cambios),
        "canones_afectados": sorted(frecuencia),
        "grupos_fusionados": len(antes) - len(despues),
        "distintos_antes": len(antes),
        "distintos_despues": len(despues),
        "top_cambios": [
            {"canon": canon, "filas": cantidad}
            for canon, cantidad in frecuencia.most_common(20)
        ],
    }


def recalcular(ruta_bd="datos/boe.db", directorio_backup="backups/sqlite", *, dry_run=False):
    ruta_bd = Path(ruta_bd)
    if not ruta_bd.is_file():
        raise FileNotFoundError(f"No existe la base SQLite: {ruta_bd}")
    metadata, filas = _leer(ruta_bd)
    cambios, informe = _plan(filas)
    informe.update({
        "dry_run": dry_run, "actualizada": False, "backup": None,
        "schema_version": metadata["schema_version"],
        "data_version_antes": metadata["data_version"],
        "data_version_despues": metadata["data_version"],
    })
    if dry_run or not cambios:
        return informe

    backup = base_datos.crear_backup(ruta_bd, directorio_backup)
    conexion = base_datos.conectar(ruta_bd)
    try:
        with base_datos.transaccion(conexion):
            # La validación se repite bajo el bloqueo de escritura para evitar
            # aplicar un plan calculado sobre un estado concurrentemente distinto.
            metadata_bloqueada = dict(conexion.execute("SELECT clave,valor FROM metadata"))
            if metadata_bloqueada != metadata:
                raise RuntimeError("La base cambió durante la preparación del recálculo")
            conexion.executemany(
                "UPDATE oposiciones SET puesto_normalizado=? WHERE oposicion_id=?",
                ((nuevo, oposicion_id) for nuevo, oposicion_id, _, _ in cambios),
            )
            version_nueva = int(metadata["data_version"]) + 1
            base_datos.guardar_metadata(conexion, data_version=version_nueva)
            if base_datos.integrity_check(conexion) != ["ok"]:
                raise RuntimeError("La base recalculada no supera integrity_check")
            if base_datos.foreign_key_check(conexion):
                raise RuntimeError("La base recalculada no supera foreign_key_check")
    finally:
        conexion.close()

    informe.update({
        "actualizada": True, "backup": str(backup),
        "data_version_despues": str(int(metadata["data_version"]) + 1),
    })
    return informe


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-datos", default="datos/boe.db")
    parser.add_argument("--directorio-backup", default="backups/sqlite")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(recalcular(
        args.base_datos, args.directorio_backup, dry_run=args.dry_run
    ), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
