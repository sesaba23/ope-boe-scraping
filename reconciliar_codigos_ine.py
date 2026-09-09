"""Reconciliación conservadora de municipios ya identificables con alta confianza.

Sólo enlaza ``municipio_codigo_ine`` nulo cuando la auditoría encuentra un
municipio maestro único y compatible. No modifica textos geográficos ni usa
coordenadas legacy, sedes o inferencias administrativas.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time

import base_datos
from analizar_sin_coordenadas import (
    auditar,
    cargar_catalogos,
    cargar_registros_sin_codigo_ine,
    clasificar_registro,
)


CATEGORIAS_PERMITIDAS = {
    "coincidencia_exacta_unica",
    "coincidencia_casefold_unica",
    "coincidencia_normalizada_unica",
    "resoluble_con_provincia",
}


def _hash(ruta):
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def _metadata(con):
    return dict(con.execute("SELECT clave, valor FROM metadata"))


def seleccionar_candidatos(con):
    """Recalcula candidatos desde catálogo y datos actuales; no acepta listas externas."""
    catalogos = cargar_catalogos(con)
    candidatos = []
    excluidos = []
    for fila in cargar_registros_sin_codigo_ine(con):
        resultado = clasificar_registro(fila, catalogos)
        categoria = resultado["categoria"]
        codigo = resultado.get("codigo_ine_candidato")
        maestro = catalogos["por_codigo"].get(codigo) if codigo else None
        permitido = (
            resultado["confianza"] == "ALTA"
            and categoria in CATEGORIAS_PERMITIDAS
            and maestro is not None
            and maestro["latitud"] is not None
            and maestro["longitud"] is not None
        )
        detalle = {
            "oposicion_id": fila["oposicion_id"], "municipio_original": fila["municipio"],
            "provincia_original": fila["provincia"], "comunidad_original": fila["comunidad_autonoma"],
            "codigo_ine_candidato": codigo, "municipio_maestro": resultado.get("municipio_maestro_candidato"),
            "regla": categoria, "confianza": resultado["confianza"],
        }
        if permitido:
            candidatos.append(detalle)
        elif categoria in CATEGORIAS_PERMITIDAS and resultado["confianza"] == "ALTA":
            excluidos.append({**detalle, "motivo": "maestro sin coordenadas o inexistente"})
    return candidatos, excluidos


def _comprobar_esperados(candidatos, esperados):
    if esperados is not None and len(candidatos) != esperados:
        raise RuntimeError(
            f"Deriva de reconciliación: se esperaban {esperados} candidatos y se encontraron {len(candidatos)}"
        )


def reconciliar(ruta_bd="datos/boe.db", *, directorio_backup="backups/sqlite/reconciliacion_geografica",
                dry_run=False, esperados=75):
    """Simula o persiste una reconciliación atómica; devuelve trazabilidad completa."""
    ruta = Path(ruta_bd)
    inicio = time.perf_counter()
    sha_antes = _hash(ruta)
    lectura = base_datos.conectar(ruta, readonly=True)
    try:
        metadata_antes = _metadata(lectura)
        if metadata_antes.get("schema_version") != "6":
            raise RuntimeError("La reconciliación requiere schema_version 6")
        candidatos, omitidos = seleccionar_candidatos(lectura)
    finally:
        lectura.close()
    _comprobar_esperados(candidatos, esperados)
    resultado = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(), "dry_run": dry_run,
        "schema_version_antes": metadata_antes["schema_version"], "data_version_antes": metadata_antes["data_version"],
        "sha256_antes": sha_antes, "candidatos": candidatos, "numero_candidatos": len(candidatos),
        "numero_omitidos": len(omitidos), "omitidos": omitidos,
        "campos_modificados": ["municipio_codigo_ine"], "backup": None,
    }
    if dry_run:
        resultado.update(schema_version_despues=metadata_antes["schema_version"], data_version_despues=metadata_antes["data_version"], sha256_despues=_hash(ruta), actualizados=0, rendimiento_segundos=round(time.perf_counter()-inicio, 3))
        return resultado

    backup = base_datos.crear_backup(ruta, directorio_backup)
    escritura = base_datos.conectar(ruta)
    try:
        with base_datos.transaccion(escritura):
            for candidato in candidatos:
                cursor = escritura.execute(
                    "UPDATE oposiciones SET municipio_codigo_ine=? WHERE oposicion_id=? AND municipio_codigo_ine IS NULL",
                    (candidato["codigo_ine_candidato"], candidato["oposicion_id"]),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(f"Deriva durante escritura en oposición {candidato['oposicion_id']}")
            base_datos.guardar_metadata(
                escritura, data_version=int(metadata_antes["data_version"]) + 1,
                schema_version=metadata_antes["schema_version"],
            )
            if base_datos.integrity_check(escritura) != ["ok"] or base_datos.foreign_key_check(escritura):
                raise RuntimeError("La reconciliación no supera integridad o claves foráneas")
    finally:
        escritura.close()
    verificacion = base_datos.conectar(ruta, readonly=True)
    try:
        metadata_despues = _metadata(verificacion)
        ids = [x["oposicion_id"] for x in candidatos]
        marcas = ",".join("?" for _ in ids)
        enlazados = verificacion.execute(f"""
            SELECT COUNT(*) FROM oposiciones AS o JOIN municipios AS m ON m.codigo_ine=o.municipio_codigo_ine
             WHERE o.oposicion_id IN ({marcas}) AND m.latitud IS NOT NULL AND m.longitud IS NOT NULL
        """, ids).fetchone()[0] if ids else 0
        integridad = base_datos.integrity_check(verificacion)
        fk = base_datos.foreign_key_check(verificacion)
    finally:
        verificacion.close()
    resultado.update(
        backup=str(backup), actualizados=len(candidatos), enlazados_con_coordenadas=enlazados,
        schema_version_despues=metadata_despues["schema_version"], data_version_despues=metadata_despues["data_version"],
        sha256_despues=_hash(ruta), integrity_check=integridad, foreign_key_check=fk,
        rendimiento_segundos=round(time.perf_counter()-inicio, 3),
    )
    return resultado


def _guardar_json(ruta, contenido):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(contenido, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-datos", default="datos/boe.db")
    parser.add_argument("--directorio-backup", default="backups/sqlite/reconciliacion_geografica")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--esperados", type=int, default=75)
    parser.add_argument("--informe", default="informes/reconciliacion_geografica_alta_confianza.json")
    parser.add_argument("--informe-post", default="informes/sin_coordenadas_post_reconciliacion.json")
    args = parser.parse_args(argv)
    resultado = reconciliar(args.base_datos, directorio_backup=args.directorio_backup,
                            dry_run=args.dry_run, esperados=args.esperados)
    _guardar_json(args.informe, resultado)
    if not args.dry_run:
        _guardar_json(args.informe_post, auditar(args.base_datos))
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
