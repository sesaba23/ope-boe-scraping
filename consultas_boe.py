"""Consultas de lectura para los consumidores SQLite de BOE."""
from pathlib import Path
import sqlite3

import pandas as pd

import base_datos


class ErrorConsultaSQLite(RuntimeError):
    """La base productiva no está disponible para consultas."""


COLUMNAS_ESTADISTICAS = ["Num_plazas", "Puesto", "Puesto_normalizado", "Administración", "Provincia", "Municipio", "Ambito", "Sistema", "Turno", "Fecha_boe"]
COLUMNAS_MAPA = ["Num_plazas", "Puesto", "Administración", "Sistema", "Fecha_boe_original", "Enlace", "Latitud", "Longitud", "Habitantes", "Municipio", "Provincia"]


def _conexion(ruta_bd):
    try:
        base_datos.validar_base_principal(ruta_bd)
        return base_datos.conectar(ruta_bd, readonly=True)
    except (OSError, sqlite3.Error, base_datos.EspejoSQLiteError) as error:
        raise ErrorConsultaSQLite(f"SQLite no está disponible: {ruta_bd}") from error


def _filtros(desde=None, hasta=None, provincia=None, municipio=None, administracion=None,
             puesto=None, sistema=None, turno=None, ambito=None):
    clausulas, parametros = [], []
    for columna, valor, operador in (("fecha_boe", desde, ">="), ("fecha_boe", hasta, "<="),
                                     ("provincia", provincia, "="), ("municipio", municipio, "="),
                                     ("administracion", administracion, "="), ("ambito", ambito, "="), ("sistema", sistema, "="),
                                     ("turno", turno, "=")):
        if valor:
            clausulas.append(f"{columna} {operador} ?"); parametros.append(valor)
    if puesto:
        for palabra in str(puesto).split():
            clausulas.append("lower(puesto) LIKE lower(?)"); parametros.append(f"%{palabra}%")
    return (" WHERE " + " AND ".join(clausulas) if clausulas else ""), parametros


def oposiciones(ruta_bd="datos/boe.db", *, columnas=COLUMNAS_ESTADISTICAS, **filtros):
    """Devuelve solo las columnas y filas solicitadas, en una conexión read-only."""
    mapa = {"Num_plazas": "num_plazas", "Puesto": "puesto",
            "Puesto_normalizado": "COALESCE(puesto_normalizado, puesto)", "Administración": "COALESCE(administracion_normalizada, administracion)",
            "Provincia": "provincia", "Municipio": "municipio", "Sistema": "sistema", "Turno": "turno",
            "Fecha_boe": "fecha_boe", "Fecha_boe_original": "fecha_boe_original",
            "Enlace": "enlace", "Latitud": "latitud",
            "Longitud": "longitud", "Habitantes": "habitantes", "Ambito": "ambito"}
    try:
        seleccion = ",".join(f"{mapa[c]} AS '{c}'" for c in columnas)
    except KeyError as error:
        raise ValueError(f"Columna de consulta no admitida: {error.args[0]}") from error
    where, parametros = _filtros(**filtros)
    conexion = _conexion(ruta_bd)
    try:
        return pd.read_sql_query(f"SELECT {seleccion} FROM oposiciones{where} ORDER BY fecha_boe,oposicion_id", conexion, params=parametros)
    finally:
        conexion.close()


def opciones_filtros(ruta_bd="datos/boe.db"):
    conexion = _conexion(ruta_bd)
    try:
        resultado = {}
        for clave, columna in (("provincias", "provincia"), ("ambitos", "ambito"), ("sistemas", "sistema"), ("turnos", "turno")):
            filas = conexion.execute(f"SELECT DISTINCT {columna} FROM oposiciones WHERE {columna} IS NOT NULL AND trim({columna}) NOT IN ('', '--', 'no disponible') ORDER BY {columna} COLLATE NOCASE").fetchall()
            resultado[clave] = [fila[0] for fila in filas]
        return resultado
    finally:
        conexion.close()


def metadata(ruta_bd="datos/boe.db"):
    conexion = _conexion(ruta_bd)
    try:
        return dict(conexion.execute("SELECT clave,valor FROM metadata"))
    finally:
        conexion.close()
