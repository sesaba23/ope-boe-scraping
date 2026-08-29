"""Migra BOE-oposiciones.xlsx a SQLite y audita la equivalencia.

La base resultante no forma parte todavía del flujo productivo: Excel sigue
siendo la fuente de verdad hasta una fase posterior de la migración.
"""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile
import time

import pandas as pd
from tqdm import tqdm

import base_datos


CLAVE_DEDUPLICACION = [
    "Puesto", "Fecha_boe", "Administración", "Enlace", "Num_plazas",
    "Turno", "Sistema", "Escala", "Subescala", "Clase",
]
TABLAS = ("Búsquedas", "Oposiciones", "Log-errores", "Publicaciones", "Cobertura")


def _nulo(valor):
    return valor is None or (isinstance(valor, float) and math.isnan(valor))


def _valor(valor):
    """Convierte valores pandas/numpy sin transformar texto ni NULL."""
    if _nulo(valor):
        return None
    if hasattr(valor, "item"):
        valor = valor.item()
    return valor


def normalizar_fecha(valor):
    """Devuelve YYYY-MM-DD sin modificar la representación original."""
    texto = str(valor)
    if len(texto) == 8 and texto.isdigit():
        return f"{texto[:4]}-{texto[4:6]}-{texto[6:]}"
    try:
        return datetime.strptime(texto, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        pass
    meses = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
        "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
        "octubre": 10, "noviembre": 11, "diciembre": 12,
    }
    partes = texto.lower().split(" de ")
    if len(partes) == 3 and partes[1] in meses:
        return datetime(int(partes[2]), meses[partes[1]], int(partes[0])).strftime("%Y-%m-%d")
    raise ValueError(f"Fecha BOE no reconocida: {texto!r}")


def leer_excel(ruta_excel):
    """Lee el libro sin escribirlo ni normalizar sus contenidos."""
    ruta_excel = Path(ruta_excel)
    with pd.ExcelFile(ruta_excel) as libro:
        faltantes = set(TABLAS) - set(libro.sheet_names)
        if faltantes:
            raise ValueError(f"Faltan hojas requeridas: {sorted(faltantes)}")
        return {hoja: libro.parse(hoja) for hoja in TABLAS}


def _filas(df, columnas):
    for fila in df.loc[:, columnas].itertuples(index=False, name=None):
        yield tuple(_valor(valor) for valor in fila)


