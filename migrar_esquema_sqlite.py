"""Migraciones explícitas y auditables de schema SQLite BOE."""

import argparse
import csv
import json
from pathlib import Path
import time

import base_datos
from normalizacion_puestos import normalizar_puesto
from resolucion_geografica import resolver_administracion_geografia


RAIZ = Path(__file__).resolve().parent
RUTA_MUNICIPIOS = RAIZ / "datos" / "municipios_oficial.csv"
RUTA_PROVINCIAS = RAIZ / "datos" / "provincias.csv"
RUTA_MUNICIPIOS_METADATA = RAIZ / "datos" / "municipios_oficial.metadata.json"
RUTA_MUNICIPIOS_TERRITORIOS_INSULARES = RAIZ / "datos" / "municipios_territorios_insulares.v1.json"
RUTA_SEDES_ADMINISTRATIVAS = RAIZ / "datos" / "sedes_administrativas.v1.json"

PROVINCIAS_ANALITICAS = {
    "Mallorca": "Illes Balears", "Menorca": "Illes Balears",
    "Ibiza/Eivissa": "Illes Balears", "Formentera": "Illes Balears",
    "Ibiza-Formentera": "Illes Balears",
    "Gran Canaria": "Las Palmas", "Lanzarote": "Las Palmas",
    "Fuerteventura": "Las Palmas", "Tenerife": "Santa Cruz de Tenerife",
    "La Palma": "Santa Cruz de Tenerife", "La Gomera": "Santa Cruz de Tenerife",
    "El Hierro": "Santa Cruz de Tenerife",
    # municipios_oficial.csv conserva la denominación bilingüe y
    # provincias.csv fija el canon administrativo de esta migración.
    "Araba/Álava": "Álava",
}
CIUDADES_AUTONOMAS = {
    "Ciudad Autónoma de Ceuta": "Ceuta", "Ceuta": "Ceuta",
    "Ciudad Autónoma de Melilla": "Melilla", "Melilla": "Melilla",
}
TEXTOS_PROVINCIA_CIUDAD_AUTONOMA = {
    "Ceuta", "Ciudad Autónoma de Ceuta", "Melilla", "Ciudad Autónoma de Melilla",
}
TERRITORIOS_INSULARES = (
    ('Mallorca', 'ISLA', 'Illes Balears', 'Illes Balears'),
    ('Menorca', 'ISLA', 'Illes Balears', 'Illes Balears'),
    ('Ibiza/Eivissa', 'ISLA', 'Illes Balears', 'Illes Balears'),
    ('Formentera', 'ISLA', 'Illes Balears', 'Illes Balears'),
    ('Gran Canaria', 'ISLA', 'Las Palmas', 'Canarias'),
    ('Lanzarote', 'ISLA', 'Las Palmas', 'Canarias'),
    ('Fuerteventura', 'ISLA', 'Las Palmas', 'Canarias'),
    ('La Graciosa', 'ISLA', 'Las Palmas', 'Canarias'),
    ('Tenerife', 'ISLA', 'Santa Cruz de Tenerife', 'Canarias'),
    ('La Palma', 'ISLA', 'Santa Cruz de Tenerife', 'Canarias'),
    ('La Gomera', 'ISLA', 'Santa Cruz de Tenerife', 'Canarias'),
    ('El Hierro', 'ISLA', 'Santa Cruz de Tenerife', 'Canarias'),
    ('Ibiza-Formentera', 'AGRUPACION_INSULAR_HISTORICA', 'Illes Balears', 'Illes Balears'),
)


def _normalizar(valor):
    """Clave determinista ya empleada por el catálogo geográfico productivo."""
    from mapa_plazas import normalizar_nombre_municipal
    return normalizar_nombre_municipal(str(valor or ""))


def _leer_csv(ruta):
    with Path(ruta).open(encoding="utf-8-sig", newline="") as archivo:
        return list(csv.DictReader(archivo, delimiter=";"))


def _hash(ruta):
    return base_datos.hash_archivo(ruta)


def _nombre_comunidad(valor):
    return CIUDADES_AUTONOMAS.get(str(valor or "").strip(), str(valor or "").strip())


def _provincia_administrativa(valor):
    valor = str(valor or "").strip()
    if valor in CIUDADES_AUTONOMAS:
        return None
    return PROVINCIAS_ANALITICAS.get(valor, valor or None)


def _catalogos_fuente():
    municipios = _leer_csv(RUTA_MUNICIPIOS)
    provincias = _leer_csv(RUTA_PROVINCIAS)
    metadata = json.loads(RUTA_MUNICIPIOS_METADATA.read_text(encoding="utf-8"))
    return municipios, provincias, metadata


