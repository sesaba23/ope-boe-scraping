"""Motor reutilizable de exportación funcional de la base SQLite."""
from __future__ import annotations

from datetime import datetime
import csv
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import time
import zipfile

import pandas as pd

import base_datos
import consultas_boe
from migrar_excel_sqlite import _fingerprint, _registros_excel


CONTRATOS = {
    "Búsquedas": ("SELECT codigo FROM busquedas ORDER BY codigo", ["Código"]),
    "Oposiciones": ("", ["Oposicion_ID", "Publicacion_ID", "Fecha_boe", "Fecha_boe_original", "Puesto", "Puesto_normalizado", "Num_plazas", "Administración", "Administración_normalizada", "Ambito", "Tipo_entidad", "Comunidad_Autónoma", "Provincia", "Municipio", "Sistema", "Turno", "Escala", "Subescala", "Clase", "Publicación", "Latitud", "Longitud", "Habitantes", "Version_extractor", "Fecha_analisis", "Confianza_geografica", "Evidencia_geografica", "Version_resolutor", "Enlace"]),
    "Log-errores": ("SELECT fecha,tipo_error,enlace_web FROM log_errores ORDER BY error_id", ["Fecha", "Tipo de error", "Enlace Web"]),
    "Publicaciones": ("""SELECT publicacion_id,enlace,fecha_boe_original,titulo_original,fecha_ultimo_analisis,version_extractor,estado_analisis,coincidencias,departamento_boe,administracion_resuelta,familia_administrativa,estado_resolucion,metodo_resolucion,confianza_resolucion,version_resolucion FROM publicaciones ORDER BY fecha_boe,publicacion_id""", ["Publicacion_ID", "Enlace", "Fecha_BOE", "Titulo_original", "Fecha_ultimo_analisis", "Version_extractor", "Estado_analisis", "Coincidencias", "Departamento_BOE", "Administracion_resuelta", "Familia_administrativa", "Estado_resolucion", "Metodo_resolucion", "Confianza_resolucion", "Version_resolucion"]),
    "Cobertura": ("SELECT fecha,estado,version_extractor,fecha_ultima_consulta,numero_publicaciones FROM cobertura ORDER BY fecha", ["Fecha", "Estado", "Version_extractor", "Fecha_ultima_consulta", "Numero_publicaciones"]),
}

MAPA_OPOSICIONES = {
    "Oposicion_ID": "oposicion_id", "Publicacion_ID": "publicacion_id", "Fecha_boe": "fecha_boe",
    "Fecha_boe_original": "fecha_boe_original", "Puesto": "puesto", "Puesto_normalizado": "puesto_normalizado",
    "Num_plazas": "num_plazas", "Administración": "administracion", "Administración_normalizada": "administracion_normalizada",
    "Ambito": "ambito", "Tipo_entidad": "tipo_entidad", "Comunidad_Autónoma": "comunidad_autonoma",
    "Provincia": "provincia", "Municipio": "municipio", "Sistema": "sistema", "Turno": "turno",
    "Escala": "escala", "Subescala": "subescala", "Clase": "clase", "Publicación": "publicacion",
    "Latitud": "latitud", "Longitud": "longitud", "Habitantes": "habitantes", "Version_extractor": "version_extractor",
    "Fecha_analisis": "fecha_analisis", "Confianza_geografica": "confianza_geografica",
    "Evidencia_geografica": "evidencia_geografica", "Version_resolutor": "version_resolutor", "Enlace": "enlace",
}

_PREFIJOS_FORMULA = ("=", "+", "-", "@")

NOMBRES_CSV_COMPLETOS = {
    "Búsquedas": "busquedas.csv",
    "Oposiciones": "oposiciones.csv",
    "Log-errores": "log_errores.csv",
    "Publicaciones": "publicaciones.csv",
    "Cobertura": "cobertura.csv",
}

COLUMNAS_OPOSICIONES_FILTRADAS = [
    "Fecha BOE", "Puesto", "Puesto normalizado", "Número de plazas",
    "Administración", "Ámbito", "Tipo de entidad", "Comunidad autónoma",
    "Provincia", "Municipio", "Sistema", "Turno", "Escala", "Subescala",
    "Clase", "Confianza geográfica", "Evidencia geográfica", "Enlace BOE",
]

