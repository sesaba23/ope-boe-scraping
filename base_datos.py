"""Persistencia SQLite productiva y soporte para la migración inicial."""
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import hashlib
import sqlite3
import pandas as pd


ESQUEMA = """
CREATE TABLE metadata (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

CREATE TABLE publicaciones (
    publicacion_id TEXT PRIMARY KEY,
    enlace TEXT NOT NULL,
    fecha_boe TEXT NOT NULL,
    fecha_boe_original TEXT NOT NULL,
    titulo_original TEXT,
    fecha_ultimo_analisis TEXT,
    version_extractor TEXT NOT NULL,
    estado_analisis TEXT NOT NULL,
    coincidencias INTEGER NOT NULL,
    departamento_boe TEXT,
    administracion_resuelta TEXT,
    familia_administrativa TEXT,
    estado_resolucion TEXT,
    metodo_resolucion TEXT,
    confianza_resolucion TEXT,
    version_resolucion TEXT
);

CREATE TABLE oposiciones (
    oposicion_id INTEGER PRIMARY KEY,
    num_plazas INTEGER,
    puesto TEXT NOT NULL,
    puesto_normalizado TEXT,
    administracion TEXT,
    administracion_normalizada TEXT,
    ambito TEXT,
    tipo_entidad TEXT,
    escala TEXT NOT NULL,
    subescala TEXT NOT NULL,
    clase TEXT NOT NULL,
    sistema TEXT NOT NULL,
    turno TEXT NOT NULL,
    fecha_boe TEXT NOT NULL,
    fecha_boe_original TEXT NOT NULL,
    publicacion TEXT,
    enlace TEXT NOT NULL,
    municipio TEXT,
    provincia TEXT,
    comunidad_autonoma TEXT,
    confianza_geografica TEXT,
    evidencia_geografica TEXT,
    version_resolutor TEXT,
    latitud REAL,
    longitud REAL,
    habitantes INTEGER,
    publicacion_id TEXT NOT NULL,
    version_extractor TEXT NOT NULL,
    fecha_analisis TEXT,
    FOREIGN KEY (publicacion_id) REFERENCES publicaciones(publicacion_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE busquedas (
    codigo TEXT PRIMARY KEY
);

CREATE TABLE cobertura (
    fecha TEXT PRIMARY KEY,
    estado TEXT NOT NULL,
    version_extractor TEXT NOT NULL,
    fecha_ultima_consulta TEXT NOT NULL,
    numero_publicaciones INTEGER NOT NULL
);

CREATE TABLE log_errores (
    error_id INTEGER PRIMARY KEY,
    fecha TEXT NOT NULL,
    tipo_error TEXT NOT NULL,
    enlace_web TEXT NOT NULL
);
"""

VERSION_ESQUEMA = "4"

INDICES = """
CREATE INDEX ix_oposiciones_fecha ON oposiciones(fecha_boe);
CREATE INDEX ix_oposiciones_administracion ON oposiciones(administracion);
CREATE INDEX ix_oposiciones_administracion_normalizada ON oposiciones(administracion_normalizada);
CREATE INDEX ix_oposiciones_ambito ON oposiciones(ambito);
CREATE INDEX ix_oposiciones_municipio ON oposiciones(municipio);
CREATE INDEX ix_oposiciones_provincia ON oposiciones(provincia);
CREATE INDEX ix_oposiciones_publicacion ON oposiciones(publicacion_id);
CREATE INDEX ix_oposiciones_puesto ON oposiciones(puesto);
CREATE INDEX ix_oposiciones_clave_deduplicacion ON oposiciones(
    puesto, fecha_boe, administracion, enlace, num_plazas,
    turno, sistema, escala, subescala, clase
);
CREATE INDEX ix_publicaciones_fecha ON publicaciones(fecha_boe);
"""


def conectar(ruta, *, readonly=False):
    """Abre una conexión con las claves foráneas activas."""
    ruta = Path(ruta)
    if readonly:
        conexion = sqlite3.connect(f"file:{ruta.resolve()}?mode=ro", uri=True)
    else:
        conexion = sqlite3.connect(ruta)
    conexion.execute("PRAGMA foreign_keys = ON")
    return conexion


def crear_esquema(conexion):
    conexion.executescript(ESQUEMA)


def crear_indices(conexion):
    conexion.executescript(INDICES)


