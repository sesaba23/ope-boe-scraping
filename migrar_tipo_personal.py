"""Migración y recálculo manual de ``tipo_personal`` en SQLite.

No forma parte del flujo de descarga/importación. La clasificación sólo se
ejecuta al invocar explícitamente esta utilidad.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

import base_datos
from tipo_personal import CATEGORIAS, VERSION, clasificar_tipo_personal


SCHEMA_ORIGEN = "6"
SCHEMA_DESTINO = "7"
METADATA_VERSION = "tipo_personal_version"
CATALOGO = frozenset(CATEGORIAS)
RECUENTOS_ESPERADOS = {
    "Funcionario": 55961,
    "Laboral": 18216,
    "Estatutario": 1,
    "Universitario": 2900,
    "Militar": 1,
    "Otros": 1,
    "No determinado": 32349,
}


def _columnas(conexion: sqlite3.Connection, tabla: str) -> list[str]:
    return [fila[1] for fila in conexion.execute(f'PRAGMA table_info("{tabla}")')]


def _serializar(valor):
    if isinstance(valor, bytes):
        return {"bytes_sha256": hashlib.sha256(valor).hexdigest(), "longitud": len(valor)}
    return valor


def fingerprint_invariantes(conexion: sqlite3.Connection) -> dict[str, object]:
    """Huella todas las tablas salvo cambios permitidos de esta migración."""
    resultado = {}
    tablas = [fila[0] for fila in conexion.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]
    for tabla in tablas:
        if tabla == "metadata":
            continue
        columnas = _columnas(conexion, tabla)
        if tabla == "oposiciones":
            columnas = [columna for columna in columnas if columna != "tipo_personal"]
        seleccion = ",".join(f'"{columna}"' for columna in columnas)
        orden = "oposicion_id" if tabla == "oposiciones" else "rowid"
        digest = hashlib.sha256()
        cantidad = 0
        for fila in conexion.execute(f'SELECT {seleccion} FROM "{tabla}" ORDER BY {orden}'):
            digest.update((json.dumps(
                [_serializar(valor) for valor in fila], ensure_ascii=False,
                separators=(",", ":"), sort_keys=True,
            ) + "\n").encode())
            cantidad += 1
        resultado[tabla] = {"filas": cantidad, "sha256": digest.hexdigest()}
    global_digest = hashlib.sha256(json.dumps(
        resultado, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    return {"sha256": global_digest, "tablas": resultado}


def generar_plan(ruta_bd: str | Path) -> dict[str, object]:
    """Clasifica toda la base en sólo lectura y valida la cobertura del plan."""
    ruta = Path(ruta_bd)
    conexion = base_datos.conectar(ruta, readonly=True)
    conexion.row_factory = sqlite3.Row
    try:
        metadata = base_datos.leer_metadata(conexion)
        publicaciones = {
            fila["publicacion_id"]: dict(fila)
            for fila in conexion.execute("SELECT * FROM publicaciones")
        }
        resultados = []
        vistos = set()
        recuentos = Counter()
        digest = hashlib.sha256()
        for fila_sql in conexion.execute("SELECT * FROM oposiciones ORDER BY oposicion_id"):
            fila = dict(fila_sql)
            oposicion_id = fila["oposicion_id"]
            if oposicion_id in vistos:
                raise RuntimeError(f"oposicion_id duplicado: {oposicion_id}")
            vistos.add(oposicion_id)
            resultado = clasificar_tipo_personal(fila, publicaciones.get(fila["publicacion_id"]))
            if resultado["categoria"] not in CATALOGO:
                raise RuntimeError(f"Categoría fuera de catálogo: {resultado['categoria']!r}")
            registro = {
                "oposicion_id": oposicion_id,
                "tipo_personal": resultado["categoria"],
                "confianza": resultado["confianza"],
                "reglas_aplicadas": resultado["reglas_aplicadas"],
                "familias_detectadas": resultado["familias_detectadas"],
                "grupos_evidencia": resultado["grupos_evidencia"],
                "version": resultado["version"],
            }
            resultados.append(registro)
            recuentos[resultado["categoria"]] += 1
            digest.update((json.dumps(
                registro, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ) + "\n").encode())
        total_bd = conexion.execute("SELECT count(*) FROM oposiciones").fetchone()[0]
        ids_bd = {fila[0] for fila in conexion.execute("SELECT oposicion_id FROM oposiciones")}
        if len(resultados) != total_bd or vistos != ids_bd:
            raise RuntimeError("El plan no cubre exactamente todas las oposiciones")
        if set(recuentos) - CATALOGO or sum(recuentos.values()) != total_bd:
            raise RuntimeError("Distribución inválida en el dry-run")
        return {
            "metadata": metadata,
            "total": total_bd,
            "recuentos": {categoria: recuentos[categoria] for categoria in CATEGORIAS},
            "sha256": digest.hexdigest(),
            "resultados": resultados,
        }
    finally:
        conexion.close()


def validar_dry_run_doble(ruta_bd: str | Path, *, recuentos_esperados=None) -> dict[str, object]:
    primero = generar_plan(ruta_bd)
    segundo = generar_plan(ruta_bd)
    if primero["sha256"] != segundo["sha256"] or primero["resultados"] != segundo["resultados"]:
        raise RuntimeError("El clasificador no es determinista")
    esperados = recuentos_esperados
    if esperados is None and primero["total"] == sum(RECUENTOS_ESPERADOS.values()):
        esperados = RECUENTOS_ESPERADOS
    if esperados is not None and primero["recuentos"] != {
        categoria: esperados.get(categoria, 0) for categoria in CATEGORIAS
    }:
        raise RuntimeError("La distribución del dry-run no coincide con el baseline aprobado")
    return primero


def escribir_informe(plan: dict[str, object], directorio: str | Path) -> dict[str, str]:
    destino = Path(directorio)
    destino.mkdir(parents=True, exist_ok=True)
    csv_path = destino / "tipo_personal_v1_detalle.csv"
    json_path = destino / "tipo_personal_v1_resumen.json"
    campos = (
        "oposicion_id", "tipo_personal", "confianza", "reglas_aplicadas",
        "familias_detectadas", "grupos_evidencia", "version",
    )
    with csv_path.open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=campos)
        escritor.writeheader()
        for fila in plan["resultados"]:
            escritor.writerow({
                **fila,
                "reglas_aplicadas": json.dumps(fila["reglas_aplicadas"], ensure_ascii=False),
                "familias_detectadas": json.dumps(fila["familias_detectadas"], ensure_ascii=False),
                "grupos_evidencia": json.dumps(fila["grupos_evidencia"], ensure_ascii=False),
            })
    resumen = {
        "modo": "dry-run reproducible",
        "total": plan["total"],
        "recuentos": plan["recuentos"],
        "sha256_resultado": plan["sha256"],
        "version": VERSION,
    }
    json_path.write_text(json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"detalle": str(csv_path), "resumen": str(json_path)}


def _validar_persistencia(conexion, plan):
    total, no_nulos = conexion.execute(
        "SELECT count(*),count(tipo_personal) FROM oposiciones"
    ).fetchone()
    distribucion = dict(conexion.execute(
        "SELECT tipo_personal,count(*) FROM oposiciones GROUP BY tipo_personal"
    ))
    esperada = {categoria: cantidad for categoria, cantidad in plan["recuentos"].items() if cantidad}
    if total != plan["total"] or no_nulos != total or distribucion != esperada:
        raise RuntimeError("La persistencia no coincide exactamente con el dry-run")
    if set(distribucion) - CATALOGO:
        raise RuntimeError("La persistencia contiene categorías fuera de catálogo")
    metadata = base_datos.leer_metadata(conexion)
    if metadata.get("schema_version") != SCHEMA_DESTINO:
        raise RuntimeError("schema_version no alcanzó la versión 7")
    if metadata.get(METADATA_VERSION) != VERSION:
        raise RuntimeError("Falta la versión del clasificador en metadata")


def _persistir_plan(conexion, plan):
    conexion.executemany(
        "UPDATE oposiciones SET tipo_personal=? WHERE oposicion_id=?",
        ((fila["tipo_personal"], fila["oposicion_id"]) for fila in plan["resultados"]),
    )


def migrar(
    ruta_bd: str | Path = "datos/boe.db",
    directorio_backup: str | Path = "backups/sqlite",
    directorio_informe: str | Path = "backups/tipo_personal",
    *,
    dry_run: bool = False,
) -> dict[str, object]:
    ruta = Path(ruta_bd)
    lectura = base_datos.conectar(ruta, readonly=True)
    try:
        metadata_antes = base_datos.leer_metadata(lectura)
        columnas = _columnas(lectura, "oposiciones")
        invariantes_antes = fingerprint_invariantes(lectura)
    finally:
        lectura.close()
    if metadata_antes.get("schema_version") == SCHEMA_DESTINO:
        if "tipo_personal" not in columnas or metadata_antes.get(METADATA_VERSION) != VERSION:
            raise RuntimeError("Metadata v7 sin estructura/provenance de tipo_personal")
        plan = validar_dry_run_doble(ruta)
        validacion = base_datos.conectar(ruta, readonly=True)
        try:
            _validar_persistencia(validacion, plan)
        finally:
            validacion.close()
        informe = escribir_informe(plan, directorio_informe)
        return {
            "actualizada": False, "dry_run": dry_run, "backup": None,
            "schema_version": SCHEMA_DESTINO, "data_version": metadata_antes["data_version"],
            "recuentos": plan["recuentos"], "sha256_resultado": plan["sha256"],
            "informe": informe,
        }
    if metadata_antes.get("schema_version") != SCHEMA_ORIGEN or "tipo_personal" in columnas:
        raise RuntimeError("La base no es un esquema v6 migrable a tipo_personal v1")

    plan = validar_dry_run_doble(ruta)
    informe = escribir_informe(plan, directorio_informe)
    if dry_run:
        return {
            "actualizada": False, "dry_run": True, "backup": None,
            "schema_version": SCHEMA_ORIGEN, "data_version": metadata_antes["data_version"],
            "recuentos": plan["recuentos"], "sha256_resultado": plan["sha256"],
            "informe": informe, "invariantes": invariantes_antes,
        }

    backup = base_datos.crear_backup(ruta, directorio_backup)
    conexion = base_datos.conectar(ruta)
    try:
        with base_datos.transaccion(conexion):
            if base_datos.leer_metadata(conexion) != metadata_antes:
                raise RuntimeError("La base cambió durante la preparación de la migración")
            if fingerprint_invariantes(conexion) != invariantes_antes:
                raise RuntimeError("Los datos cambiaron durante la preparación de la migración")
            catalogo_sql = ",".join(f"'{categoria}'" for categoria in CATEGORIAS)
            conexion.execute(
                "ALTER TABLE oposiciones ADD COLUMN tipo_personal TEXT NOT NULL "
                f"DEFAULT 'No determinado' CHECK(tipo_personal IN ({catalogo_sql}))"
            )
            _persistir_plan(conexion, plan)
            base_datos.guardar_metadata(
                conexion,
                schema_version=SCHEMA_DESTINO,
                data_version=int(metadata_antes["data_version"]) + 1,
            )
            conexion.execute(
                "INSERT INTO metadata(clave,valor) VALUES (?,?) "
                "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
                (METADATA_VERSION, VERSION),
            )
            _validar_persistencia(conexion, plan)
            if fingerprint_invariantes(conexion) != invariantes_antes:
                raise RuntimeError("La migración alteró datos ajenos a tipo_personal")
            if base_datos.integrity_check(conexion) != ["ok"] or base_datos.foreign_key_check(conexion):
                raise RuntimeError("La base migrada no supera integridad")
    finally:
        conexion.close()

    verificacion = base_datos.conectar(ruta, readonly=True)
    try:
        _validar_persistencia(verificacion, plan)
        invariantes_despues = fingerprint_invariantes(verificacion)
        metadata_despues = base_datos.leer_metadata(verificacion)
    finally:
        verificacion.close()
    return {
        "actualizada": True, "dry_run": False, "backup": str(backup),
        "schema_version": metadata_despues["schema_version"],
        "data_version_antes": metadata_antes["data_version"],
        "data_version_despues": metadata_despues["data_version"],
        "recuentos": plan["recuentos"], "sha256_resultado": plan["sha256"],
        "informe": informe, "invariantes_antes": invariantes_antes,
        "invariantes_despues": invariantes_despues,
    }


def recalcular(ruta_bd: str | Path = "datos/boe.db", *, dry_run: bool = True,
               directorio_backup: str | Path = "backups/sqlite") -> dict[str, object]:
    ruta = Path(ruta_bd)
    plan = validar_dry_run_doble(ruta)
    conexion = base_datos.conectar(ruta, readonly=True)
    try:
        metadata = base_datos.leer_metadata(conexion)
        if metadata.get("schema_version") != SCHEMA_DESTINO or "tipo_personal" not in _columnas(conexion, "oposiciones"):
            raise RuntimeError("El recálculo requiere schema_version 7 con tipo_personal")
        actuales = dict(conexion.execute("SELECT oposicion_id,tipo_personal FROM oposiciones"))
        invariantes_antes = fingerprint_invariantes(conexion)
    finally:
        conexion.close()
    cambios = [fila for fila in plan["resultados"] if actuales.get(fila["oposicion_id"]) != fila["tipo_personal"]]
    resultado = {
        "dry_run": dry_run, "filas_examinadas": plan["total"],
        "filas_que_cambiarian": len(cambios), "cambios": [
            {"oposicion_id": fila["oposicion_id"], "antes": actuales.get(fila["oposicion_id"]),
             "despues": fila["tipo_personal"]} for fila in cambios
        ],
        "sha256_resultado": plan["sha256"], "backup": None,
        "data_version_antes": metadata["data_version"], "data_version_despues": metadata["data_version"],
    }
    if dry_run or not cambios:
        return resultado
    backup = base_datos.crear_backup(ruta, directorio_backup)
    escritura = base_datos.conectar(ruta)
    try:
        with base_datos.transaccion(escritura):
            if base_datos.leer_metadata(escritura) != metadata:
                raise RuntimeError("La base cambió durante la preparación del recálculo")
            escritura.executemany(
                "UPDATE oposiciones SET tipo_personal=? WHERE oposicion_id=?",
                ((fila["tipo_personal"], fila["oposicion_id"]) for fila in cambios),
            )
            base_datos.guardar_metadata(
                escritura, schema_version=SCHEMA_DESTINO,
                data_version=int(metadata["data_version"]) + 1,
            )
            escritura.execute(
                "INSERT INTO metadata(clave,valor) VALUES (?,?) "
                "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
                (METADATA_VERSION, VERSION),
            )
            _validar_persistencia(escritura, plan)
            if fingerprint_invariantes(escritura) != invariantes_antes:
                raise RuntimeError("El recálculo alteró datos ajenos a tipo_personal")
            if base_datos.integrity_check(escritura) != ["ok"] or base_datos.foreign_key_check(escritura):
                raise RuntimeError("La base recalculada no supera integridad")
    finally:
        escritura.close()
    resultado.update(
        dry_run=False, backup=str(backup),
        data_version_despues=str(int(metadata["data_version"]) + 1),
    )
    return resultado


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-datos", default="datos/boe.db")
    parser.add_argument("--directorio-backup", default="backups/sqlite")
    parser.add_argument("--directorio-informe", default="backups/tipo_personal")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--recalcular", action="store_true")
    args = parser.parse_args(argv)
    if args.recalcular:
        resultado = recalcular(
            args.base_datos, dry_run=args.dry_run,
            directorio_backup=args.directorio_backup,
        )
    else:
        resultado = migrar(
            args.base_datos, args.directorio_backup, args.directorio_informe,
            dry_run=args.dry_run,
        )
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