_SELECCION_OPOSICIONES_FILTRADAS = """fecha_boe AS 'Fecha BOE', puesto AS 'Puesto',
    puesto_normalizado AS 'Puesto normalizado', num_plazas AS 'Número de plazas',
    administracion AS 'Administración', ambito AS 'Ámbito', tipo_entidad AS 'Tipo de entidad',
    comunidad_autonoma AS 'Comunidad autónoma', provincia AS 'Provincia', municipio AS 'Municipio',
    sistema AS 'Sistema', turno AS 'Turno', escala AS 'Escala', subescala AS 'Subescala',
    clase AS 'Clase', confianza_geografica AS 'Confianza geográfica',
    evidencia_geografica AS 'Evidencia geográfica', enlace AS 'Enlace BOE'"""

_FILTROS_OPOSICIONES = {
    "texto", "fecha_desde", "fecha_hasta", "administracion", "ambito",
    "comunidad_autonoma", "provincia", "municipio", "municipio_exacto",
    "municipio_provincia_exacto", "tipo_entidad", "sistema", "turno",
    "escala", "subescala", "clase",
}


def _contratos(conexion):
    contratos = dict(CONTRATOS)
    existentes = {fila[1] for fila in conexion.execute("PRAGMA table_info(oposiciones)")}
    columnas = [nombre for nombre in CONTRATOS["Oposiciones"][1] if MAPA_OPOSICIONES[nombre] in existentes]
    seleccion = ",".join(MAPA_OPOSICIONES[nombre] for nombre in columnas)
    contratos["Oposiciones"] = (
        f"SELECT {seleccion} FROM oposiciones ORDER BY fecha_boe,enlace,puesto,oposicion_id",
        columnas,
    )
    return contratos