@contextmanager
def transaccion(conexion):
    """Transacción de escritura que revierte cualquier excepción."""
    conexion.execute("BEGIN IMMEDIATE")
    try:
        yield conexion
    except Exception:
        conexion.rollback()
        raise
    else:
        conexion.commit()


def integrity_check(conexion):
    return [fila[0] for fila in conexion.execute("PRAGMA integrity_check")]


def foreign_key_check(conexion):
    return [tuple(fila) for fila in conexion.execute("PRAGMA foreign_key_check")]


def hash_archivo(ruta):
    digest = hashlib.sha256()
    with Path(ruta).open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def guardar_metadata(conexion, *, source_excel_hash=None, data_version=None):
    existente = dict(conexion.execute("SELECT clave,valor FROM metadata"))
    ahora = datetime.now().isoformat(timespec="seconds")
    if data_version is None:
        data_version = int(existente.get("data_version", "0"))
    source_hash = source_excel_hash or existente.get("migration_source_hash")
    pares = [
        ("schema_version", VERSION_ESQUEMA), ("data_version", str(data_version)),
        ("updated_at", ahora), ("created_at", existente.get("created_at", ahora)),
    ]
    if source_hash:
        pares += [("migration_source_hash", source_hash),
                  ("migration_source_filename", existente.get("migration_source_filename", "BOE-oposiciones.xlsx")),
                  ("migrated_at", existente.get("migrated_at", ahora))]
    conexion.executemany(
        "INSERT INTO metadata(clave,valor) VALUES (?,?) ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
        pares,
    )


def validar_base_principal(ruta_bd):
    """Validación ligera para el arranque diario, independiente del Excel."""
    ruta_bd = Path(ruta_bd)
    if not ruta_bd.exists():
        raise EspejoSQLiteError("SQLite no disponible. Ejecute migrar_excel_sqlite.py.")
    conexion = conectar(ruta_bd, readonly=True)
    try:
        try:
            filas = dict(conexion.execute("SELECT clave,valor FROM metadata"))
            if conexion.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise EspejoSQLiteError("SQLite no supera quick_check.")
        except sqlite3.OperationalError as error:
            raise EspejoSQLiteError(
                "SQLite no contiene metadatos de procedencia. Ejecute migrar_excel_sqlite.py."
            ) from error
    finally:
        conexion.close()
    obligatorias = {"schema_version", "data_version", "created_at", "updated_at"}
    if filas.get("schema_version") in {"2", "3"}:
        raise EspejoSQLiteError(
            f"SQLite usa schema_version {filas.get('schema_version')}. Ejecute: "
            "python migrar_esquema_sqlite.py --base-datos datos/boe.db"
        )
    if filas.get("schema_version") != VERSION_ESQUEMA or not obligatorias <= set(filas):
        raise EspejoSQLiteError("SQLite no contiene metadatos válidos. Ejecute migrar_excel_sqlite.py.")
    return filas


def _iso_rango(fecha):
    texto = str(fecha).replace("/", "-")
    if len(texto) == 10 and texto[4] == "-":
        return texto
    from migrar_excel_sqlite import normalizar_fecha
    return normalizar_fecha(texto)


def _dataframe(conexion, consulta, columnas, parametros=()):
    return pd.DataFrame(conexion.execute(consulta, parametros).fetchall(), columns=columnas)