def importar(conexion, hojas, *, progreso=True):
    """Inserta las hojas en una única transacción; devuelve conteos."""
    publicaciones = hojas["Publicaciones"]
    oposiciones = hojas["Oposiciones"]
    conteos = {}
    with base_datos.transaccion(conexion):
        filas = (
            (pid, enlace, normalizar_fecha(fecha), fecha, titulo, ultimo, version,
             estado, coincidencias, None, None, None, None, None, None, None)
            for pid, enlace, fecha, titulo, ultimo, version, estado, coincidencias in _filas(
                publicaciones,
                ["Publicacion_ID", "Enlace", "Fecha_BOE", "Titulo_original", "Fecha_ultimo_analisis",
                 "Version_extractor", "Estado_analisis", "Coincidencias"],
            )
        )
        conexion.executemany(
            "INSERT INTO publicaciones VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", filas
        )
        conteos["publicaciones"] = len(publicaciones)

        columnas_oposiciones = [
            "Num_plazas", "Puesto", "Administración", "Escala", "Subescala", "Clase",
            "Sistema", "Turno", "Fecha_boe", "Publicación", "Enlace", "Municipio",
            "Provincia", "Latitud", "Longitud", "Habitantes", "Publicacion_ID",
            "Version_extractor", "Fecha_analisis",
        ]
        filas = (
            (num, puesto, administracion, escala, subescala, clase, sistema, turno,
             normalizar_fecha(fecha), fecha, publicacion, enlace, municipio, provincia,
             latitud, longitud, habitantes, publicacion_id, version, analisis)
            for num, puesto, administracion, escala, subescala, clase, sistema, turno,
            fecha, publicacion, enlace, municipio, provincia, latitud, longitud,
            habitantes, publicacion_id, version, analisis in _filas(oposiciones, columnas_oposiciones)
        )
        if progreso:
            filas = tqdm(filas, total=len(oposiciones), desc="Importando Oposiciones", unit="fila")
        conexion.executemany(
            """INSERT INTO oposiciones(
                num_plazas, puesto, administracion, escala, subescala, clase, sistema,
                turno, fecha_boe, fecha_boe_original, publicacion, enlace, municipio,
                provincia, latitud, longitud, habitantes, publicacion_id,
                version_extractor, fecha_analisis
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            filas,
        )
        conteos["oposiciones"] = len(oposiciones)

        conexion.executemany("INSERT INTO busquedas(codigo) VALUES (?)", _filas(hojas["Búsquedas"], ["Código"]))
        conteos["busquedas"] = len(hojas["Búsquedas"])
        conexion.executemany(
            "INSERT INTO cobertura VALUES (?,?,?,?,?)",
            _filas(hojas["Cobertura"], ["Fecha", "Estado", "Version_extractor", "Fecha_ultima_consulta", "Numero_publicaciones"]),
        )
        conteos["cobertura"] = len(hojas["Cobertura"])
        conexion.executemany(
            "INSERT INTO log_errores(fecha,tipo_error,enlace_web) VALUES (?,?,?)",
            _filas(hojas["Log-errores"], ["Fecha", "Tipo de error", "Enlace Web"]),
        )
        conteos["log_errores"] = len(hojas["Log-errores"])
    return conteos


def _etiquetar(valor):
    valor = _valor(valor)
    if valor is None:
        return "NULL"
    if isinstance(valor, bool):
        return f"INTEGER:{int(valor)}"
    if isinstance(valor, int):
        return f"INTEGER:{valor}"
    if isinstance(valor, float):
        return f"REAL:{valor.hex()}"
    return f"TEXT:{len(str(valor))}:{valor}"


def _fingerprint(registros):
    lineas = sorted(
        json.dumps([_etiquetar(valor) for valor in fila], ensure_ascii=False, separators=(",", ":"))
        for fila in registros
    )
    digest = hashlib.sha256()
    for linea in lineas:
        digest.update(linea.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _registros_excel(hojas, hoja):
    columnas = {
        "Búsquedas": ["Código"],
        "Oposiciones": ["Num_plazas", "Puesto", "Administración", "Escala", "Subescala", "Clase", "Sistema", "Turno", "Fecha_boe", "Publicación", "Enlace", "Municipio", "Provincia", "Latitud", "Longitud", "Habitantes", "Publicacion_ID", "Version_extractor", "Fecha_analisis"],
        "Log-errores": ["Fecha", "Tipo de error", "Enlace Web"],
        "Publicaciones": ["Publicacion_ID", "Enlace", "Fecha_BOE", "Titulo_original", "Fecha_ultimo_analisis", "Version_extractor", "Estado_analisis", "Coincidencias"],
        "Cobertura": ["Fecha", "Estado", "Version_extractor", "Fecha_ultima_consulta", "Numero_publicaciones"],
    }[hoja]
    registros = list(_filas(hojas[hoja], columnas))
    texto_por_hoja = {
        "Búsquedas": {"Código"},
        "Oposiciones": {"Puesto", "Administración", "Escala", "Subescala", "Clase", "Sistema", "Turno", "Fecha_boe", "Publicación", "Enlace", "Municipio", "Provincia", "Publicacion_ID", "Version_extractor", "Fecha_analisis"},
        "Log-errores": {"Fecha", "Tipo de error", "Enlace Web"},
        "Publicaciones": {"Publicacion_ID", "Enlace", "Fecha_BOE", "Titulo_original", "Fecha_ultimo_analisis", "Version_extractor", "Estado_analisis"},
        "Cobertura": {"Fecha", "Estado", "Version_extractor", "Fecha_ultima_consulta"},
    }[hoja]
    texto_indices = {columnas.index(columna) for columna in texto_por_hoja}
    registros = [
        tuple(str(valor) if indice in texto_indices and valor is not None else valor for indice, valor in enumerate(fila))
        for fila in registros
    ]
    # Pandas convierte una columna entera con NULL (Habitantes) en float64.
    # Su semántica de datos es entera y SQLite la conserva como INTEGER.
    if hoja == "Oposiciones":
        registros = [
            fila[:15] + (int(fila[15]) if isinstance(fila[15], float) and fila[15].is_integer() else fila[15],) + fila[16:]
            for fila in registros
        ]
    return registros, columnas


def _registros_sqlite(conexion, hoja):
    consultas = {
        "Búsquedas": "SELECT codigo FROM busquedas",
        "Oposiciones": "SELECT num_plazas,puesto,administracion,escala,subescala,clase,sistema,turno,fecha_boe_original,publicacion,enlace,municipio,provincia,latitud,longitud,habitantes,publicacion_id,version_extractor,fecha_analisis FROM oposiciones",
        "Log-errores": "SELECT fecha,tipo_error,enlace_web FROM log_errores",
        "Publicaciones": "SELECT publicacion_id,enlace,fecha_boe_original,titulo_original,fecha_ultimo_analisis,version_extractor,estado_analisis,coincidencias FROM publicaciones",
        "Cobertura": "SELECT fecha,estado,version_extractor,fecha_ultima_consulta,numero_publicaciones FROM cobertura",
    }
    return [tuple(fila) for fila in conexion.execute(consultas[hoja])]


def _nulos(registros, columnas):
    return {columna: sum(_valor(fila[i]) is None for fila in registros) for i, columna in enumerate(columnas)}


def _clave_nula_segura(fila):
    return tuple("<NULL>" if _valor(valor) is None else _etiquetar(valor) for valor in fila)


def auditar(hojas, conexion):
    """Devuelve una auditoría determinista, sin asumir conteos fijos."""
    tablas = {}
    global_digest = hashlib.sha256()
    diferencias = []
    for hoja in TABLAS:
        excel, columnas = _registros_excel(hojas, hoja)
        sqlite = _registros_sqlite(conexion, hoja)
        fp_excel, fp_sqlite = _fingerprint(excel), _fingerprint(sqlite)
        detalle = {
            "filas_excel": len(excel), "filas_sqlite": len(sqlite),
            "nulos_excel": _nulos(excel, columnas), "nulos_sqlite": _nulos(sqlite, columnas),
            "fingerprint_excel": fp_excel, "fingerprint_sqlite": fp_sqlite,
            "equivalente": len(excel) == len(sqlite) and fp_excel == fp_sqlite and _nulos(excel, columnas) == _nulos(sqlite, columnas),
        }
        tablas[hoja] = detalle
        global_digest.update(f"{hoja}:{fp_excel}:{fp_sqlite}\n".encode())
        if not detalle["equivalente"]:
            diferencias.append(f"{hoja}: filas, nulos o fingerprint distintos")

    oposiciones_excel, _ = _registros_excel(hojas, "Oposiciones")
    oposiciones_sqlite = _registros_sqlite(conexion, "Oposiciones")
    indice_clave = [1, 8, 2, 10, 0, 7, 6, 3, 4, 5]
    duplicados_excel = len(oposiciones_excel) - len({_clave_nula_segura([fila[i] for i in indice_clave]) for fila in oposiciones_excel})
    duplicados_sqlite = len(oposiciones_sqlite) - len({_clave_nula_segura([fila[i] for i in indice_clave]) for fila in oposiciones_sqlite})
    ids_publicaciones = {fila[0] for fila in _registros_sqlite(conexion, "Publicaciones")}
    ids_oposiciones = {fila[16] for fila in oposiciones_sqlite}
    no_enteros = [fila[0] for fila in oposiciones_sqlite if not isinstance(fila[0], int)]
    semantica = {
        "publicacion_id_unicos": len(ids_publicaciones),
        "publicaciones_sin_oposiciones": len(ids_publicaciones - ids_oposiciones),
        "oposiciones_huerfanas": len(ids_oposiciones - ids_publicaciones),
        "duplicados_clave_excel": duplicados_excel,
        "duplicados_clave_sqlite": duplicados_sqlite,
        "num_plazas_no_enteros": [_etiquetar(valor) for valor in no_enteros],
    }
    if duplicados_excel != duplicados_sqlite:
        diferencias.append("La deduplicación NULL-safe no coincide")
    if semantica["oposiciones_huerfanas"]:
        diferencias.append("Existen oposiciones huérfanas")
    return {
        "tablas": tablas, "fingerprint_global": global_digest.hexdigest(),
        "integrity_check": base_datos.integrity_check(conexion),
        "foreign_key_check": base_datos.foreign_key_check(conexion),
        "semantica": semantica, "diferencias": diferencias,
        "correcta": not diferencias and all(valor["equivalente"] for valor in tablas.values()),
    }


def _markdown(informe):
    lineas = ["# Auditoría de migración Excel → SQLite", "", f"Resultado: {'correcto' if informe['correcta'] else 'CON DIFERENCIAS'}", "", "## Tablas", "", "| Hoja | Excel | SQLite | Equivalente |", "|---|---:|---:|---|"]
    for nombre, datos in informe["tablas"].items():
        lineas.append(f"| {nombre} | {datos['filas_excel']} | {datos['filas_sqlite']} | {datos['equivalente']} |")
    lineas += ["", "## Semántica", ""]
    for clave, valor in informe["semantica"].items():
        lineas.append(f"- {clave}: `{valor}`")
    lineas += ["", "## Integridad", "", f"- integrity_check: `{informe['integrity_check']}`", f"- foreign_key_check: `{informe['foreign_key_check']}`", f"- fingerprint global: `{informe['fingerprint_global']}`"]
    if informe["diferencias"]:
        lineas += ["", "## Diferencias", ""] + [f"- {d}" for d in informe["diferencias"]]
    return "\n".join(lineas) + "\n"


def migrar(ruta_excel="BOE-oposiciones.xlsx", destino="datos/boe.db", *, recrear=False, progreso=True):
    destino = Path(destino)
    if destino.exists() and not recrear:
        raise FileExistsError(f"La base ya existe: {destino}. Use --recrear para sustituirla.")
    inicio = time.perf_counter()
    hojas = leer_excel(ruta_excel)
    hash_excel = base_datos.hash_archivo(ruta_excel)
    destino.parent.mkdir(parents=True, exist_ok=True)
    descriptor, nombre_temporal = tempfile.mkstemp(prefix=".boe-", suffix=".db", dir=destino.parent)
    os.close(descriptor)
    temporal = Path(nombre_temporal)
    try:
        conexion = base_datos.conectar(temporal)
        try:
            base_datos.crear_esquema(conexion)
            conteos = importar(conexion, hojas, progreso=progreso)
            base_datos.crear_indices(conexion)
            base_datos.guardar_metadata(conexion, source_excel_hash=hash_excel, data_version=1)
            conexion.commit()
            informe = auditar(hojas, conexion)
            if informe["integrity_check"] != ["ok"] or informe["foreign_key_check"] or not informe["correcta"]:
                raise RuntimeError(f"Auditoría fallida: {informe['diferencias']}")
        finally:
            conexion.close()
        informes = Path("informes/migracion_sqlite")
        informes.mkdir(parents=True, exist_ok=True)
        (informes / "auditoria_migracion_sqlite.json").write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (informes / "auditoria_migracion_sqlite.md").write_text(_markdown(informe), encoding="utf-8")
        os.replace(temporal, destino)
        return {"destino": str(destino), "conteos": conteos, "segundos": time.perf_counter() - inicio, "informe": informe}
    except Exception:
        temporal.unlink(missing_ok=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--excel", default="BOE-oposiciones.xlsx")
    parser.add_argument("--destino", default="datos/boe.db")
    parser.add_argument("--recrear", action="store_true")
    parser.add_argument("--sin-progreso", action="store_true")
    args = parser.parse_args(argv)
    resultado = migrar(args.excel, args.destino, recrear=args.recrear, progreso=not args.sin_progreso)
    print(json.dumps({"destino": resultado["destino"], "conteos": resultado["conteos"], "segundos": round(resultado["segundos"], 3), "fingerprint_global": resultado["informe"]["fingerprint_global"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
