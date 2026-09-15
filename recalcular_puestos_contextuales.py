"""Aplica de forma transaccional la normalización contextual ya validada."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import base_datos
from normalizacion_contextual_puestos import normalizar_puesto_efectivo


def _leer(ruta_bd):
    con = base_datos.conectar(ruta_bd, readonly=True)
    try:
        metadata = base_datos.leer_metadata(con)
        filas = con.execute("SELECT * FROM oposiciones ORDER BY oposicion_id").fetchall()
        return metadata, filas
    finally:
        con.close()


def _resultado(fila):
    return normalizar_puesto_efectivo(
        fila[2], administracion=fila[3], ambito=fila[23], tipo_entidad=fila[24],
        escala=fila[4], subescala=fila[5], sistema=fila[7], municipio=fila[13], provincia=fila[14],
    )


def _plan(filas):
    cambios = []
    for fila in filas:
        resultado = _resultado(fila)
        actual = fila[21]
        if resultado.regla and resultado.normalizado != actual:
            cambios.append({"oposicion_id": fila[0], "puesto": fila[2], "anterior": actual, "nuevo": resultado.normalizado, "regla": resultado.regla, "confianza": resultado.confianza, "evidencia": resultado.evidencia, "plazas": fila[1], "administracion": fila[3], "ambito": fila[23], "tipo_entidad": fila[24], "municipio": fila[13], "provincia": fila[14], "escala": fila[4], "subescala": fila[5], "sistema": fila[7]})
    por_regla = Counter(c["regla"] for c in cambios); por_canon = Counter(c["nuevo"] for c in cambios)
    return cambios, {"filas_examinadas": len(filas), "filas_que_cambiarian": len(cambios), "plazas_afectadas": sum(c["plazas"] or 0 for c in cambios), "por_regla": dict(por_regla), "por_canon": dict(por_canon)}


def recalcular(ruta_bd="datos/boe.db", directorio_backup="backups/sqlite", *, dry_run=False, esperadas=329):
    ruta = Path(ruta_bd); metadata, filas = _leer(ruta); cambios, informe = _plan(filas)
    informe.update({"dry_run": dry_run, "actualizada": False, "backup": None, "data_version_antes": metadata["data_version"], "data_version_despues": metadata["data_version"], "schema_version": metadata["schema_version"], "propuestas": cambios})
    if len(cambios) != esperadas:
        raise RuntimeError(f"El recálculo contextual esperaba {esperadas} cambios y obtuvo {len(cambios)}")
    if dry_run:
        return informe
    backup = base_datos.crear_backup(ruta, directorio_backup)
    con = base_datos.conectar(ruta)
    try:
        with base_datos.transaccion(con):
            if base_datos.leer_metadata(con) != metadata:
                raise RuntimeError("La base cambió durante la preparación del recálculo contextual")
            con.executemany("UPDATE oposiciones SET puesto_normalizado=? WHERE oposicion_id=?", ((c["nuevo"], c["oposicion_id"]) for c in cambios))
            base_datos.guardar_metadata(con, data_version=int(metadata["data_version"]) + 1)
            if base_datos.integrity_check(con) != ["ok"] or base_datos.foreign_key_check(con):
                raise RuntimeError("Las invariantes SQLite fallaron antes de COMMIT")
    finally:
        con.close()
    informe.update({"actualizada": True, "backup": str(backup), "data_version_despues": str(int(metadata["data_version"]) + 1)})
    return informe


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--base-datos", default="datos/boe.db"); p.add_argument("--directorio-backup", default="backups/sqlite"); p.add_argument("--dry-run", action="store_true"); p.add_argument("--esperadas", type=int, default=329)
    a = p.parse_args(argv); print(json.dumps(recalcular(a.base_datos, a.directorio_backup, dry_run=a.dry_run, esperadas=a.esperadas), ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