def cargar_para_lectura(ruta_bd, fecha_inicio, fecha_fin):
    """Carga solo el histórico imprescindible durante el procesamiento de un rango."""
    inicio, fin = _iso_rango(fecha_inicio), _iso_rango(fecha_fin)
    conexion = conectar(ruta_bd, readonly=True)
    try:
        return {
            # Búsquedas es global: sus códigos no incluyen necesariamente una fecha.
            "Búsquedas": _dataframe(conexion, "SELECT codigo FROM busquedas", ["Código"]),
            # Fecha_boe pertenece a la clave funcional: fuera del intervalo no puede
            # existir un duplicado de una convocatoria del intervalo.
            "Oposiciones": _dataframe(conexion, """SELECT num_plazas,puesto,puesto_normalizado,administracion,escala,subescala,clase,sistema,turno,fecha_boe_original,publicacion,enlace,municipio,provincia,latitud,longitud,habitantes,publicacion_id,version_extractor,fecha_analisis FROM oposiciones WHERE fecha_boe BETWEEN ? AND ?""", ["Num_plazas", "Puesto", "Puesto_normalizado", "Administración", "Escala", "Subescala", "Clase", "Sistema", "Turno", "Fecha_boe", "Publicación", "Enlace", "Municipio", "Provincia", "Latitud", "Longitud", "Habitantes", "Publicacion_ID", "Version_extractor", "Fecha_analisis"], (inicio, fin)),
            "Publicaciones": _dataframe(conexion, "SELECT publicacion_id,enlace,fecha_boe_original,titulo_original,fecha_ultimo_analisis,version_extractor,estado_analisis,coincidencias,departamento_boe,administracion_resuelta,familia_administrativa,estado_resolucion,metodo_resolucion,confianza_resolucion,version_resolucion FROM publicaciones WHERE fecha_boe BETWEEN ? AND ?", ["Publicacion_ID", "Enlace", "Fecha_BOE", "Titulo_original", "Fecha_ultimo_analisis", "Version_extractor", "Estado_analisis", "Coincidencias", "Departamento_BOE", "Administracion_resuelta", "Familia_administrativa", "Estado_resolucion", "Metodo_resolucion", "Confianza_resolucion", "Version_resolucion"], (inicio, fin)),
            "Cobertura": _dataframe(conexion, "SELECT fecha,estado,version_extractor,fecha_ultima_consulta,numero_publicaciones FROM cobertura WHERE fecha BETWEEN ? AND ?", ["Fecha", "Estado", "Version_extractor", "Fecha_ultima_consulta", "Numero_publicaciones"], (inicio, fin)),
            # Sólo hay 33 filas; se conserva la semántica de append del libro.
            "Log-errores": _dataframe(conexion, "SELECT fecha,tipo_error,enlace_web FROM log_errores", ["Fecha", "Tipo de error", "Enlace Web"]),
        }
    finally:
        conexion.close()


class EspejoSQLiteError(RuntimeError):
    """La escritura espejo no pudo completar una sincronización verificable."""


def crear_backup(ruta_bd, directorio="backups/sqlite"):
    """Crea un backup consistente con la API SQLite y lo verifica."""
    ruta_bd = Path(ruta_bd)
    if not ruta_bd.exists():
        raise EspejoSQLiteError(f"No existe la base SQLite: {ruta_bd}")
    destino_dir = Path(directorio)
    destino_dir.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destino = destino_dir / f"{ruta_bd.stem}_{marca}.db"
    origen = conectar(ruta_bd, readonly=True)
    copia = conectar(destino)
    try:
        origen.backup(copia)
        if integrity_check(copia) != ["ok"] or foreign_key_check(copia):
            raise EspejoSQLiteError("El backup SQLite no supera sus comprobaciones de integridad")
    except Exception:
        copia.close()
        destino.unlink(missing_ok=True)
        raise
    else:
        copia.close()
    finally:
        origen.close()
    return destino


def _funciones_migracion():
    """Importación diferida para mantener este módulo como dueño del adaptador."""
    from migrar_excel_sqlite import _filas, normalizar_fecha
    return _filas, normalizar_fecha


def insertar_publicaciones(conexion, df):
    filas, fecha = _funciones_migracion()
    conexion.executemany(
        "INSERT INTO publicaciones VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ((pid, enlace, fecha(f_boe), f_boe, titulo, ultimo, version, estado, coincidencias,
          None, None, None, None, None, None, None)
         for pid, enlace, f_boe, titulo, ultimo, version, estado, coincidencias in filas(
             df, ["Publicacion_ID", "Enlace", "Fecha_BOE", "Titulo_original",
                  "Fecha_ultimo_analisis", "Version_extractor", "Estado_analisis", "Coincidencias"])),
    )


