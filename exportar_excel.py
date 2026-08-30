"""Exporta SQLite a un Excel de interoperabilidad, sin usar Excel como entrada."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

import pandas as pd

import base_datos
from migrar_excel_sqlite import _fingerprint, _registros_excel


CONTRATOS = {
    "Búsquedas": ("SELECT codigo FROM busquedas ORDER BY codigo", ["Código"]),
    "Oposiciones": ("", ["Oposicion_ID","Publicacion_ID","Fecha_boe","Fecha_boe_original","Puesto","Puesto_normalizado","Num_plazas","Administración","Administración_normalizada","Ambito","Tipo_entidad","Comunidad_Autónoma","Provincia","Municipio","Sistema","Turno","Escala","Subescala","Clase","Publicación","Latitud","Longitud","Habitantes","Version_extractor","Fecha_analisis","Confianza_geografica","Evidencia_geografica","Version_resolutor","Enlace"]),
    "Log-errores": ("SELECT fecha,tipo_error,enlace_web FROM log_errores ORDER BY error_id", ["Fecha","Tipo de error","Enlace Web"]),
    "Publicaciones": ("""SELECT publicacion_id,enlace,fecha_boe_original,titulo_original,fecha_ultimo_analisis,version_extractor,estado_analisis,coincidencias,departamento_boe,administracion_resuelta,familia_administrativa,estado_resolucion,metodo_resolucion,confianza_resolucion,version_resolucion FROM publicaciones ORDER BY fecha_boe,publicacion_id""", ["Publicacion_ID","Enlace","Fecha_BOE","Titulo_original","Fecha_ultimo_analisis","Version_extractor","Estado_analisis","Coincidencias","Departamento_BOE","Administracion_resuelta","Familia_administrativa","Estado_resolucion","Metodo_resolucion","Confianza_resolucion","Version_resolucion"]),
    "Cobertura": ("SELECT fecha,estado,version_extractor,fecha_ultima_consulta,numero_publicaciones FROM cobertura ORDER BY fecha", ["Fecha","Estado","Version_extractor","Fecha_ultima_consulta","Numero_publicaciones"]),
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

def _contratos(con):
    contratos = dict(CONTRATOS)
    existentes = {fila[1] for fila in con.execute("PRAGMA table_info(oposiciones)")}
    columnas = [nombre for nombre in CONTRATOS["Oposiciones"][1] if MAPA_OPOSICIONES[nombre] in existentes]
    seleccion = ",".join(MAPA_OPOSICIONES[nombre] for nombre in columnas)
    contratos["Oposiciones"] = (f"SELECT {seleccion} FROM oposiciones ORDER BY fecha_boe,enlace,puesto,oposicion_id", columnas)
    return contratos


def cargar_sqlite(ruta):
    if not Path(ruta).exists():
        raise FileNotFoundError("SQLite no disponible. Ejecute migrar_excel_sqlite.py.")
    con = base_datos.conectar(ruta, readonly=True)
    try:
        if con.execute("PRAGMA quick_check").fetchone()[0] != "ok" or base_datos.foreign_key_check(con):
            raise RuntimeError("SQLite no supera las comprobaciones de integridad")
        tablas = {fila[0] for fila in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if {"metadata", "busquedas", "oposiciones", "log_errores", "publicaciones", "cobertura"} - tablas:
            raise RuntimeError("SQLite no contiene el esquema requerido")
        contratos = _contratos(con)
        return {nombre: pd.DataFrame(con.execute(sql).fetchall(), columns=cols) for nombre, (sql, cols) in contratos.items()}, dict(con.execute("SELECT clave,valor FROM metadata"))
    finally:
        con.close()


def _fingerprint_hoja(df, nombre):
    return _fingerprint(_registros_excel({nombre: df}, nombre)[0])


def auditar(dataframes, ruta_excel):
    leidas = pd.read_excel(ruta_excel, sheet_name=list(CONTRATOS))
    tablas, diferencias = {}, []
    global_ = hashlib.sha256()
    for nombre, esperado in dataframes.items():
        real = leidas[nombre].reindex(columns=esperado.columns)
        a, b = _fingerprint_hoja(esperado, nombre), _fingerprint_hoja(real, nombre)
        tablas[nombre] = {"filas_sqlite": len(esperado), "filas_excel": len(real), "columnas": esperado.columns.tolist(), "fingerprint_sqlite": a, "fingerprint_excel": b, "equivalente": a == b and len(esperado) == len(real)}
        global_.update(f"{nombre}:{a}:{b}\n".encode())
        if not tablas[nombre]["equivalente"]: diferencias.append(nombre)
    return {"tablas": tablas, "fingerprint_global": global_.hexdigest(), "diferencias": diferencias, "correcta": not diferencias}


def _backup(ruta, directorio="backups/exportacion_excel"):
    directorio = Path(directorio); directorio.mkdir(parents=True, exist_ok=True)
    destino = directorio / f"{ruta.stem}_pre_exportacion_{datetime.now():%Y%m%d_%H%M%S_%f}.xlsx"
    shutil.copy2(ruta, destino)
    if destino.read_bytes() != ruta.read_bytes():
        destino.unlink(missing_ok=True); raise RuntimeError("El backup Excel no coincide")
    return destino


def exportar(ruta_bd="datos/boe.db", salida="BOE-oposiciones.xlsx", *, sobrescribir=False):
    salida = Path(salida)
    if salida.exists() and not sobrescribir:
        raise FileExistsError(f"El destino existe: {salida}. Use --sobrescribir.")
    dataframes, metadata = cargar_sqlite(ruta_bd)
    salida.parent.mkdir(parents=True, exist_ok=True)
    backup = _backup(salida) if salida.exists() else None
    inicio = time.perf_counter(); temporal = None
    try:
        descriptor, nombre = tempfile.mkstemp(prefix=f".{salida.stem}-", suffix=".tmp.xlsx", dir=salida.parent)
        os.close(descriptor); temporal = Path(nombre)
        with pd.ExcelWriter(temporal, engine="openpyxl") as writer:
            for nombre_hoja, df in dataframes.items():
                df.to_excel(writer, sheet_name=nombre_hoja, index=False)
        from preparar_archivo_datos import formatear_hoja_oposiciones
        formatear_hoja_oposiciones(temporal)
        informe = auditar(dataframes, temporal)
        if not informe["correcta"]: raise RuntimeError(f"Auditoría fallida: {informe['diferencias']}")
        os.replace(temporal, salida); temporal = None
    finally:
        if temporal is not None: temporal.unlink(missing_ok=True)
    informe.update({"fecha": datetime.now().isoformat(timespec="seconds"), "origen_sqlite": str(ruta_bd), "schema_version": metadata.get("schema_version"), "data_version": metadata.get("data_version"), "destino_excel": str(salida), "duracion_s": round(time.perf_counter()-inicio,3), "tamano_bytes": salida.stat().st_size, "backup": str(backup) if backup else None})
    informes = Path("informes/exportacion_excel"); informes.mkdir(parents=True, exist_ok=True)
    (informes/"auditoria_exportacion_excel.json").write_text(json.dumps(informe,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (informes/"auditoria_exportacion_excel.md").write_text("# Auditoría exportación Excel\n\n"+json.dumps(informe,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return informe


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--bd",default="datos/boe.db"); p.add_argument("--salida",default="BOE-oposiciones.xlsx"); p.add_argument("--sobrescribir",action="store_true"); a=p.parse_args(argv)
    print(json.dumps(exportar(a.bd,a.salida,sobrescribir=a.sobrescribir),ensure_ascii=False,indent=2))

if __name__ == "__main__": main()
