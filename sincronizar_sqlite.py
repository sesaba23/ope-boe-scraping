"""Snapshots verificables y restauración segura de la base SQLite del BOE."""

import argparse
from contextlib import contextmanager, nullcontext
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import tempfile

import base_datos


FORMAT_VERSION = 1
TABLAS = ("publicaciones", "oposiciones", "busquedas", "cobertura", "log_errores")
IDS_TECNICOS = {"oposicion_id", "error_id"}
CLASIFICACIONES = {
    "IDENTICA", "LOCAL_MAS_RECIENTE", "REMOTA_MAS_RECIENTE",
    "DIVERGENTE", "INCOMPATIBLE", "INVALIDA",
}


class ErrorSincronizacion(RuntimeError):
    pass


def sha256_archivo(ruta):
    return base_datos.hash_archivo(ruta)


def _valor_canonico(valor):
    if isinstance(valor, bytes):
        return {"bytes_hex": valor.hex()}
    if isinstance(valor, float):
        return {"float_hex": valor.hex()}
    return valor


def _columnas_logicas(conexion, tabla):
    columnas = [fila[1] for fila in conexion.execute(f'PRAGMA table_info("{tabla}")')]
    return [columna for columna in columnas if columna not in IDS_TECNICOS]


def fingerprints_logicos(conexion):
    """Calcula huellas independientes del layout y del orden de inserción."""
    huellas = {}
    for tabla in TABLAS:
        columnas = _columnas_logicas(conexion, tabla)
        seleccion = ",".join(f'"{columna}"' for columna in columnas)
        orden = ",".join(f'"{columna}"' for columna in columnas)
        digest = hashlib.sha256()
        for fila in conexion.execute(
            f'SELECT {seleccion} FROM "{tabla}" ORDER BY {orden}'
        ):
            registro = [_valor_canonico(valor) for valor in fila]
            digest.update(
                json.dumps(
                    registro, ensure_ascii=False, separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            )
            digest.update(b"\n")
        huellas[tabla] = digest.hexdigest()
    global_ = hashlib.sha256()
    for tabla in TABLAS:
        global_.update(f"{tabla}:{huellas[tabla]}\n".encode("ascii"))
    return huellas, global_.hexdigest()


def inspeccionar(ruta_bd="datos/boe.db"):
    """Inspecciona una base mediante una conexión SQLite estrictamente read-only."""
    ruta = Path(ruta_bd).expanduser().resolve()
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe la base SQLite: {ruta}")
    try:
        conexion = base_datos.conectar(ruta, readonly=True)
        try:
            tablas = {
                fila[0]
                for fila in conexion.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            faltantes = {"metadata", *TABLAS} - tablas
            if faltantes:
                raise ErrorSincronizacion(
                    f"Esquema incompleto; faltan tablas: {sorted(faltantes)}"
                )
            metadata = dict(conexion.execute("SELECT clave, valor FROM metadata"))
            conteos = {
                tabla: conexion.execute(f'SELECT count(*) FROM "{tabla}"').fetchone()[0]
                for tabla in TABLAS
            }
            integridad = base_datos.integrity_check(conexion)
            claves_foraneas = base_datos.foreign_key_check(conexion)
            huellas, global_ = fingerprints_logicos(conexion)
        finally:
            conexion.close()
    except (sqlite3.DatabaseError, sqlite3.OperationalError) as error:
        raise ErrorSincronizacion(f"Base SQLite inválida: {error}") from error
    stat = ruta.stat()
    return {
        "ruta": str(ruta),
        "nombre_bd": ruta.name,
        "tamano": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256_fisico": sha256_archivo(ruta),
        "schema_version": metadata.get("schema_version"),
        "data_version": metadata.get("data_version"),
        "created_at": metadata.get("created_at"),
        "updated_at": metadata.get("updated_at"),
        "migrated_at": metadata.get("migrated_at"),
        "metadata": metadata,
        "conteos": conteos,
        "fingerprints": huellas,
        "fingerprint_global": global_,
        "integrity_check": integridad,
        "foreign_key_check": claves_foraneas,
    }


def _contenido_firmado(manifiesto):
    return {clave: valor for clave, valor in manifiesto.items() if clave != "manifest_sha256"}


def _firma_manifiesto(manifiesto):
    bruto = json.dumps(
        _contenido_firmado(manifiesto), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(bruto).hexdigest()


def _ruta_manifiesto(ruta_bd):
    return Path(ruta_bd).with_suffix(".json")


def _ruta_procedencia(ruta_bd):
    ruta = Path(ruta_bd)
    return ruta.with_name(ruta.name + ".sync.json")


def _leer_json(ruta):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ErrorSincronizacion(f"JSON inválido: {ruta}: {error}") from error


def _ascendencia_origen(ruta_bd, fingerprint_actual):
    ruta = _ruta_procedencia(ruta_bd)
    if not ruta.is_file():
        return []
    datos = _leer_json(ruta)
    if datos.get("format_version") != FORMAT_VERSION:
        return []
    padre = datos.get("fingerprint_restaurado")
    ancestros = datos.get("ancestros", [])
    if not padre or padre == fingerprint_actual:
        return list(dict.fromkeys(ancestros))
    return list(dict.fromkeys([*ancestros, padre]))


def crear_manifiesto(ruta_snapshot, inspeccion, ancestros=()):
    manifiesto = {
        "format_version": FORMAT_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "hostname": socket.gethostname(),
        "nombre_bd": Path(ruta_snapshot).name,
        "tamano": inspeccion["tamano"],
        "sha256_fisico": inspeccion["sha256_fisico"],
        "schema_version": inspeccion["schema_version"],
        "data_version": inspeccion["data_version"],
        "metadata": inspeccion["metadata"],
        "conteos": inspeccion["conteos"],
        "fingerprints": inspeccion["fingerprints"],
        "fingerprint_global": inspeccion["fingerprint_global"],
        "ancestros": list(dict.fromkeys(ancestros)),
        "parent_fingerprint": ancestros[-1] if ancestros else None,
        "integrity_check": inspeccion["integrity_check"],
        "foreign_key_check": inspeccion["foreign_key_check"],
    }
    manifiesto["manifest_sha256"] = _firma_manifiesto(manifiesto)
    return manifiesto


def verificar_manifiesto(ruta_snapshot, ruta_manifiesto=None):
    ruta_snapshot = Path(ruta_snapshot).resolve()
    ruta_manifiesto = Path(ruta_manifiesto or _ruta_manifiesto(ruta_snapshot))
    if not ruta_manifiesto.is_file():
        raise ErrorSincronizacion(f"Falta el manifiesto: {ruta_manifiesto}")
    manifiesto = _leer_json(ruta_manifiesto)
    if manifiesto.get("format_version") != FORMAT_VERSION:
        raise ErrorSincronizacion("Versión de manifiesto incompatible")
    if manifiesto.get("manifest_sha256") != _firma_manifiesto(manifiesto):
        raise ErrorSincronizacion("La firma del manifiesto no coincide")
    actual = inspeccionar(ruta_snapshot)
    campos = (
        "tamano", "sha256_fisico", "schema_version", "data_version", "metadata",
        "conteos", "fingerprints", "fingerprint_global", "integrity_check",
        "foreign_key_check",
    )
    diferentes = [campo for campo in campos if manifiesto.get(campo) != actual.get(campo)]
    if manifiesto.get("nombre_bd") != ruta_snapshot.name:
        diferentes.append("nombre_bd")
    if diferentes:
        raise ErrorSincronizacion(
            "El manifiesto no corresponde al snapshot: " + ", ".join(diferentes)
        )
    if actual["integrity_check"] != ["ok"] or actual["foreign_key_check"]:
        raise ErrorSincronizacion("El snapshot no supera las comprobaciones SQLite")
    return manifiesto, actual


@contextmanager
def bloqueo_operacion(ruta_bd):
    ruta_lock = Path(str(Path(ruta_bd).resolve()) + ".sync.lock")
    ruta_lock.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(ruta_lock, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ErrorSincronizacion(f"Otra operación usa el bloqueo {ruta_lock}") from error
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
        ruta_lock.unlink(missing_ok=True)


def _copiar_con_backup_sqlite(origen, destino):
    origen = Path(origen).resolve()
    destino = Path(destino).resolve()
    destino.parent.mkdir(parents=True, exist_ok=True)
    fuente = base_datos.conectar(origen, readonly=True)
    copia = sqlite3.connect(destino)
    try:
        fuente.backup(copia)
        copia.commit()
    finally:
        copia.close()
        fuente.close()


def snapshot(
    ruta_bd="datos/boe.db", directorio="backups/snapshots", *, nombre=None,
    _bloqueado=False,
):
    ruta_bd = Path(ruta_bd).resolve()
    antes = inspeccionar(ruta_bd)
    directorio = Path(directorio).resolve()
    directorio.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    nombre = nombre or f"boe_snapshot_{marca}_v{antes['data_version']}.db"
    destino = directorio / nombre
    manifiesto_ruta = _ruta_manifiesto(destino)
    if destino.exists() or manifiesto_ruta.exists():
        raise FileExistsError(f"Ya existe el destino del snapshot: {destino}")
    contexto = nullcontext() if _bloqueado else bloqueo_operacion(ruta_bd)
    with contexto:
        try:
            _copiar_con_backup_sqlite(ruta_bd, destino)
            actual = inspeccionar(destino)
            if actual["integrity_check"] != ["ok"] or actual["foreign_key_check"]:
                raise ErrorSincronizacion("El snapshot creado no es válido")
            ancestros = _ascendencia_origen(ruta_bd, actual["fingerprint_global"])
            manifiesto = crear_manifiesto(destino, actual, ancestros)
            manifiesto_ruta.write_text(
                json.dumps(manifiesto, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            verificar_manifiesto(destino, manifiesto_ruta)
        except Exception:
            destino.unlink(missing_ok=True)
            manifiesto_ruta.unlink(missing_ok=True)
            raise
    despues = inspeccionar(ruta_bd)
    if antes != despues:
        destino.unlink(missing_ok=True)
        manifiesto_ruta.unlink(missing_ok=True)
        raise ErrorSincronizacion("La base origen cambió durante el snapshot")
    return {"snapshot": str(destino), "manifiesto": str(manifiesto_ruta), **actual}


def _manifiesto_opcional(ruta):
    manifiesto = _ruta_manifiesto(ruta)
    if not manifiesto.is_file():
        return None
    return verificar_manifiesto(ruta, manifiesto)[0]


def comparar(ruta_local="datos/boe.db", ruta_remota=None):
    if ruta_remota is None:
        raise TypeError("Debe indicarse otra base o snapshot")
    try:
        local = inspeccionar(ruta_local)
        remoto = inspeccionar(ruta_remota)
    except (OSError, ErrorSincronizacion) as error:
        return {"clasificacion": "INVALIDA", "error": str(error)}
    if local["schema_version"] != remoto["schema_version"]:
        clasificacion = "INCOMPATIBLE"
    elif local["fingerprint_global"] == remoto["fingerprint_global"]:
        clasificacion = "IDENTICA"
    else:
        try:
            manifiesto_local = _manifiesto_opcional(ruta_local)
            manifiesto_remoto = _manifiesto_opcional(ruta_remota)
        except ErrorSincronizacion as error:
            return {"clasificacion": "INVALIDA", "error": str(error)}
        ancestros_local = set((manifiesto_local or {}).get("ancestros", []))
        ancestros_remotos = set((manifiesto_remoto or {}).get("ancestros", []))
        if remoto["fingerprint_global"] in ancestros_local:
            clasificacion = "LOCAL_MAS_RECIENTE"
        elif local["fingerprint_global"] in ancestros_remotos:
            clasificacion = "REMOTA_MAS_RECIENTE"
        else:
            clasificacion = "DIVERGENTE"
    tablas_diferentes = [
        tabla for tabla in TABLAS
        if local["fingerprints"].get(tabla) != remoto["fingerprints"].get(tabla)
    ]
    return {
        "clasificacion": clasificacion,
        "local": local,
        "remota": remoto,
        "tablas_diferentes": tablas_diferentes,
        "diferencias_conteos": {
            tabla: {"local": local["conteos"][tabla], "remota": remoto["conteos"][tabla]}
            for tabla in TABLAS if local["conteos"][tabla] != remoto["conteos"][tabla]
        },
    }


def _comprobar_sin_wal(ruta_bd):
    presentes = [Path(str(ruta_bd) + sufijo) for sufijo in ("-wal", "-shm")]
    presentes = [ruta for ruta in presentes if ruta.exists()]
    if presentes:
        raise ErrorSincronizacion(
            "Cierre todos los procesos SQLite y retire WAL/SHM mediante un cierre "
            "limpio antes de restaurar: " + ", ".join(map(str, presentes))
        )


def restaurar(ruta_snapshot, ruta_bd="datos/boe.db", directorio_backup="backups/snapshots"):
    ruta_snapshot = Path(ruta_snapshot).resolve()
    ruta_bd = Path(ruta_bd).resolve()
    manifiesto, remoto = verificar_manifiesto(ruta_snapshot)
    resultado = comparar(ruta_bd, ruta_snapshot)
    if resultado["clasificacion"] != "REMOTA_MAS_RECIENTE":
        raise ErrorSincronizacion(
            f"Restauración abortada: clasificación {resultado['clasificacion']}"
        )
    with bloqueo_operacion(ruta_bd):
        _comprobar_sin_wal(ruta_bd)
        backup = snapshot(
            ruta_bd, directorio_backup,
            nombre=f"boe_pre_restauracion_{datetime.now():%Y%m%d_%H%M%S_%f}.db",
            _bloqueado=True,
        )
        descriptor, nombre_temporal = tempfile.mkstemp(
            prefix=f".{ruta_bd.stem}-restauracion-", suffix=".tmp.db",
            dir=ruta_bd.parent,
        )
        os.close(descriptor)
        temporal = Path(nombre_temporal)
        temporal.unlink()
        try:
            _copiar_con_backup_sqlite(ruta_snapshot, temporal)
            temporal_info = inspeccionar(temporal)
            if temporal_info["fingerprint_global"] != remoto["fingerprint_global"]:
                raise ErrorSincronizacion("La copia temporal no coincide con el snapshot")
            descriptor = os.open(temporal, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.replace(temporal, ruta_bd)
            directorio_fd = os.open(ruta_bd.parent, os.O_RDONLY)
            try:
                os.fsync(directorio_fd)
            finally:
                os.close(directorio_fd)
            procedencia = {
                "format_version": FORMAT_VERSION,
                "fingerprint_restaurado": remoto["fingerprint_global"],
                "ancestros": manifiesto.get("ancestros", []),
                "restored_at": datetime.now().isoformat(timespec="seconds"),
            }
            _ruta_procedencia(ruta_bd).write_text(
                json.dumps(procedencia, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        finally:
            temporal.unlink(missing_ok=True)
    return {"clasificacion": resultado["clasificacion"], "backup": backup, "base_datos": str(ruta_bd)}


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-datos", default="datos/boe.db")
    sub = parser.add_subparsers(dest="operacion", required=True)
    sub.add_parser("inspeccionar")
    p_snapshot = sub.add_parser("snapshot")
    p_snapshot.add_argument("--directorio", default="backups/snapshots")
    p_comparar = sub.add_parser("comparar")
    p_comparar.add_argument("otra_bd_o_snapshot")
    p_restaurar = sub.add_parser("restaurar")
    p_restaurar.add_argument("snapshot")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.operacion == "inspeccionar":
        resultado = inspeccionar(args.base_datos)
    elif args.operacion == "snapshot":
        resultado = snapshot(args.base_datos, args.directorio)
    elif args.operacion == "comparar":
        resultado = comparar(args.base_datos, args.otra_bd_o_snapshot)
    else:
        resultado = restaurar(args.snapshot, args.base_datos)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