def importar_catalogos_administrativos(con):
    """Carga sólo la jerarquía administrativa desde los CSV versionados."""
    municipios, provincias_csv, metadata = _catalogos_fuente()
    fuente_municipios = json.dumps(metadata.get("fuentes", {}), ensure_ascii=False, sort_keys=True)
    version_municipios = metadata.get("referencia_ine") or metadata.get("fecha_generacion")
    catalogos = [
        ("municipios_oficial", version_municipios, fuente_municipios,
         metadata.get("referencia_ine"), _hash(RUTA_MUNICIPIOS)),
        ("provincias", _hash(RUTA_PROVINCIAS), "datos/provincias.csv", None,
         _hash(RUTA_PROVINCIAS)),
    ]
    con.executemany(
        """INSERT INTO catalogos_geograficos(nombre,version,fuente,fecha_referencia,sha256)
           VALUES (?,?,?,?,?)""", catalogos,
    )
    catalogo_municipios = con.execute(
        "SELECT catalogo_id FROM catalogos_geograficos WHERE nombre='municipios_oficial' AND version=?",
        (version_municipios,),
    ).fetchone()[0]
    catalogo_provincias = con.execute(
        "SELECT catalogo_id FROM catalogos_geograficos WHERE nombre='provincias' AND version=?",
        (_hash(RUTA_PROVINCIAS),),
    ).fetchone()[0]

    comunidades = sorted({_nombre_comunidad(f["Comunidad"]) for f in municipios})
    if len(comunidades) != 19:
        raise RuntimeError(f"El catálogo municipal no contiene 19 comunidades/ciudades: {len(comunidades)}")
    con.executemany(
        """INSERT INTO comunidades_autonomas(nombre,nombre_normalizado,es_ciudad_autonoma,catalogo_id)
           VALUES (?,?,?,?)""",
        ((nombre, _normalizar(nombre), int(nombre in {"Ceuta", "Melilla"}), catalogo_municipios)
         for nombre in comunidades),
    )
    comunidades_id = dict(con.execute("SELECT nombre,comunidad_id FROM comunidades_autonomas"))

    filas_provincia = [f for f in provincias_csv if f["Provincia"] not in {"Ceuta", "Melilla"}]
    if len(filas_provincia) != 50:
        raise RuntimeError(f"provincias.csv no produce exactamente 50 provincias: {len(filas_provincia)}")
    por_provincia = {}
    for municipio in municipios:
        provincia = _provincia_administrativa(municipio["Provincia"])
        if provincia:
            por_provincia.setdefault(provincia, set()).add(str(municipio["Codigo_INE"]).zfill(5)[:2])
    datos_provincias = []
    for fila in filas_provincia:
        nombre = fila["Provincia"]
        codigos = por_provincia.get(nombre, set())
        comunidades_provincia = {
            _nombre_comunidad(x["Comunidad"]) for x in municipios
            if _provincia_administrativa(x["Provincia"]) == nombre
        }
        if len(codigos) != 1 or len(comunidades_provincia) != 1:
            raise RuntimeError(f"Provincia no determinista en municipios_oficial.csv: {nombre}")
        comunidad = next(iter(comunidades_provincia))
        datos_provincias.append((next(iter(codigos)), nombre, fila["Provincia_normalizada"],
                                 comunidades_id[comunidad], catalogo_provincias))
    con.executemany(
        """INSERT INTO provincias(provincia_id,nombre,nombre_normalizado,comunidad_id,catalogo_id)
           VALUES (?,?,?,?,?)""", datos_provincias,
    )
    provincias_id = dict(con.execute("SELECT nombre,provincia_id FROM provincias"))
    con.executemany(
        """INSERT INTO municipios(codigo_ine,nombre,nombre_normalizado,provincia_id,comunidad_id,
                                    latitud,longitud,altitud,habitantes,catalogo_id)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        ((str(f["Codigo_INE"]).zfill(5), f["Municipio"], f["Municipio_normalizado"],
          provincias_id.get(_provincia_administrativa(f["Provincia"])),
          comunidades_id[_nombre_comunidad(f["Comunidad"])],
          float(f["Latitud"]) if f["Latitud"] else None,
          float(f["Longitud"]) if f["Longitud"] else None,
          float(f["Altitud"]) if f["Altitud"] else None,
          int(float(f["Habitantes"])) if f["Habitantes"] else None,
          catalogo_municipios)
         for f in municipios),
    )
    return {"municipios_fuente": len(municipios), "metadata_municipios": metadata.get("filas")}


def _poblar_referencias_oposiciones(con):
    """Enlaza sólo nombres canónicos/aliases exactos y provincias ya aprobadas."""
    comunidades = {_normalizar(nombre): ident for nombre, ident in con.execute(
        "SELECT nombre,comunidad_id FROM comunidades_autonomas"
    )}
    provincias = {_normalizar(nombre): ident for nombre, ident in con.execute(
        "SELECT nombre,provincia_id FROM provincias"
    )}
    from mapa_plazas import _variantes_nombre_catalogo
    municipios = {}
    for codigo, nombre, provincia_id in con.execute("SELECT codigo_ine,nombre_normalizado,provincia_id FROM municipios"):
        fila = con.execute("SELECT nombre FROM municipios WHERE codigo_ine=?", (codigo,)).fetchone()
        for variante in _variantes_nombre_catalogo(fila[0]):
            municipios.setdefault((_normalizar(variante), provincia_id), []).append(codigo)
    actualizaciones = []
    for oid, municipio, provincia, comunidad in con.execute(
        "SELECT oposicion_id,municipio,provincia,comunidad_autonoma FROM oposiciones"
    ):
        provincia_admin = _provincia_administrativa(provincia)
        provincia_id = provincias.get(_normalizar(provincia_admin)) if provincia_admin else None
        comunidad_nombre = _nombre_comunidad(comunidad)
        if not comunidad_nombre and provincia_id:
            comunidad_nombre = con.execute(
                "SELECT c.nombre FROM provincias p JOIN comunidades_autonomas c USING(comunidad_id) WHERE p.provincia_id=?",
                (provincia_id,),
            ).fetchone()[0]
        if not comunidad_nombre and provincia in CIUDADES_AUTONOMAS:
            comunidad_nombre = _nombre_comunidad(provincia)
        comunidad_id = comunidades.get(_normalizar(comunidad_nombre)) if comunidad_nombre else None
        candidatos = municipios.get((_normalizar(municipio), provincia_id), []) if municipio else []
        codigo_ine = candidatos[0] if len(candidatos) == 1 else None
        actualizaciones.append((codigo_ine, provincia_id, comunidad_id, oid))
    con.executemany(
        """UPDATE oposiciones SET municipio_codigo_ine=?, provincia_id=?, comunidad_id=?
           WHERE oposicion_id=?""", actualizaciones,
    )


def referencias_administrativas(con, municipio, provincia, comunidad):
    """Devuelve FK administrativas por coincidencias exactas ya catalogadas."""
    provincia_admin = _provincia_administrativa(provincia)
    fila_provincia = con.execute(
        "SELECT provincia_id, comunidad_id FROM provincias WHERE nombre_normalizado=?",
        (_normalizar(provincia_admin),),
    ).fetchone() if provincia_admin else None
    provincia_id = fila_provincia[0] if fila_provincia else None
    comunidad_nombre = _nombre_comunidad(comunidad)
    if not comunidad_nombre and fila_provincia:
        comunidad_id = fila_provincia[1]
    elif comunidad_nombre:
        fila_comunidad = con.execute(
            "SELECT comunidad_id FROM comunidades_autonomas WHERE nombre_normalizado=?",
            (_normalizar(comunidad_nombre),),
        ).fetchone()
        comunidad_id = fila_comunidad[0] if fila_comunidad else None
    elif provincia in CIUDADES_AUTONOMAS:
        fila_comunidad = con.execute(
            "SELECT comunidad_id FROM comunidades_autonomas WHERE nombre_normalizado=?",
            (_normalizar(_nombre_comunidad(provincia)),),
        ).fetchone()
        comunidad_id = fila_comunidad[0] if fila_comunidad else None
    else:
        comunidad_id = None
    codigo_ine = None
    if municipio:
        from mapa_plazas import _variantes_nombre_catalogo
        candidatos = set()
        for variante in _variantes_nombre_catalogo(municipio):
            candidatos.update(x[0] for x in con.execute(
                "SELECT codigo_ine FROM municipios WHERE nombre_normalizado=? AND provincia_id IS ?",
                (_normalizar(variante), provincia_id),
            ))
        if len(candidatos) == 1:
            codigo_ine = candidatos.pop()
    return codigo_ine, provincia_id, comunidad_id


def provincia_administrativa_canon(con, provincia, provincia_id, comunidad_id):
    """Devuelve el texto administrativo canónico sin reinterpretar valores sin FK.

    La FK es la autoridad para las cincuenta provincias. Ceuta y Melilla se
    conservan como ciudades autónomas, por lo que su provincia textual es NULL.
    """
    if provincia_id:
        fila = con.execute("SELECT nombre FROM provincias WHERE provincia_id=?", (provincia_id,)).fetchone()
        if not fila:
            raise RuntimeError(f"provincia_id inexistente: {provincia_id}")
        return fila[0]
    ciudad = con.execute("""SELECT nombre,es_ciudad_autonoma FROM comunidades_autonomas
                          WHERE comunidad_id=?""", (comunidad_id,)).fetchone() if comunidad_id else None
    if ciudad and ciudad[1] and provincia in TEXTOS_PROVINCIA_CIUDAD_AUTONOMA:
        return None
    return provincia


def comunidad_autonoma_canon(con, comunidad, comunidad_id):
    """Sólo canoniza texto cuando la FK identifica una ciudad autónoma."""
    if comunidad_id:
        fila = con.execute("SELECT nombre,es_ciudad_autonoma FROM comunidades_autonomas WHERE comunidad_id=?",
                           (comunidad_id,)).fetchone()
        if fila and fila[1]:
            return fila[0]
    return comunidad


def normalizar_referencias_administrativas(con, municipio, provincia, comunidad):
    """Calcula FK y textos canónicos para una oposición, sin fuzzy matching."""
    codigo_ine, provincia_id, comunidad_id = referencias_administrativas(con, municipio, provincia, comunidad)
    return (codigo_ine, provincia_administrativa_canon(con, provincia, provincia_id, comunidad_id),
            comunidad_autonoma_canon(con, comunidad, comunidad_id), provincia_id, comunidad_id)


def migrar_v4_v5(ruta_bd="datos/boe.db", directorio_backup="backups/sqlite"):
    """Añade geografía administrativa normalizada sin destruir textos históricos."""
    ruta_bd = Path(ruta_bd)
    metadata, columnas = _estado(ruta_bd)
    nuevas = {"municipio_codigo_ine", "provincia_id", "comunidad_id"}
    tablas = set()
    con_estado = base_datos.conectar(ruta_bd, readonly=True)
    try:
        tablas = {x[0] for x in con_estado.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con_estado.close()
    maestras = {"catalogos_geograficos", "comunidades_autonomas", "provincias", "municipios"}
    if metadata.get("schema_version") == "5":
        if not nuevas <= set(columnas) or not maestras <= tablas:
            raise RuntimeError("Metadata v5 sin estructura administrativa")
        return {"actualizada": False, "schema_version": "5", "data_version": metadata["data_version"]}
    if metadata.get("schema_version") != "4" or nuevas & set(columnas) or maestras & tablas:
        raise RuntimeError("La base no es un esquema v4 migrable a v5")
    backup = base_datos.crear_backup(ruta_bd, directorio_backup)
    inicio = time.perf_counter()
    con = base_datos.conectar(ruta_bd)
    try:
        with base_datos.transaccion(con):
            con.executescript("""
                CREATE TABLE catalogos_geograficos (
                    catalogo_id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, version TEXT NOT NULL,
                    fuente TEXT NOT NULL, fecha_referencia TEXT, sha256 TEXT,
                    UNIQUE (nombre, version)
                );
                CREATE TABLE comunidades_autonomas (
                    comunidad_id INTEGER PRIMARY KEY, nombre TEXT NOT NULL UNIQUE,
                    nombre_normalizado TEXT NOT NULL UNIQUE,
                    es_ciudad_autonoma INTEGER NOT NULL CHECK (es_ciudad_autonoma IN (0,1)),
                    catalogo_id INTEGER NOT NULL REFERENCES catalogos_geograficos(catalogo_id) ON DELETE RESTRICT
                );
                CREATE TABLE provincias (
                    provincia_id TEXT PRIMARY KEY, nombre TEXT NOT NULL UNIQUE,
                    nombre_normalizado TEXT NOT NULL UNIQUE,
                    comunidad_id INTEGER NOT NULL REFERENCES comunidades_autonomas(comunidad_id) ON DELETE RESTRICT,
                    catalogo_id INTEGER NOT NULL REFERENCES catalogos_geograficos(catalogo_id) ON DELETE RESTRICT,
                    UNIQUE (provincia_id, comunidad_id)
                );
                CREATE TABLE municipios (
                    codigo_ine TEXT PRIMARY KEY, nombre TEXT NOT NULL, nombre_normalizado TEXT NOT NULL,
                    provincia_id TEXT, comunidad_id INTEGER NOT NULL REFERENCES comunidades_autonomas(comunidad_id) ON DELETE RESTRICT,
                    latitud REAL, longitud REAL, altitud REAL, habitantes INTEGER,
                    catalogo_id INTEGER NOT NULL REFERENCES catalogos_geograficos(catalogo_id) ON DELETE RESTRICT,
                    FOREIGN KEY (provincia_id, comunidad_id) REFERENCES provincias(provincia_id, comunidad_id) ON DELETE RESTRICT,
                    UNIQUE (nombre_normalizado, provincia_id)
                );
                ALTER TABLE oposiciones ADD COLUMN municipio_codigo_ine TEXT REFERENCES municipios(codigo_ine) ON DELETE RESTRICT;
                ALTER TABLE oposiciones ADD COLUMN provincia_id TEXT REFERENCES provincias(provincia_id) ON DELETE RESTRICT;
                ALTER TABLE oposiciones ADD COLUMN comunidad_id INTEGER REFERENCES comunidades_autonomas(comunidad_id) ON DELETE RESTRICT;
                CREATE INDEX ix_municipios_provincia ON municipios(provincia_id);
                CREATE INDEX ix_municipios_comunidad ON municipios(comunidad_id);
                CREATE INDEX ix_oposiciones_municipio_ine ON oposiciones(municipio_codigo_ine);
                CREATE INDEX ix_oposiciones_provincia_id ON oposiciones(provincia_id);
                CREATE INDEX ix_oposiciones_comunidad_id ON oposiciones(comunidad_id);
            """)
            auditoria = importar_catalogos_administrativos(con)
            _poblar_referencias_oposiciones(con)
            base_datos.guardar_metadata(con, data_version=int(metadata["data_version"]) + 1)
            con.execute("UPDATE metadata SET valor='5' WHERE clave='schema_version'")
            if base_datos.integrity_check(con) != ["ok"] or base_datos.foreign_key_check(con):
                raise RuntimeError("La base migrada no supera integridad")
    finally:
        con.close()
    return {"actualizada": True, "backup": str(backup), "schema_version": "5",
            "data_version": str(int(metadata["data_version"]) + 1),
            "segundos": time.perf_counter() - inicio, "auditoria": auditoria}


def _crear_estructura_insular(con):
    con.executescript("""
    CREATE TABLE territorios_insulares (
      territorio_id INTEGER PRIMARY KEY,nombre TEXT NOT NULL UNIQUE,nombre_normalizado TEXT NOT NULL UNIQUE,
      clase TEXT NOT NULL CHECK(clase IN ('ISLA','AGRUPACION_INSULAR_HISTORICA')),
      provincia_id TEXT NOT NULL REFERENCES provincias(provincia_id) ON DELETE RESTRICT,
      comunidad_id INTEGER NOT NULL REFERENCES comunidades_autonomas(comunidad_id) ON DELETE RESTRICT,
      catalogo_id INTEGER NOT NULL REFERENCES catalogos_geograficos(catalogo_id) ON DELETE RESTRICT);
    CREATE TABLE municipios_territorios_insulares (
      codigo_ine TEXT NOT NULL REFERENCES municipios(codigo_ine) ON DELETE RESTRICT,
      territorio_id INTEGER NOT NULL REFERENCES territorios_insulares(territorio_id) ON DELETE RESTRICT,
      catalogo_id INTEGER NOT NULL REFERENCES catalogos_geograficos(catalogo_id) ON DELETE RESTRICT,
      PRIMARY KEY(codigo_ine,territorio_id));
    CREATE TABLE oposiciones_territorios_insulares (
      oposicion_id INTEGER NOT NULL REFERENCES oposiciones(oposicion_id) ON DELETE CASCADE,
      territorio_id INTEGER NOT NULL REFERENCES territorios_insulares(territorio_id) ON DELETE RESTRICT,
      evidencia TEXT NOT NULL,version_resolutor TEXT NOT NULL,PRIMARY KEY(oposicion_id,territorio_id));
    CREATE INDEX ix_territorios_provincia ON territorios_insulares(provincia_id);
    CREATE INDEX ix_mti_territorio ON municipios_territorios_insulares(territorio_id);
    CREATE INDEX ix_oti_territorio ON oposiciones_territorios_insulares(territorio_id);
    """)


def _catalogo_municipios_territorios_insulares():
    """Lee la correspondencia INE→isla publicada con sus fuentes oficiales."""
    datos = json.loads(RUTA_MUNICIPIOS_TERRITORIOS_INSULARES.read_text(encoding="utf-8"))
    if not {"version", "fecha_consulta", "fuentes", "relaciones", "procedencia_por_territorio"} <= set(datos):
        raise RuntimeError("Catálogo insular municipal incompleto")
    return datos


def _cargar_catalogo_municipios_territorios_insulares(con):
    """Carga enlaces INE→isla sin derivar territorios de oposiciones ni geometría."""
    datos = _catalogo_municipios_territorios_insulares()
    territorios = {
        nombre: (ident, provincia_id, comunidad_id, clase)
        for ident, nombre, provincia_id, comunidad_id, clase in con.execute(
            "SELECT territorio_id,nombre,provincia_id,comunidad_id,clase FROM territorios_insulares"
        )
    }
    esperados = []
    for territorio, codigos in datos["relaciones"].items():
        if territorio not in territorios:
            raise RuntimeError(f"Territorio insular desconocido en catálogo: {territorio}")
        if territorios[territorio][3] != "ISLA":
            raise RuntimeError(f"Un municipio no puede relacionarse con {territorio}")
        procedencia = datos["procedencia_por_territorio"].get(territorio)
        if procedencia not in datos["fuentes"]:
            raise RuntimeError(f"Procedencia ausente para {territorio}")
        esperados.extend((str(codigo).zfill(5), territorio, procedencia) for codigo in codigos)
    if len({(codigo, territorio) for codigo, territorio, _ in esperados}) != len(esperados):
        raise RuntimeError("El catálogo insular municipal contiene relaciones duplicadas")

    universo = {
        codigo for codigo, in con.execute("""SELECT m.codigo_ine FROM municipios m
            JOIN provincias p ON p.provincia_id=m.provincia_id
            WHERE p.nombre IN ('Illes Balears','Las Palmas','Santa Cruz de Tenerife')""")
    }
    codigos_catalogo = {codigo for codigo, _, _ in esperados}
    if codigos_catalogo != universo:
        raise RuntimeError("El catálogo insular municipal no cubre exactamente el universo v5")
    for codigo, territorio, _ in esperados:
        fila = con.execute("""SELECT m.provincia_id,m.comunidad_id FROM municipios m
                            WHERE m.codigo_ine=?""", (codigo,)).fetchone()
        _, provincia_id, comunidad_id, _ = territorios[territorio]
        if fila is None or tuple(fila) != (provincia_id, comunidad_id):
            raise RuntimeError(f"Relación municipio-isla incompatible: {codigo} → {territorio}")

    sha = _hash(RUTA_MUNICIPIOS_TERRITORIOS_INSULARES)
    catalogos = {}
    for clave, fuente in datos["fuentes"].items():
        nombre = f"municipios_territorios_insulares_{clave.lower()}"
        version = datos["version"]
        con.execute("""INSERT OR IGNORE INTO catalogos_geograficos(nombre,version,fuente,fecha_referencia,sha256)
                       VALUES (?,?,?,?,?)""", (nombre, version, json.dumps(fuente, ensure_ascii=False, sort_keys=True),
                                                   datos["fecha_consulta"], sha))
        catalogos[clave] = con.execute("SELECT catalogo_id FROM catalogos_geograficos WHERE nombre=? AND version=?",
                                        (nombre, version)).fetchone()[0]
    antes = {(codigo, territorio_id): catalogo_id for codigo, territorio_id, catalogo_id in con.execute(
        "SELECT codigo_ine,territorio_id,catalogo_id FROM municipios_territorios_insulares"
    )}
    enlaces = [(codigo, territorios[territorio][0], catalogos[origen]) for codigo, territorio, origen in esperados]
    esperados_ids = {(codigo, territorio_id): catalogo_id for codigo, territorio_id, catalogo_id in enlaces}
    extras = set(antes) - set(esperados_ids)
    if extras:
        raise RuntimeError("Existen relaciones municipales insulares no versionadas por el catálogo v1")
    nuevos = sum(clave not in antes for clave in esperados_ids)
    modificados = sum(antes.get(clave) not in (None, catalogo_id) for clave, catalogo_id in esperados_ids.items())
    con.executemany("""INSERT INTO municipios_territorios_insulares(codigo_ine,territorio_id,catalogo_id)
                       VALUES (?,?,?) ON CONFLICT(codigo_ine,territorio_id)
                       DO UPDATE SET catalogo_id=excluded.catalogo_id""", enlaces)
    return {"nuevas": nuevos, "modificadas": modificados, "relaciones": len(enlaces)}


def _territorio_seguro(administracion, administracion_normalizada, provincia, evidencia):
    clave_admin = _normalizar(administracion_normalizada or administracion)
    cerradas = {
        'mancomunidad des raiguer': 'Mallorca',
        'consorcio de la ciudad romana de pollentia': 'Mallorca',
        'consejo insular de ibiza y formentera': 'Ibiza-Formentera',
        'consejo insular de ibiza formentera': 'Ibiza-Formentera',
        'ayuntamiento de mao mahon': 'Menorca',
        'ayuntamiento de santa eulalia del rio': 'Ibiza/Eivissa',
        'ayuntamiento de palma de mallorca patronato municipal de escuelas infantiles': 'Mallorca',
        'ayuntamiento de sant antoni de postmany': 'Ibiza/Eivissa',
        'ayuntamiento de sant antony de portmany': 'Ibiza/Eivissa',
    }
    if clave_admin in cerradas:
        return cerradas[clave_admin], 'REGLA_APROBADA'
    if evidencia in {'TERRITORIO_INSULAR', 'ISLA_PARENTESIS'} and provincia in dict((x[0], x) for x in TERRITORIOS_INSULARES):
        return provincia, evidencia
    return None


def relaciones_territoriales_seguras_pendientes(con):
    """Obtiene sólo enlaces de oposiciones sustentados por reglas cerradas."""
    territorios = dict(con.execute("SELECT nombre,territorio_id FROM territorios_insulares"))
    existentes = set(con.execute("SELECT oposicion_id,territorio_id FROM oposiciones_territorios_insulares"))
    pendientes = []
    for oid, admin, normalizada, provincia, evidencia, version in con.execute(
        """SELECT oposicion_id,administracion,administracion_normalizada,provincia,
                  evidencia_geografica,version_resolutor FROM oposiciones"""
    ):
        dato = _territorio_seguro(admin, normalizada, provincia, evidencia)
        if not dato and _normalizar(normalizada or admin) in {
            'mancomunidad migjorn de mallorca', 'mancomunidad pla de mallorca',
        }:
            # Decisión de etapa 4: denominaciones completas, no una búsqueda
            # por subcadena de "Mallorca".
            dato = ('Mallorca', 'MANCOMUNIDAD_TERRITORIO')
        if dato and (oid, territorios[dato[0]]) not in existentes:
            pendientes.append((oid, territorios[dato[0]], dato[1], version or "geografia-v1"))
    return pendientes


def migrar_v5_territorios_insulares(ruta_bd="datos/boe.db", directorio_backup="backups/sqlite"):
    ruta_bd=Path(ruta_bd); metadata,columnas=_estado(ruta_bd)
    if metadata.get('schema_version') != '5': raise RuntimeError('La etapa insular requiere schema_version 5')
    con=base_datos.conectar(ruta_bd,readonly=True)
    try: tablas={x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally: con.close()
    requeridas={'territorios_insulares','municipios_territorios_insulares','oposiciones_territorios_insulares'}
    if requeridas <= tablas:
        resultado = migrar_v5_catalogo_municipios_territorios_insulares(ruta_bd, directorio_backup)
        if resultado["actualizada"]:
            return resultado
        resultado = migrar_v5_provincias_administrativas(ruta_bd, directorio_backup)
        if resultado["actualizada"]:
            return resultado
        resultado = migrar_v5_correcciones_geograficas_aprobadas(ruta_bd, directorio_backup)
        if resultado["actualizada"]:
            return resultado
        resultado = migrar_v5_sedes_administrativas(ruta_bd, directorio_backup)
        if resultado["actualizada"]: return resultado
        resultado = migrar_v5_alias_sedes_administrativas(ruta_bd, directorio_backup)
        return resultado if resultado["actualizada"] else migrar_v5_universidades(ruta_bd, directorio_backup)
    if tablas & requeridas: raise RuntimeError('Estructura insular v5 incompleta')
    backup=base_datos.crear_backup(ruta_bd,directorio_backup); inicio=time.perf_counter(); con=base_datos.conectar(ruta_bd)
    try:
      with base_datos.transaccion(con):
        _crear_estructura_insular(con)
        version='decisiones-insulares-v1'; fuente='Decisiones manuales aprobadas; relación Teguise–La Graciosa aprobada'
        con.execute("INSERT INTO catalogos_geograficos(nombre,version,fuente) VALUES (?,?,?)",('territorios_insulares',version,fuente))
        catalogo_id=con.execute("SELECT catalogo_id FROM catalogos_geograficos WHERE nombre=? AND version=?",('territorios_insulares',version)).fetchone()[0]
        prov=dict(con.execute('SELECT nombre,provincia_id FROM provincias')); com=dict(con.execute('SELECT nombre,comunidad_id FROM comunidades_autonomas'))
        con.executemany('INSERT INTO territorios_insulares(nombre,nombre_normalizado,clase,provincia_id,comunidad_id,catalogo_id) VALUES (?,?,?,?,?,?)',
          ((_n,_normalizar(_n),_cl,prov[_p],com[_c],catalogo_id) for _n,_cl,_p,_c in TERRITORIOS_INSULARES))
        terr=dict(con.execute('SELECT nombre,territorio_id FROM territorios_insulares'))
        con.executemany('INSERT INTO municipios_territorios_insulares VALUES (?,?,?)',(('35024',terr['Lanzarote'],catalogo_id),('35024',terr['La Graciosa'],catalogo_id)))
        enlaces=[]
        for oid,admin,normalizada,provincia,evidencia,version_res in con.execute('SELECT oposicion_id,administracion,administracion_normalizada,provincia,evidencia_geografica,version_resolutor FROM oposiciones'):
          dato=_territorio_seguro(admin,normalizada,provincia,evidencia)
          if dato: enlaces.append((oid,terr[dato[0]],dato[1],version_res or 'geografia-v1'))
        con.executemany('INSERT INTO oposiciones_territorios_insulares VALUES (?,?,?,?)',enlaces)
        base_datos.guardar_metadata(con,data_version=int(metadata['data_version'])+1)
        if base_datos.integrity_check(con)!=['ok'] or base_datos.foreign_key_check(con): raise RuntimeError('Falla integridad insular')
    finally: con.close()
    return {'actualizada':True,'backup':str(backup),'schema_version':'5','data_version':str(int(metadata['data_version'])+1),'segundos':time.perf_counter()-inicio,'oposiciones_insulares':len(enlaces),'municipios_territorios':2}


def migrar_v5_catalogo_municipios_territorios_insulares(ruta_bd="datos/boe.db", directorio_backup="backups/sqlite"):
    """Tercera etapa v5: completa el catálogo oficial municipio↔territorio insular."""
    ruta_bd = Path(ruta_bd)
    metadata, _ = _estado(ruta_bd)
    if metadata.get("schema_version") != "5":
        raise RuntimeError("El catálogo municipal insular requiere schema_version 5")
    con = base_datos.conectar(ruta_bd, readonly=True)
    try:
        tablas = {x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        requeridas = {"territorios_insulares", "municipios_territorios_insulares", "oposiciones_territorios_insulares"}
        if not requeridas <= tablas:
            raise RuntimeError("La tercera etapa requiere la estructura insular v5")
        # Ejecutamos la misma validación/cálculo sin publicar cambios para no crear
        # copia de seguridad ni alterar data_version cuando ya está al día.
        datos = _catalogo_municipios_territorios_insulares()
        territorios = dict(con.execute("SELECT nombre,territorio_id FROM territorios_insulares"))
        actuales = {(codigo, territorio_id) for codigo, territorio_id in con.execute(
            "SELECT codigo_ine,territorio_id FROM municipios_territorios_insulares"
        )}
        esperados = {(str(codigo).zfill(5), territorios[nombre])
                     for nombre, codigos in datos["relaciones"].items() for codigo in codigos}
        al_dia = actuales == esperados and con.execute(
            "SELECT count(*) FROM catalogos_geograficos WHERE nombre LIKE 'municipios_territorios_insulares_%' AND version=?",
            (datos["version"],),
        ).fetchone()[0] == len(datos["fuentes"])
    finally:
        con.close()
    if al_dia:
        return {"actualizada": False, "schema_version": "5", "data_version": metadata["data_version"]}

    backup = base_datos.crear_backup(ruta_bd, directorio_backup)
    inicio = time.perf_counter()
    con = base_datos.conectar(ruta_bd)
    try:
        with base_datos.transaccion(con):
            auditoria = _cargar_catalogo_municipios_territorios_insulares(con)
            base_datos.guardar_metadata(con, data_version=int(metadata["data_version"]) + 1)
            if base_datos.integrity_check(con) != ["ok"] or base_datos.foreign_key_check(con):
                raise RuntimeError("La carga del catálogo insular no supera integridad")
    finally:
        con.close()
    return {"actualizada": True, "backup": str(backup), "schema_version": "5",
            "data_version": str(int(metadata["data_version"]) + 1), "segundos": time.perf_counter() - inicio,
            "auditoria": auditoria}


def migrar_v5_provincias_administrativas(ruta_bd="datos/boe.db", directorio_backup="backups/sqlite"):
    """Etapa 4 v5: el texto provincia refleja exclusivamente la FK administrativa."""
    ruta_bd = Path(ruta_bd)
    metadata, _ = _estado(ruta_bd)
    if metadata.get("schema_version") != "5":
        raise RuntimeError("La normalización provincial requiere schema_version 5")
    con = base_datos.conectar(ruta_bd, readonly=True)
    try:
        cambios = []
        for oid, provincia, comunidad, provincia_id, comunidad_id in con.execute(
            """SELECT oposicion_id,provincia,comunidad_autonoma,provincia_id,comunidad_id
               FROM oposiciones"""
        ):
            provincia_nueva = provincia_administrativa_canon(con, provincia, provincia_id, comunidad_id)
            comunidad_nueva = comunidad_autonoma_canon(con, comunidad, comunidad_id)
            if (provincia_nueva, comunidad_nueva) != (provincia, comunidad):
                cambios.append((provincia_nueva, comunidad_nueva, oid))
        enlaces = relaciones_territoriales_seguras_pendientes(con)
    finally:
        con.close()
    if not cambios and not enlaces:
        return {"actualizada": False, "schema_version": "5", "data_version": metadata["data_version"]}
    backup = base_datos.crear_backup(ruta_bd, directorio_backup)
    inicio = time.perf_counter()
    con = base_datos.conectar(ruta_bd)
    try:
        with base_datos.transaccion(con):
            con.executemany("UPDATE oposiciones SET provincia=?,comunidad_autonoma=? WHERE oposicion_id=?", cambios)
            con.executemany("INSERT OR IGNORE INTO oposiciones_territorios_insulares VALUES (?,?,?,?)", enlaces)
            base_datos.guardar_metadata(con, data_version=int(metadata["data_version"]) + 1)
            if base_datos.integrity_check(con) != ["ok"] or base_datos.foreign_key_check(con):
                raise RuntimeError("La normalización provincial no supera integridad")
    finally:
        con.close()
    return {"actualizada": True, "backup": str(backup), "schema_version": "5",
            "data_version": str(int(metadata["data_version"]) + 1), "segundos": time.perf_counter() - inicio,
            "filas_modificadas": len(cambios), "relaciones_territorios_nuevas": len(enlaces)}


def migrar_v5_correcciones_geograficas_aprobadas(ruta_bd="datos/boe.db", directorio_backup="backups/sqlite"):
    """Aplica sólo correcciones geográficas manuales identificadas por administración exacta."""
    ruta_bd = Path(ruta_bd)
    metadata, _ = _estado(ruta_bd)
    if metadata.get("schema_version") != "5":
        raise RuntimeError("Las correcciones geográficas aprobadas requieren schema_version 5")
    from resolucion_geografica import resolver_administracion_geografia
    administraciones = ("Consejo de Seguridad Nuclear", "Consorcio de Teatro Fortuny")
    con = base_datos.conectar(ruta_bd, readonly=True)
    try:
        cambios = []
        for fila in con.execute(
            """SELECT oposicion_id,administracion,puesto,ambito,tipo_entidad,municipio,municipio_codigo_ine,
                      provincia,provincia_id,comunidad_autonoma,comunidad_id,confianza_geografica,evidencia_geografica
               FROM oposiciones WHERE administracion IN (?,?)""", administraciones,
        ):
            oid, administracion, puesto, *actual = fila
            actual = tuple(actual)
            r = resolver_administracion_geografia(administracion, puesto)
            codigo, provincia, comunidad, provincia_id, comunidad_id = normalizar_referencias_administrativas(
                con, r.municipio, r.provincia, r.comunidad_autonoma,
            )
            nuevo = (r.ambito, r.tipo_entidad, r.municipio, codigo, provincia, provincia_id,
                     comunidad, comunidad_id, r.confianza, r.evidencia)
            if nuevo != actual:
                cambios.append((*nuevo, oid))
    finally:
        con.close()
    if not cambios:
        return {"actualizada": False, "schema_version": "5", "data_version": metadata["data_version"]}
    backup = base_datos.crear_backup(ruta_bd, directorio_backup)
    inicio = time.perf_counter()
    con = base_datos.conectar(ruta_bd)
    try:
        with base_datos.transaccion(con):
            con.executemany("""UPDATE oposiciones SET ambito=?,tipo_entidad=?,municipio=?,municipio_codigo_ine=?,
                               provincia=?,provincia_id=?,comunidad_autonoma=?,comunidad_id=?,
                               confianza_geografica=?,evidencia_geografica=? WHERE oposicion_id=?""", cambios)
            base_datos.guardar_metadata(con, data_version=int(metadata["data_version"]) + 1)
            if base_datos.integrity_check(con) != ["ok"] or base_datos.foreign_key_check(con):
                raise RuntimeError("Las correcciones geográficas aprobadas no superan integridad")
    finally:
        con.close()
    return {"actualizada": True, "backup": str(backup), "schema_version": "5",
            "data_version": str(int(metadata["data_version"]) + 1), "segundos": time.perf_counter() - inicio,
            "filas_modificadas": len(cambios)}


def _catalogo_sedes_administrativas():
    datos = json.loads(RUTA_SEDES_ADMINISTRATIVAS.read_text(encoding="utf-8"))
    obligatorias = {"administracion", "municipio_codigo_ine", "familia_administrativa", "tipo_sede", "confianza", "fuente"}
    if not isinstance(datos.get("sedes"), list) or not datos.get("version"):
        raise RuntimeError("El catálogo de sedes administrativas no tiene formato válido")
    vistos = set()
    for fila in datos["sedes"]:
        if not obligatorias <= set(fila):
            raise RuntimeError("Una sede administrativa carece de campos obligatorios")
        clave = _normalizar(fila["administracion"])
        if clave in vistos:
            raise RuntimeError(f"Sede administrativa duplicada: {fila['administracion']}")
        vistos.add(clave)
        if fila["tipo_sede"] not in {"INSTITUCIONAL", "TERRITORIAL"} or fila["confianza"] not in {"ALTA", "MEDIA"}:
            raise RuntimeError(f"Clasificación no válida para sede: {fila['administracion']}")
    return datos


def _crear_estructura_sedes_administrativas(con):
    con.executescript("""
        CREATE TABLE IF NOT EXISTS sedes_administraciones (
            sede_id INTEGER PRIMARY KEY,
            administracion_canonica TEXT NOT NULL,
            administracion_normalizada TEXT NOT NULL UNIQUE,
            municipio_codigo_ine TEXT NOT NULL REFERENCES municipios(codigo_ine) ON DELETE RESTRICT,
            familia_administrativa TEXT,
            tipo_sede TEXT NOT NULL CHECK (tipo_sede IN ('INSTITUCIONAL', 'TERRITORIAL')),
            confianza TEXT NOT NULL CHECK (confianza IN ('ALTA', 'MEDIA')),
            evidencia TEXT NOT NULL CHECK (evidencia = 'SEDE_ADMINISTRATIVA_CATALOGADA'),
            catalogo_id INTEGER NOT NULL REFERENCES catalogos_geograficos(catalogo_id) ON DELETE RESTRICT,
            vigente_desde TEXT,
            vigente_hasta TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_sedes_municipio ON sedes_administraciones(municipio_codigo_ine);
    """)


def migrar_v5_sedes_administrativas(ruta_bd="datos/boe.db", directorio_backup="backups/sqlite"):
    """Sexta etapa v5: catálogo relacional y backfill exacto de sedes institucionales."""
    ruta_bd = Path(ruta_bd)
    metadata, _ = _estado(ruta_bd)
    if metadata.get("schema_version") != "5":
        raise RuntimeError("Las sedes administrativas requieren schema_version 5")
    datos = _catalogo_sedes_administrativas()
    con = base_datos.conectar(ruta_bd, readonly=True)
    try:
        tablas = {fila[0] for fila in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        actuales = [] if "sedes_administraciones" not in tablas else list(con.execute(
            "SELECT administracion_normalizada,municipio_codigo_ine,familia_administrativa,tipo_sede,confianza FROM sedes_administraciones"
        ))
        esperadas = sorted((
            _normalizar(f["administracion"]), str(f["municipio_codigo_ine"]).zfill(5),
            f["familia_administrativa"], f["tipo_sede"], f["confianza"],
        ) for f in datos["sedes"])
        catalogo = con.execute(
            "SELECT catalogo_id FROM catalogos_geograficos WHERE nombre=? AND version=?",
            ("sedes_administrativas", datos["version"]),
        ).fetchone()
        al_dia = sorted(actuales) == esperadas and catalogo is not None
        cambios = []
        if not al_dia:
            from resolucion_geografica import resolver_administracion_geografia
            candidatas = {_normalizar(f["administracion"]) for f in datos["sedes"] if f["tipo_sede"] == "INSTITUCIONAL"}
            candidatas.update({
                _normalizar("Comunidad Autónoma de Andalucía"), _normalizar("Comunidad Autónoma de Aragón"),
                _normalizar("Comunidad Autónoma del Principado de Asturias"), _normalizar("Comunidad Autónoma de Canarias"),
                _normalizar("Comunidad Autónoma de Cantabria"), _normalizar("Comunidad Autónoma de Castilla-La Mancha"),
                _normalizar("Comunidad Autónoma de Cataluña"), _normalizar("Comunidad Autónoma de Extremadura"),
                _normalizar("Comunidad Autónoma de Galicia"), _normalizar("Comunidad Autónoma de La Rioja"),
                _normalizar("Comunidad Autónoma de las Illes Balears"), _normalizar("Comunidad Autónoma de la Región de Murcia"),
                _normalizar("Comunidad Autónoma del País Vasco"), _normalizar("Comunidad de Madrid"),
                _normalizar("Comunidad Foral de Navarra"),
            })
            for fila in con.execute("""SELECT oposicion_id,administracion,puesto,administracion_normalizada,ambito,tipo_entidad,
                    municipio,municipio_codigo_ine,provincia,provincia_id,comunidad_autonoma,comunidad_id,
                    confianza_geografica,evidencia_geografica,version_resolutor FROM oposiciones"""):
                oid, administracion, puesto, *actual = fila
                if _normalizar(administracion) not in candidatas:
                    continue
                r = resolver_administracion_geografia(administracion, puesto)
                if r.evidencia not in {"SEDE_ADMINISTRATIVA_CATALOGADA", "COMUNIDAD_ADMINISTRACION_EXACTA"}:
                    continue
                codigo, provincia, comunidad, provincia_id, comunidad_id = normalizar_referencias_administrativas(
                    con, r.municipio, r.provincia, r.comunidad_autonoma,
                )
                nuevo = (r.administracion_normalizada, r.ambito, r.tipo_entidad, r.municipio, codigo, provincia,
                         provincia_id, comunidad, comunidad_id, r.confianza, r.evidencia, r.version_catalogo)
                if nuevo != tuple(actual):
                    cambios.append((*nuevo, oid))
    finally:
        con.close()
    if al_dia:
        return {"actualizada": False, "schema_version": "5", "data_version": metadata["data_version"]}
    backup = base_datos.crear_backup(ruta_bd, directorio_backup)
    inicio = time.perf_counter()
    con = base_datos.conectar(ruta_bd)
    try:
        with base_datos.transaccion(con):
            _crear_estructura_sedes_administrativas(con)
            con.execute("DELETE FROM sedes_administraciones")
            con.execute("DELETE FROM catalogos_geograficos WHERE nombre=? AND version=?", ("sedes_administrativas", datos["version"]))
            fuente = json.dumps({"archivo": str(RUTA_SEDES_ADMINISTRATIVAS.relative_to(RAIZ)), "fuentes": [f["fuente"] for f in datos["sedes"]]}, ensure_ascii=False, sort_keys=True)
            con.execute("""INSERT INTO catalogos_geograficos(nombre,version,fuente,fecha_referencia,sha256)
                         VALUES (?,?,?,?,?)""", ("sedes_administrativas", datos["version"], fuente,
                                                      datos.get("fecha_referencia"), _hash(RUTA_SEDES_ADMINISTRATIVAS)))
            catalogo_id = con.execute("SELECT catalogo_id FROM catalogos_geograficos WHERE nombre=? AND version=?", ("sedes_administrativas", datos["version"])).fetchone()[0]
            municipios = {fila[0] for fila in con.execute("SELECT codigo_ine FROM municipios")}
            for fila in datos["sedes"]:
                codigo = str(fila["municipio_codigo_ine"]).zfill(5)
                if codigo not in municipios:
                    raise RuntimeError(f"Municipio inexistente para sede: {fila['administracion']}")
                con.execute("""INSERT INTO sedes_administraciones(administracion_canonica,administracion_normalizada,
                             municipio_codigo_ine,familia_administrativa,tipo_sede,confianza,evidencia,catalogo_id,
                             vigente_desde,vigente_hasta) VALUES (?,?,?,?,?,?, 'SEDE_ADMINISTRATIVA_CATALOGADA',?,?,?)""",
                            (fila["administracion"], _normalizar(fila["administracion"]), codigo,
                             fila["familia_administrativa"], fila["tipo_sede"], fila["confianza"], catalogo_id,
                             fila.get("vigente_desde"), fila.get("vigente_hasta")))
            con.executemany("""UPDATE oposiciones SET administracion_normalizada=?,ambito=?,tipo_entidad=?,municipio=?,
                              municipio_codigo_ine=?,provincia=?,provincia_id=?,comunidad_autonoma=?,comunidad_id=?,
                              confianza_geografica=?,evidencia_geografica=?,version_resolutor=? WHERE oposicion_id=?""", cambios)
            base_datos.guardar_metadata(con, data_version=int(metadata["data_version"]) + 1)
            if base_datos.integrity_check(con) != ["ok"] or base_datos.foreign_key_check(con):
                raise RuntimeError("El catálogo de sedes no supera integridad")
    finally:
        con.close()
    return {"actualizada": True, "backup": str(backup), "schema_version": "5",
            "data_version": str(int(metadata["data_version"]) + 1), "segundos": time.perf_counter() - inicio,
            "sedes_importadas": len(datos["sedes"]), "filas_modificadas": len(cambios)}


def migrar_v5_alias_sedes_administrativas(ruta_bd="datos/boe.db", directorio_backup="backups/sqlite"):
    """Séptima etapa v5: denominaciones históricas exactas → sede canónica."""
    ruta_bd = Path(ruta_bd); metadata, _ = _estado(ruta_bd); datos = _catalogo_sedes_administrativas()
    aliases = datos.get("alias_sedes", [])
    con = base_datos.conectar(ruta_bd, readonly=True)
    try:
        tablas = {x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        actuales = [] if "alias_sedes_administraciones" not in tablas else list(con.execute(
            "SELECT denominacion_normalizada,tipo_relacion,confianza FROM alias_sedes_administraciones"))
        esperados = sorted((_normalizar(x["denominacion"]), x["tipo_relacion"], x["confianza"]) for x in aliases)
        if sorted(actuales) == esperados:
            return {"actualizada": False, "schema_version": "5", "data_version": metadata["data_version"]}
        from resolucion_geografica import resolver_administracion_geografia
        cambios = []
        claves = {_normalizar(x["denominacion"]) for x in aliases}
        for fila in con.execute("""SELECT oposicion_id,administracion,puesto,administracion_normalizada,ambito,tipo_entidad,
                municipio,municipio_codigo_ine,provincia,provincia_id,comunidad_autonoma,comunidad_id,
                confianza_geografica,evidencia_geografica,version_resolutor FROM oposiciones"""):
            oid, administracion, puesto, *actual = fila
            if _normalizar(administracion) not in claves:
                continue
            r = resolver_administracion_geografia(administracion, puesto)
            codigo, provincia, comunidad, provincia_id, comunidad_id = normalizar_referencias_administrativas(con, r.municipio, r.provincia, r.comunidad_autonoma)
            nuevo = (r.administracion_normalizada, r.ambito, r.tipo_entidad, r.municipio, codigo, provincia, provincia_id,
                     comunidad, comunidad_id, r.confianza, r.evidencia, r.version_catalogo)
            if nuevo != tuple(actual): cambios.append((*nuevo, oid))
    finally: con.close()
    backup = base_datos.crear_backup(ruta_bd, directorio_backup); inicio = time.perf_counter(); con = base_datos.conectar(ruta_bd)
    try:
        with base_datos.transaccion(con):
            con.executescript("""CREATE TABLE IF NOT EXISTS alias_sedes_administraciones (
                alias_id INTEGER PRIMARY KEY, sede_id INTEGER NOT NULL REFERENCES sedes_administraciones(sede_id) ON DELETE RESTRICT,
                denominacion TEXT NOT NULL, denominacion_normalizada TEXT NOT NULL UNIQUE,
                tipo_relacion TEXT NOT NULL CHECK (tipo_relacion IN ('ACTUAL','DENOMINACION_HISTORICA','CAMBIO_DENOMINACION','REORGANIZACION')),
                fecha_desde TEXT, fecha_hasta TEXT, fuente TEXT NOT NULL,
                confianza TEXT NOT NULL CHECK (confianza IN ('ALTA','MEDIA')));
                CREATE INDEX IF NOT EXISTS ix_alias_sedes_sede ON alias_sedes_administraciones(sede_id);""")
            con.execute("DELETE FROM alias_sedes_administraciones")
            sedes = dict(con.execute("SELECT administracion_normalizada,sede_id FROM sedes_administraciones"))
            for alias in aliases:
                sede_id = sedes.get(_normalizar(alias["sede"]))
                if sede_id is None: raise RuntimeError(f"Sede canónica ausente: {alias['sede']}")
                con.execute("""INSERT INTO alias_sedes_administraciones(sede_id,denominacion,denominacion_normalizada,
                    tipo_relacion,fecha_desde,fecha_hasta,fuente,confianza) VALUES (?,?,?,?,?,?,?,?)""",
                    (sede_id, alias["denominacion"], _normalizar(alias["denominacion"]), alias["tipo_relacion"],
                     alias.get("fecha_desde"), alias.get("fecha_hasta"), alias["fuente"], alias["confianza"]))
            con.executemany("""UPDATE oposiciones SET administracion_normalizada=?,ambito=?,tipo_entidad=?,municipio=?,municipio_codigo_ine=?,provincia=?,provincia_id=?,comunidad_autonoma=?,comunidad_id=?,confianza_geografica=?,evidencia_geografica=?,version_resolutor=? WHERE oposicion_id=?""", cambios)
            base_datos.guardar_metadata(con, data_version=int(metadata["data_version"]) + 1)
            if base_datos.integrity_check(con) != ["ok"] or base_datos.foreign_key_check(con): raise RuntimeError("Los alias de sedes no superan integridad")
    finally: con.close()
    return {"actualizada": True, "backup": str(backup), "schema_version": "5", "data_version": str(int(metadata["data_version"])+1), "segundos": time.perf_counter()-inicio, "alias_importados": len(aliases), "filas_modificadas": len(cambios)}


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


def migrar_v5_universidades(ruta_bd="datos/boe.db", directorio_backup="backups/sqlite"):
    """Octava etapa v5: catálogo relacional universitario y recuperación segura."""
    from resolucion_universidades import catalogo, detectar
    ruta_bd=Path(ruta_bd); metadata,columnas=_estado(ruta_bd); datos,indice=catalogo()
    con=base_datos.conectar(ruta_bd,readonly=True)
    try:
        tablas={x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        al_dia={'universidades','alias_universidades'} <= tablas and 'universidad_id' in columnas
    finally: con.close()
    if al_dia: return {"actualizada":False,"schema_version":"5","data_version":metadata['data_version']}
    backup=base_datos.crear_backup(ruta_bd,directorio_backup); inicio=time.perf_counter(); con=base_datos.conectar(ruta_bd)
    try:
      with base_datos.transaccion(con):
        con.executescript("""CREATE TABLE universidades (universidad_id INTEGER PRIMARY KEY,nombre TEXT NOT NULL,nombre_normalizado TEXT NOT NULL UNIQUE,municipio_codigo_ine TEXT REFERENCES municipios(codigo_ine) ON DELETE RESTRICT,catalogo_id INTEGER NOT NULL REFERENCES catalogos_geograficos(catalogo_id) ON DELETE RESTRICT); CREATE TABLE alias_universidades (alias_id INTEGER PRIMARY KEY,universidad_id INTEGER NOT NULL REFERENCES universidades(universidad_id) ON DELETE RESTRICT,denominacion TEXT NOT NULL,denominacion_normalizada TEXT NOT NULL UNIQUE); ALTER TABLE oposiciones ADD COLUMN universidad_id INTEGER REFERENCES universidades(universidad_id) ON DELETE RESTRICT; CREATE INDEX ix_oposiciones_universidad ON oposiciones(universidad_id);""")
        con.execute("INSERT INTO catalogos_geograficos(nombre,version,fuente) VALUES (?,?,?)",('universidades',datos['version'],str(RUTA_SEDES_ADMINISTRATIVAS.parent/'universidades.v1.json')))
        cid=con.execute("SELECT catalogo_id FROM catalogos_geograficos WHERE nombre=? AND version=?",('universidades',datos['version'])).fetchone()[0]
        for u in datos['universidades']:
          con.execute("INSERT INTO universidades(nombre,nombre_normalizado,municipio_codigo_ine,catalogo_id) VALUES (?,?,?,?)",(u['nombre'],_normalizar(u['nombre']),u.get('municipio_codigo_ine'),cid)); uid=con.execute("SELECT universidad_id FROM universidades WHERE nombre_normalizado=?",(_normalizar(u['nombre']),)).fetchone()[0]
          for a in u.get('aliases',[]): con.execute("INSERT INTO alias_universidades(universidad_id,denominacion,denominacion_normalizada) VALUES (?,?,?)",(uid,a,_normalizar(a)))
        ids=dict(con.execute("SELECT nombre,universidad_id FROM universidades")); filas=list(con.execute("SELECT oposicion_id,publicacion_id,puesto,escala FROM oposiciones WHERE administracion='Universidades'")); por={}
        for oid,pid,puesto,escala in filas:
          u=detectar((puesto or '')+' '+(escala or ''),indice)
          if u: por.setdefault(pid,set()).add(u)
        cambios=[]
        for oid,pid,puesto,escala in filas:
          u=detectar((puesto or '')+' '+(escala or ''),indice); evidencia='UNIVERSIDAD_TEXTO_EXPLICITO' if u else ''
          if not u and len(por.get(pid,set()))==1: u=next(iter(por[pid])); evidencia='UNIVERSIDAD_PROPAGADA_PUBLICACION'
          if not u: continue
          codigo=con.execute("SELECT municipio_codigo_ine FROM universidades WHERE universidad_id=?",(ids[u],)).fetchone()[0]
          if codigo:
            m=con.execute("SELECT nombre,provincia_id,comunidad_id FROM municipios WHERE codigo_ine=?",(codigo,)).fetchone(); p=con.execute("SELECT nombre FROM provincias WHERE provincia_id=?",(m[1],)).fetchone()[0]; ca=con.execute("SELECT nombre FROM comunidades_autonomas WHERE comunidad_id=?",(m[2],)).fetchone()[0]
            cambios.append((ids[u],'UNIVERSITARIO','UNIVERSIDAD',m[0],codigo,p,m[1],ca,m[2],'ALTA',evidencia,oid))
          else: cambios.append((ids[u],'UNIVERSITARIO','UNIVERSIDAD',None,None,None,None,None,None,'ALTA',evidencia,oid))
        con.executemany("UPDATE oposiciones SET universidad_id=?,ambito=?,tipo_entidad=?,municipio=?,municipio_codigo_ine=?,provincia=?,provincia_id=?,comunidad_autonoma=?,comunidad_id=?,confianza_geografica=?,evidencia_geografica=? WHERE oposicion_id=?",cambios)
        base_datos.guardar_metadata(con,data_version=int(metadata['data_version'])+1)
        if base_datos.integrity_check(con) != ["ok"] or base_datos.foreign_key_check(con):
          raise RuntimeError("La migración universitaria no supera integridad")
    finally: con.close()
    return {'actualizada':True,'backup':str(backup),'schema_version':'5','data_version':str(int(metadata['data_version'])+1),'universidades':len(datos['universidades']),'filas_modificadas':len(cambios),'segundos':time.perf_counter()-inicio}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-datos", default="datos/boe.db")
    parser.add_argument("--directorio-backup", default="backups/sqlite")
    args = parser.parse_args(argv)
    version = _estado(args.base_datos)[0].get("schema_version")
    funciones = {"2": migrar_v2_v3, "3": migrar_v3_v4, "4": migrar_v4_v5, "5": migrar_v5_territorios_insulares}
    if version not in funciones:
        raise RuntimeError(f"No hay migración disponible desde schema_version {version!r}")
    print(json.dumps(funciones[version](args.base_datos, args.directorio_backup), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