def cargar_datos_exportacion_completa(ruta_bd="datos/boe.db"):
    """Lee los cinco datasets funcionales y metadatos sin modificar SQLite."""
    ruta = Path(ruta_bd)
    if not ruta.exists():
        raise FileNotFoundError("SQLite no disponible. Ejecute migrar_excel_sqlite.py.")
    conexion = base_datos.conectar(ruta, readonly=True)
    try:
        if conexion.execute("PRAGMA quick_check").fetchone()[0] != "ok" or base_datos.foreign_key_check(conexion):
            raise RuntimeError("SQLite no supera las comprobaciones de integridad")
        tablas = {fila[0] for fila in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        requeridas = {"metadata", "busquedas", "oposiciones", "log_errores", "publicaciones", "cobertura"}
        if requeridas - tablas:
            raise RuntimeError("SQLite no contiene el esquema requerido")
        contratos = _contratos(conexion)
        datasets = {
            nombre: pd.DataFrame(conexion.execute(sql).fetchall(), columns=columnas)
            for nombre, (sql, columnas) in contratos.items()
        }
        return datasets, dict(conexion.execute("SELECT clave,valor FROM metadata"))
    finally:
        conexion.close()


def sanitizar_valor_formula(valor):
    """Neutraliza una fórmula potencial sin transformar números ni fechas."""
    if isinstance(valor, str) and valor.startswith(_PREFIJOS_FORMULA):
        return "'" + valor
    return valor


def preparar_datasets_para_xlsx(datasets):
    """Copia datasets para Excel aplicando solo saneamiento de fórmulas."""
    preparados = {}
    for nombre, dataframe in datasets.items():
        copia = dataframe.copy()
        for columna in copia.columns:
            if pd.api.types.is_object_dtype(copia[columna]) or pd.api.types.is_string_dtype(copia[columna]):
                copia[columna] = copia[columna].map(sanitizar_valor_formula)
        preparados[nombre] = copia
    return preparados


def _escribir_csv(dataframe, ruta):
    dataframe.to_csv(
        ruta, index=False, sep=";", encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL
    )


def _ruta_temporal(destino, sufijo):
    descriptor, nombre = tempfile.mkstemp(
        prefix=f".{destino.stem}-", suffix=sufijo, dir=destino.parent
    )
    os.close(descriptor)
    return Path(nombre)


def exportar_base_csv_zip(ruta_bd="datos/boe.db", salida="BOE-oposiciones.zip"):
    """Exporta los cinco datasets funcionales como CSV UTF-8-SIG dentro de ZIP."""
    destino = Path(salida)
    inicio = time.perf_counter()
    datasets, metadata = cargar_datos_exportacion_completa(ruta_bd)
    exportables = preparar_datasets_para_xlsx(datasets)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = _ruta_temporal(destino, ".tmp.zip")
    try:
        with zipfile.ZipFile(temporal, "w", compression=zipfile.ZIP_DEFLATED) as archivo:
            for nombre, dataframe in exportables.items():
                contenido = dataframe.to_csv(
                    index=False, sep=";", encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL
                )
                archivo.writestr(NOMBRES_CSV_COMPLETOS[nombre], contenido.encode("utf-8-sig"))
        os.replace(temporal, destino)
    finally:
        temporal.unlink(missing_ok=True)
    return {
        "origen_sqlite": str(ruta_bd), "schema_version": metadata.get("schema_version"),
        "data_version": metadata.get("data_version"), "destino": str(destino),
        "tamano_bytes": destino.stat().st_size,
        "duracion_s": round(time.perf_counter() - inicio, 3),
        "datasets": {nombre: len(dataframe) for nombre, dataframe in exportables.items()},
    }


def obtener_oposiciones_filtradas(ruta_bd="datos/boe.db", *, orden="fecha_desc", **filtros):
    """Obtiene todas las oposiciones del filtro web, sin paginación visual."""
    if orden not in consultas_boe._ORDEN_BUSQUEDA:
        raise ValueError(f"Orden no permitido: {orden}")
    filtros_logicos = {
        nombre: filtros[nombre]
        for nombre in _FILTROS_OPOSICIONES
        if nombre in filtros
    }
    where, parametros = consultas_boe._condiciones_busqueda(**filtros_logicos)
    conexion = consultas_boe._conexion(ruta_bd)
    try:
        return pd.read_sql_query(
            f"SELECT {_SELECCION_OPOSICIONES_FILTRADAS} FROM oposiciones{where} "
            f"ORDER BY {consultas_boe._ORDEN_BUSQUEDA[orden]}",
            conexion,
            params=parametros,
        ).reindex(columns=COLUMNAS_OPOSICIONES_FILTRADAS)
    finally:
        conexion.close()


def _exportar_oposiciones_filtradas(ruta_bd, salida, *, orden, formato, filtros):
    dataframe = obtener_oposiciones_filtradas(ruta_bd, orden=orden, **filtros)
    exportable = preparar_datasets_para_xlsx({"Oposiciones": dataframe})["Oposiciones"]
    destino = Path(salida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = _ruta_temporal(destino, f".tmp.{formato}")
    try:
        if formato == "xlsx":
            with pd.ExcelWriter(temporal, engine="openpyxl") as escritor:
                exportable.to_excel(escritor, sheet_name="Oposiciones", index=False)
            from preparar_archivo_datos import formatear_hoja_oposiciones

            formatear_hoja_oposiciones(temporal)
        else:
            _escribir_csv(exportable, temporal)
        os.replace(temporal, destino)
    finally:
        temporal.unlink(missing_ok=True)
    return {
        "destino": str(destino), "filas": len(exportable),
        "columnas": exportable.columns.tolist(), "orden": orden,
        "tamano_bytes": destino.stat().st_size,
    }


def exportar_oposiciones_filtradas_xlsx(
    ruta_bd="datos/boe.db", salida="oposiciones.xlsx", *, orden="fecha_desc", **filtros
):
    """Genera un XLSX de una hoja con todas las oposiciones filtradas."""
    return _exportar_oposiciones_filtradas(
        ruta_bd, salida, orden=orden, formato="xlsx", filtros=filtros
    )


def exportar_oposiciones_filtradas_csv(
    ruta_bd="datos/boe.db", salida="oposiciones.csv", *, orden="fecha_desc", **filtros
):
    """Genera un CSV UTF-8-SIG de todas las oposiciones filtradas."""
    return _exportar_oposiciones_filtradas(
        ruta_bd, salida, orden=orden, formato="csv", filtros=filtros
    )


def _fingerprint_hoja(dataframe, nombre):
    if nombre == "Oposiciones" and "Fecha_boe" in dataframe:
        dataframe = dataframe.copy()
        fechas = pd.to_datetime(dataframe["Fecha_boe"], errors="coerce")
        dataframe["Fecha_boe"] = fechas.dt.strftime("%Y-%m-%d").where(
            fechas.notna(), dataframe["Fecha_boe"]
        )
        for columna in ("Administración_normalizada", "Provincia", "Municipio", "Evidencia_geografica"):
            if columna in dataframe:
                dataframe[columna] = dataframe[columna].replace("", None)
    return _fingerprint(_registros_excel({nombre: dataframe}, nombre)[0])


def auditar_xlsx(datasets, ruta_excel):
    """Comprueba contenido lógico de un XLSX frente a los datasets exportados."""
    leidas = pd.read_excel(ruta_excel, sheet_name=list(CONTRATOS))
    tablas, diferencias = {}, []
    global_ = hashlib.sha256()
    for nombre, esperado in datasets.items():
        real = leidas[nombre].reindex(columns=esperado.columns)
        esperado_fingerprint = _fingerprint_hoja(esperado, nombre)
        real_fingerprint = _fingerprint_hoja(real, nombre)
        tablas[nombre] = {
            "filas_sqlite": len(esperado), "filas_excel": len(real),
            "columnas": esperado.columns.tolist(), "fingerprint_sqlite": esperado_fingerprint,
            "fingerprint_excel": real_fingerprint,
            "equivalente": esperado_fingerprint == real_fingerprint and len(esperado) == len(real),
        }
        global_.update(f"{nombre}:{esperado_fingerprint}:{real_fingerprint}\n".encode())
        if not tablas[nombre]["equivalente"]:
            diferencias.append(nombre)
    return {"tablas": tablas, "fingerprint_global": global_.hexdigest(), "diferencias": diferencias, "correcta": not diferencias}


def _backup_xlsx(ruta, directorio="backups/exportacion_excel"):
    directorio = Path(directorio)
    directorio.mkdir(parents=True, exist_ok=True)
    destino = directorio / f"{ruta.stem}_pre_exportacion_{datetime.now():%Y%m%d_%H%M%S_%f}.xlsx"
    shutil.copy2(ruta, destino)
    if destino.read_bytes() != ruta.read_bytes():
        destino.unlink(missing_ok=True)
        raise RuntimeError("El backup Excel no coincide")
    return destino


def exportar_base_xlsx(ruta_bd="datos/boe.db", salida="BOE-oposiciones.xlsx", *, sobrescribir=False):
    """Genera el XLSX funcional completo en la ruta elegida por el llamador."""
    salida = Path(salida)
    if salida.exists() and not sobrescribir:
        raise FileExistsError(f"El destino existe: {salida}. Use --sobrescribir.")
    inicio_carga = time.perf_counter()
    datasets, metadata = cargar_datos_exportacion_completa(ruta_bd)
    carga_s = time.perf_counter() - inicio_carga
    exportables = preparar_datasets_para_xlsx(datasets)
    salida.parent.mkdir(parents=True, exist_ok=True)
    backup = _backup_xlsx(salida) if salida.exists() else None
    inicio_exportacion = time.perf_counter()
    temporal = None
    try:
        descriptor, nombre = tempfile.mkstemp(prefix=f".{salida.stem}-", suffix=".tmp.xlsx", dir=salida.parent)
        os.close(descriptor)
        temporal = Path(nombre)
        with pd.ExcelWriter(temporal, engine="openpyxl") as escritor:
            for nombre_hoja, dataframe in exportables.items():
                dataframe.to_excel(escritor, sheet_name=nombre_hoja, index=False)
        from preparar_archivo_datos import formatear_hoja_oposiciones

        formatear_hoja_oposiciones(temporal)
        informe = auditar_xlsx(exportables, temporal)
        if not informe["correcta"]:
            raise RuntimeError(f"Auditoría fallida: {informe['diferencias']}")
        os.replace(temporal, salida)
        temporal = None
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)
    informe.update({
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "origen_sqlite": str(ruta_bd), "schema_version": metadata.get("schema_version"),
        "data_version": metadata.get("data_version"), "destino_excel": str(salida),
        "duracion_carga_s": round(carga_s, 3),
        "duracion_exportacion_s": round(time.perf_counter() - inicio_exportacion, 3),
        "tamano_bytes": salida.stat().st_size, "backup": str(backup) if backup else None,
        "proteccion_formula_injection": "apóstrofo inicial solo para textos con =, +, - o @",
    })
    # Compatibilidad con el informe histórico de exportar_excel.py.
    informe["duracion_s"] = informe["duracion_exportacion_s"]
    return informe