def insertar_oposiciones(conexion, df):
    filas, fecha = _funciones_migracion()
    from normalizacion_puestos import normalizar_puesto

    columnas = ["Num_plazas", "Puesto", "Administración", "Escala", "Subescala", "Clase",
                "Sistema", "Turno", "Fecha_boe", "Publicación", "Enlace", "Municipio",
                "Provincia", "Latitud", "Longitud", "Habitantes", "Publicacion_ID",
                "Version_extractor", "Fecha_analisis"]
    from resolucion_geografica import resolver_administracion_geografia
    conexion.executemany(
        """INSERT INTO oposiciones(
            num_plazas, puesto, puesto_normalizado, administracion, administracion_normalizada, ambito, tipo_entidad, escala, subescala, clase, sistema, turno,
            fecha_boe, fecha_boe_original, publicacion, enlace, municipio, provincia,
            comunidad_autonoma, confianza_geografica, evidencia_geografica, version_resolutor,
            latitud, longitud, habitantes, publicacion_id, version_extractor, fecha_analisis
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ((num, puesto, normalizar_puesto(puesto), administracion, geo.administracion_normalizada, geo.ambito, geo.tipo_entidad, escala, subescala, clase, sistema, turno,
          fecha(f_boe), f_boe, publicacion, enlace, geo.municipio or municipio, geo.provincia or provincia, geo.comunidad_autonoma,
          geo.confianza, geo.evidencia, geo.version_catalogo, latitud, longitud, habitantes, publicacion_id, version, analisis)
         for num, puesto, administracion, escala, subescala, clase, sistema, turno,
         f_boe, publicacion, enlace, municipio, provincia, latitud, longitud,
         habitantes, publicacion_id, version, analisis in filas(df, columnas)
         for geo in (resolver_administracion_geografia(administracion, puesto),)),
    )


def normalizar_oposiciones_dataframe(df):
    """Calcula siempre el canon desde Puesto, sin confiar en datos derivados."""
    from normalizacion_puestos import normalizar_puesto

    resultado = df.copy(deep=True)
    if "Puesto" not in resultado.columns:
        raise ValueError("Falta la columna obligatoria: Puesto")
    resultado["Puesto_normalizado"] = resultado["Puesto"].map(normalizar_puesto)
    return resultado


def actualizar_busquedas(conexion, df):
    filas, _ = _funciones_migracion()
    conexion.executemany("INSERT INTO busquedas(codigo) VALUES (?)", filas(df, ["Código"]))


def actualizar_cobertura(conexion, df):
    filas, _ = _funciones_migracion()
    conexion.executemany("INSERT INTO cobertura VALUES (?,?,?,?,?)", filas(
        df, ["Fecha", "Estado", "Version_extractor", "Fecha_ultima_consulta", "Numero_publicaciones"]
    ))


def insertar_log_errores(conexion, df):
    filas, _ = _funciones_migracion()
    conexion.executemany(
        "INSERT INTO log_errores(fecha,tipo_error,enlace_web) VALUES (?,?,?)",
        filas(df, ["Fecha", "Tipo de error", "Enlace Web"]),
    )


def _fingerprint_df(df, hoja):
    from migrar_excel_sqlite import _fingerprint, _registros_excel
    return _fingerprint(_registros_excel({hoja: df}, hoja)[0])


def _hay_cambios_principales(conexion, dataframes, inicio, fin):
    actuales = cargar_para_lectura(conexion.execute("PRAGMA database_list").fetchone()[2], inicio, fin)
    for hoja in ("Oposiciones", "Publicaciones", "Cobertura"):
        if _fingerprint_df(actuales[hoja], hoja) != _fingerprint_df(dataframes[hoja], hoja):
            return True
    # Búsquedas y errores se cargan completos para mantener su semántica global.
    for hoja in ("Búsquedas", "Log-errores"):
        if _fingerprint_df(actuales[hoja], hoja) != _fingerprint_df(dataframes[hoja], hoja):
            return True
    return False


def persistir_lote_principal(ruta_bd, dataframes, fecha_inicio, fecha_fin, directorio_backup="backups/sqlite"):
    """Persiste el lote final SQLite sin depender de ningún XLSX.

    Oposiciones se reemplazan sólo en el rango: Fecha_boe integra la clave
    funcional de deduplicación, por lo que el resto no participa en ella.
    """
    validar_base_principal(ruta_bd)
    dataframes = dict(dataframes)
    dataframes["Oposiciones"] = normalizar_oposiciones_dataframe(
        dataframes["Oposiciones"]
    )
    inicio, fin = _iso_rango(fecha_inicio), _iso_rango(fecha_fin)
    conexion = conectar(ruta_bd)
    try:
        if not _hay_cambios_principales(conexion, dataframes, inicio, fin):
            return {"cambios": False, "backup": None, "data_version": int(dict(conexion.execute("SELECT clave,valor FROM metadata"))["data_version"])}
    finally:
        conexion.close()
    backup = crear_backup(ruta_bd, directorio_backup)
    conexion = conectar(ruta_bd)
    try:
        with transaccion(conexion):
            conexion.execute("DELETE FROM oposiciones WHERE fecha_boe BETWEEN ? AND ?", (inicio, fin))
            insertar_publicaciones_upsert(conexion, dataframes["Publicaciones"])
            insertar_oposiciones(conexion, dataframes["Oposiciones"])
            insertar_busquedas_sin_duplicar(conexion, dataframes["Búsquedas"])
            actualizar_cobertura_upsert(conexion, dataframes["Cobertura"])
            insertar_errores_sin_duplicar(conexion, dataframes["Log-errores"])
            metadata = dict(conexion.execute("SELECT clave,valor FROM metadata"))
            guardar_metadata(conexion, data_version=int(metadata["data_version"]) + 1)
            if integrity_check(conexion) != ["ok"] or foreign_key_check(conexion):
                raise EspejoSQLiteError("Las invariantes SQLite fallaron antes de COMMIT")
        return {"cambios": True, "backup": str(backup), "data_version": int(metadata["data_version"]) + 1}
    finally:
        conexion.close()


def insertar_publicaciones_upsert(conexion, df):
    filas, fecha = _funciones_migracion()
    columnas = "publicacion_id,enlace,fecha_boe,fecha_boe_original,titulo_original,fecha_ultimo_analisis,version_extractor,estado_analisis,coincidencias,departamento_boe,administracion_resuelta,familia_administrativa,estado_resolucion,metodo_resolucion,confianza_resolucion,version_resolucion"
    actualiza = ",".join(f"{c}=excluded.{c}" for c in columnas.split(",")[1:])
    conexion.executemany(
        f"INSERT INTO publicaciones({columnas}) VALUES ({','.join('?' * 16)}) ON CONFLICT(publicacion_id) DO UPDATE SET {actualiza}",
        ((pid, enlace, fecha(f_boe), f_boe, titulo, ultimo, version, estado, coincidencias,
          dep, adm, fam, est, metodo, confianza, vres)
         for pid, enlace, f_boe, titulo, ultimo, version, estado, coincidencias, dep, adm, fam, est, metodo, confianza, vres in filas(df, ["Publicacion_ID", "Enlace", "Fecha_BOE", "Titulo_original", "Fecha_ultimo_analisis", "Version_extractor", "Estado_analisis", "Coincidencias", "Departamento_BOE", "Administracion_resuelta", "Familia_administrativa", "Estado_resolucion", "Metodo_resolucion", "Confianza_resolucion", "Version_resolucion"])),
    )


def insertar_busquedas_sin_duplicar(conexion, df):
    filas, _ = _funciones_migracion()
    conexion.executemany("INSERT OR IGNORE INTO busquedas(codigo) VALUES (?)", filas(df, ["Código"]))


def actualizar_cobertura_upsert(conexion, df):
    filas, _ = _funciones_migracion()
    conexion.executemany("INSERT INTO cobertura VALUES (?,?,?,?,?) ON CONFLICT(fecha) DO UPDATE SET estado=excluded.estado,version_extractor=excluded.version_extractor,fecha_ultima_consulta=excluded.fecha_ultima_consulta,numero_publicaciones=excluded.numero_publicaciones", filas(df, ["Fecha", "Estado", "Version_extractor", "Fecha_ultima_consulta", "Numero_publicaciones"]))


def insertar_errores_sin_duplicar(conexion, df):
    filas, _ = _funciones_migracion()
    conexion.executemany("INSERT INTO log_errores(fecha,tipo_error,enlace_web) SELECT ?,?,? WHERE NOT EXISTS (SELECT 1 FROM log_errores WHERE fecha=? AND tipo_error=? AND enlace_web=?)", ((a,b,c,a,b,c) for a,b,c in filas(df, ["Fecha", "Tipo de error", "Enlace Web"])))


def cargar_historico_para_aplicar(ruta_bd, fecha_inicio, fecha_fin):
    """Carga únicamente las filas que pueden verse afectadas por un lote histórico."""
    datos = cargar_para_lectura(ruta_bd, fecha_inicio, fecha_fin)
    return {clave: datos[clave] for clave in ("Oposiciones", "Publicaciones", "Cobertura")}


def _huella_dataframe(df, columnas):
    """Huella estable, incluyendo todas las columnas funcionales indicadas."""
    from migrar_excel_sqlite import _fingerprint, _filas
    return _fingerprint(list(_filas(df, columnas)))


def _conservar_timestamps_auditoria(propuestos, actuales, clave, columnas_logicas,
                                    columnas_temporales):
    """Conserva los valores de auditoría si la fila no cambió funcionalmente."""
    resultado = propuestos.copy(deep=True)
    if resultado.empty or actuales.empty:
        return resultado
    indice_actual = {
        tuple(fila): fila for fila in actuales.loc[:, clave + columnas_logicas + columnas_temporales]
        .itertuples(index=False, name=None)
    }
    for indice, fila in resultado.iterrows():
        identidad = tuple(fila[campo] for campo in clave)
        actual = indice_actual.get(identidad)
        if actual is None:
            continue
        valores_actuales = dict(zip(clave + columnas_logicas + columnas_temporales, actual))
        def iguales(a, b):
            return (pd.isna(a) and pd.isna(b)) or a == b
        if all(iguales(fila[campo], valores_actuales[campo]) for campo in columnas_logicas):
            for campo in columnas_temporales:
                resultado.at[indice, campo] = valores_actuales[campo]
    return resultado


def persistir_lote_historico(ruta_bd, oposiciones_nuevas, publicaciones, cobertura,
                              fecha_inicio, fecha_fin, directorio_backup="backups/sqlite"):
    """Añade un lote histórico en una sola transacción, sin depender de Excel.

    Las oposiciones ya deben venir deduplicadas frente al rango. Publicaciones y
    cobertura son el estado final del rango y se actualizan mediante sus claves.
    """
    validar_base_principal(ruta_bd)
    oposiciones_nuevas = normalizar_oposiciones_dataframe(oposiciones_nuevas)
    actuales = cargar_historico_para_aplicar(ruta_bd, fecha_inicio, fecha_fin)
    columnas_publicaciones = ["Publicacion_ID", "Enlace", "Fecha_BOE", "Titulo_original",
        "Fecha_ultimo_analisis", "Version_extractor", "Estado_analisis", "Coincidencias",
        "Departamento_BOE", "Administracion_resuelta", "Familia_administrativa",
        "Estado_resolucion", "Metodo_resolucion", "Confianza_resolucion", "Version_resolucion"]
    columnas_cobertura = ["Fecha", "Estado", "Version_extractor", "Fecha_ultima_consulta", "Numero_publicaciones"]
    publicaciones = _conservar_timestamps_auditoria(
        publicaciones, actuales["Publicaciones"], ["Publicacion_ID"],
        [campo for campo in columnas_publicaciones if campo not in {"Publicacion_ID", "Fecha_ultimo_analisis"}],
        ["Fecha_ultimo_analisis"],
    )
    cobertura = _conservar_timestamps_auditoria(
        cobertura, actuales["Cobertura"], ["Fecha"],
        ["Estado", "Version_extractor", "Numero_publicaciones"],
        ["Fecha_ultima_consulta"],
    )
    hay_cambios = bool(len(oposiciones_nuevas)) or (
        _huella_dataframe(actuales["Publicaciones"], [c for c in columnas_publicaciones if c != "Fecha_ultimo_analisis"])
        != _huella_dataframe(publicaciones, [c for c in columnas_publicaciones if c != "Fecha_ultimo_analisis"])
    ) or (
        _huella_dataframe(actuales["Cobertura"], [c for c in columnas_cobertura if c != "Fecha_ultima_consulta"])
        != _huella_dataframe(cobertura, [c for c in columnas_cobertura if c != "Fecha_ultima_consulta"])
    )
    conexion = conectar(ruta_bd, readonly=True)
    try:
        version = int(dict(conexion.execute("SELECT clave,valor FROM metadata"))["data_version"])
    finally:
        conexion.close()
    if not hay_cambios:
        return {"cambios": False, "backup": None, "data_version": version}
    backup = crear_backup(ruta_bd, directorio_backup)
    conexion = conectar(ruta_bd)
    try:
        with transaccion(conexion):
            insertar_publicaciones_upsert(conexion, publicaciones)
            insertar_oposiciones(conexion, oposiciones_nuevas)
            actualizar_cobertura_upsert(conexion, cobertura)
            guardar_metadata(conexion, data_version=version + 1)
            if integrity_check(conexion) != ["ok"] or foreign_key_check(conexion):
                raise EspejoSQLiteError("Las invariantes SQLite fallaron antes de COMMIT")
        return {"cambios": True, "backup": str(backup), "data_version": version + 1}
    finally:
        conexion.close()
