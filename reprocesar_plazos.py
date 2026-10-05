"""Recalcula los plazos de solicitudes de publicaciones ya almacenadas.

El modo predeterminado es ``--dry-run`` implícito: descarga y analiza, pero no
escribe SQLite. Para persistir hay que indicar ``--aplicar`` explícitamente.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import tempfile
import time
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup, ParserRejectedMarkup

import base_datos
from plazos_solicitudes import VERSION, extraer_plazo_presentacion, recalcular_fin_dias_habiles
from calendarios_festivos import descubrir_calendarios as descubrir_calendarios_oficiales
from calendarios_festivos import festivos_para_anio


CAMPOS_PLAZO = (
    "plazo_solicitudes", "fecha_inicio_plazo", "fecha_fin_plazo",
    "plazo_calculo", "evidencia_plazo",
)
CLAVES_RESULTADO_PLAZO = (
    "Plazo_solicitudes", "Fecha_inicio_plazo", "Fecha_fin_plazo",
    "Plazo_calculo", "Evidencia_plazo",
)
VERSION_ESTADO = 1
_PATRON_DIAS_HABILES = re.compile(r"(?P<cantidad>\d+)\s+d[ií]as\s+h[aá]biles", re.IGNORECASE)


def _fecha_iso(valor):
    texto = str(valor or "").strip().replace("/", "-")
    try:
        return datetime.strptime(texto[:10], "%Y-%m-%d").date().isoformat()
    except ValueError as error:
        raise ValueError(f"Fecha no válida: {valor!r}; use YYYY-MM-DD") from error


def _url_documento(enlace, fecha_boe):
    """Elige XML para 2004 y HTML para publicaciones modernas."""
    if str(fecha_boe).startswith("2004-"):
        return str(enlace).replace("txt.php", "xml.php")
    return str(enlace)


def _texto_documento(respuesta, fecha_boe):
    if str(fecha_boe).startswith("2004-"):
        try:
            raiz = ElementTree.fromstring(respuesta.content)
            texto = " ".join(parte.strip() for parte in raiz.itertext() if parte.strip())
            if texto:
                return texto
        except ElementTree.ParseError:
            pass
    soup = BeautifulSoup(respuesta.content, "html.parser")
    contenidos = soup.find_all("div", id="textoxslt")
    if contenidos:
        return " ".join(x.get_text(" ", strip=True) for x in contenidos)
    return soup.get_text(" ", strip=True)


def _descargar_plazo(publicacion, obtener=requests.get, timeout=20, festivos=None):
    enlace = publicacion["enlace"] or (
        f"https://www.boe.es/diario_boe/txt.php?id={publicacion['publicacion_id']}"
    )
    fecha_boe = publicacion["fecha_boe"]
    url = _url_documento(enlace, fecha_boe)
    respuesta = obtener(url, timeout=timeout)
    respuesta.raise_for_status()
    texto = _texto_documento(respuesta, fecha_boe)
    if not texto:
        raise ValueError("El documento no contiene texto extraíble")
    return extraer_plazo_presentacion(texto, fecha_boe, festivos=festivos)


def _estado_vacio():
    return {"version": VERSION_ESTADO, "actualizado": None, "publicaciones": {}}


def _cargar_estado(ruta):
    ruta = Path(ruta)
    if not ruta.exists():
        return _estado_vacio()
    try:
        estado = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"No se puede leer el estado de reprocesado: {ruta}") from error
    if estado.get("version") != VERSION_ESTADO or not isinstance(estado.get("publicaciones"), dict):
        raise ValueError(f"Formato de estado no compatible: {ruta}")
    return estado


def _guardar_estado(ruta, estado):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    estado["actualizado"] = datetime.now().isoformat(timespec="seconds")
    descriptor, temporal = tempfile.mkstemp(prefix=f".{ruta.name}.", dir=ruta.parent)
    os.close(descriptor)
    temporal = Path(temporal)
    try:
        temporal.write_text(json.dumps(estado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporal, ruta)
    finally:
        temporal.unlink(missing_ok=True)


def _esperar_entre_peticion(marca, pausa):
    if pausa <= 0 or marca is None:
        return time.monotonic()
    transcurrido = time.monotonic() - marca
    if transcurrido < pausa:
        time.sleep(pausa - transcurrido)
    return time.monotonic()


def seleccionar_publicaciones(ruta_bd="datos/boe.db", *, desde=None, hasta=None,
                               publicacion_id=None, limite=None,
                               solo_sin_plazo=False):
    """Selecciona publicaciones por fecha/ID sin abrir una conexión de escritura."""
    conexion = base_datos.conectar(ruta_bd, readonly=True)
    try:
        columnas = {fila[1] for fila in conexion.execute("PRAGMA table_info(oposiciones)")}
        tiene_plazos = set(CAMPOS_PLAZO) <= columnas
        clausulas = [
            "EXISTS (SELECT 1 FROM oposiciones o0 WHERE o0.publicacion_id=p.publicacion_id)"
        ]
        parametros = []
        if desde:
            clausulas.append("p.fecha_boe >= ?")
            parametros.append(_fecha_iso(desde))
        if hasta:
            clausulas.append("p.fecha_boe <= ?")
            parametros.append(_fecha_iso(hasta))
        if publicacion_id:
            clausulas.append("p.publicacion_id = ?")
            parametros.append(publicacion_id)
        if solo_sin_plazo and tiene_plazos:
            clausulas.append(
                "EXISTS (SELECT 1 FROM oposiciones o WHERE o.publicacion_id=p.publicacion_id "
                "AND o.fecha_fin_plazo IS NULL)"
            )
        where = f" WHERE {' AND '.join(clausulas)}" if clausulas else ""
        sql = (
            "SELECT p.publicacion_id,p.enlace,p.fecha_boe,p.titulo_original, "
            "(SELECT group_concat(DISTINCT o.comunidad_autonoma) FROM oposiciones o "
            " WHERE o.publicacion_id=p.publicacion_id AND o.comunidad_autonoma IS NOT NULL "
            " AND o.comunidad_autonoma <> '') AS comunidades "
            "FROM publicaciones p" + where + " ORDER BY p.fecha_boe,p.publicacion_id"
        )
        if limite is not None:
            if limite < 1:
                raise ValueError("--limite debe ser un entero mayor que cero")
            sql += " LIMIT ?"
            parametros.append(limite)
        return [dict(zip(("publicacion_id", "enlace", "fecha_boe", "titulo_original", "comunidades"), fila))
                for fila in conexion.execute(sql, parametros)]
    finally:
        conexion.close()


def recalcular_filas_con_calendario(ruta_bd="datos/boe.db", *, aplicar=False,
                                    directorio_backup="backups/sqlite"):
    """Recalcula fechas de filas hábiles usando calendarios ya persistidos."""
    conexion = base_datos.conectar(ruta_bd, readonly=True)
    try:
        filas = conexion.execute(
            """SELECT oposicion_id,fecha_inicio_plazo,fecha_fin_plazo,plazo_solicitudes,
                      plazo_calculo,fecha_boe,comunidad_autonoma
               FROM oposiciones WHERE plazo_calculo='CALCULADO_DIAS_HABILES_SIN_FESTIVOS'"""
        ).fetchall()
    finally:
        conexion.close()
    actualizaciones = []
    cache = {}
    for fila in filas:
        match = _PATRON_DIAS_HABILES.search(str(fila[3] or ""))
        if not match or not fila[1]:
            continue
        anio = int(str(fila[1])[:4])
        comunidad = fila[6]
        clave = (anio, comunidad or "")
        if clave not in cache:
            cache[clave] = festivos_para_anio(ruta_bd, anio, comunidad_autonoma=comunidad)
        festivos = cache[clave]
        if festivos is None:
            continue
        fecha_fin = recalcular_fin_dias_habiles(fila[1], match.group("cantidad"), festivos)
        if fecha_fin != fila[2] or fila[4] != "CALCULADO_DIAS_HABILES_CON_FESTIVOS":
            actualizaciones.append((fecha_fin, fila[0]))
    resultado = {
        "filas_candidatas": len(filas), "filas_recalculadas": len(actualizaciones),
        "filas_actualizadas": 0, "backup": None, "data_version": None,
    }
    if not aplicar or not actualizaciones:
        return resultado
    backup = base_datos.crear_backup(ruta_bd, directorio_backup)
    conexion = base_datos.conectar(ruta_bd)
    try:
        metadata = base_datos.leer_metadata(conexion)
        with base_datos.transaccion(conexion):
            conexion.executemany(
                "UPDATE oposiciones SET fecha_fin_plazo=?,plazo_calculo='CALCULADO_DIAS_HABILES_CON_FESTIVOS' WHERE oposicion_id=?",
                actualizaciones,
            )
            base_datos.guardar_metadata(conexion, data_version=int(metadata["data_version"]) + 1)
            if base_datos.integrity_check(conexion) != ["ok"] or base_datos.foreign_key_check(conexion):
                raise base_datos.EspejoSQLiteError("El recálculo con festivos no supera las comprobaciones de integridad")
        resultado.update({
            "filas_actualizadas": len(actualizaciones), "backup": str(backup),
            "data_version": int(metadata["data_version"]) + 1,
        })
    finally:
        conexion.close()
    return resultado


def reprocesar(ruta_bd="datos/boe.db", *, desde=None, hasta=None,
               publicacion_id=None, limite=None, solo_sin_plazo=False,
               aplicar=False, directorio_backup="backups/sqlite", timeout=20,
               reintentos=3, pausa=0.2, estado="backups/plazos/reprocesado.json",
               forzar=False, guardar_cada=100, mostrar_progreso=False, obtener=requests.get,
               descubrir_calendarios=False, obtener_sumario=None):
    """Descarga, analiza y opcionalmente persiste los plazos seleccionados."""
    ruta_bd = Path(ruta_bd)
    if not ruta_bd.is_file():
        raise FileNotFoundError(f"No existe la base SQLite: {ruta_bd}")
    if reintentos < 1:
        raise ValueError("reintentos debe ser un entero mayor que cero")
    if pausa < 0:
        raise ValueError("pausa no puede ser negativa")
    if guardar_cada < 1:
        raise ValueError("guardar_cada debe ser un entero mayor que cero")
    if aplicar:
        import gestion_base
        gestion_base.migrar_si_necesario(ruta_bd)
    ruta_estado = Path(estado) if estado else None
    estado_proceso = _cargar_estado(ruta_estado) if ruta_estado else _estado_vacio()
    publicaciones = seleccionar_publicaciones(
        ruta_bd, desde=desde, hasta=hasta, publicacion_id=publicacion_id,
        solo_sin_plazo=solo_sin_plazo,
    )
    resumen_calendarios = None
    resumen_recalculo_calendarios = None
    if descubrir_calendarios and publicaciones:
        anios = {int(str(publicacion["fecha_boe"])[:4]) for publicacion in publicaciones}
        resumen_calendarios = descubrir_calendarios_oficiales(
            ruta_bd, anios, obtener_sumario=obtener_sumario,
            timeout=timeout, pausa=pausa, forzar=forzar,
        )
        if aplicar:
            resumen_recalculo_calendarios = recalcular_filas_con_calendario(
                ruta_bd, aplicar=True, directorio_backup=directorio_backup,
            )
    if not forzar:
        estados_a_omitir = {"PERSISTIDO"} if aplicar else {"PROCESADO", "PERSISTIDO"}
        publicaciones = [
            publicacion for publicacion in publicaciones
            if estado_proceso["publicaciones"].get(publicacion["publicacion_id"], {}).get("estado")
            not in estados_a_omitir
        ]
    if limite is not None:
        if limite < 1:
            raise ValueError("--limite debe ser un entero mayor que cero")
        publicaciones = publicaciones[:limite]
    resultados, errores = [], []
    solicitudes = 0
    reanudadas = 0
    marca_peticion = None
    cambios_estado = 0

    def guardar_checkpoint(*, forzar=False):
        nonlocal cambios_estado
        if ruta_estado and (forzar or cambios_estado >= guardar_cada):
            _guardar_estado(ruta_estado, estado_proceso)
            cambios_estado = 0
    total = len(publicaciones)
    siguiente_porcentaje = 0.1

    def informar(indice):
        nonlocal siguiente_porcentaje
        if not mostrar_progreso or not total:
            return
        porcentaje = indice / total
        if porcentaje >= siguiente_porcentaje or indice == total:
            print(
                f"PROGRESO {porcentaje:.0%} ({indice}/{total}) | "
                f"HTTP={solicitudes} | errores={len(errores)}",
                flush=True,
            )
            while siguiente_porcentaje <= porcentaje:
                siguiente_porcentaje += 0.1

    for indice, publicacion in enumerate(publicaciones, start=1):
        identificador = publicacion["publicacion_id"]
        entrada = estado_proceso["publicaciones"].get(identificador, {})
        if not forzar and entrada.get("estado") in {"PROCESADO", "PERSISTIDO"} and entrada.get("resultado"):
            resultados.append({**publicacion, **entrada["resultado"]})
            reanudadas += 1
            informar(indice)
            continue
        intentos_previos = int(entrada.get("intentos", 0) or 0) if not forzar else 0
        if not forzar and entrada.get("estado") == "ERROR" and intentos_previos >= reintentos:
            errores.append({
                "publicacion_id": identificador,
                "enlace": publicacion["enlace"],
                "error": entrada.get("error", "Se alcanzó el máximo de reintentos"),
                "tipo_error": entrada.get("tipo_error", "ErrorReprocesado"),
            })
            informar(indice)
            continue
        ultimo_error = None
        comunidades = [valor.strip() for valor in str(publicacion.get("comunidades") or "").split(",") if valor.strip()]
        comunidad = comunidades[0] if len(set(comunidades)) == 1 else None
        festivos = festivos_para_anio(ruta_bd, int(str(publicacion["fecha_boe"])[:4]), comunidad_autonoma=comunidad)
        while intentos_previos < reintentos:
            marca_peticion = _esperar_entre_peticion(marca_peticion, pausa)
            intentos_previos += 1
            solicitudes += 1
            try:
                plazo = _descargar_plazo(publicacion, obtener=obtener, timeout=timeout, festivos=festivos)
                resultado = {**publicacion, **plazo}
                estado_proceso["publicaciones"][identificador] = {
                    "estado": "PROCESADO", "intentos": intentos_previos,
                    "resultado": {k: resultado[k] for k in (*CLAVES_RESULTADO_PLAZO, "fecha_boe", "enlace", "titulo_original")},
                    "error": None, "tipo_error": None,
                }
                cambios_estado += 1
                guardar_checkpoint()
                resultados.append(resultado)
                break
            except (requests.RequestException, ParserRejectedMarkup, TypeError, ValueError) as error:
                ultimo_error = error
                estado_proceso["publicaciones"][identificador] = {
                    "estado": "ERROR", "intentos": intentos_previos,
                    "resultado": None, "error": str(error), "tipo_error": type(error).__name__,
                }
                cambios_estado += 1
                guardar_checkpoint()
                if intentos_previos < reintentos:
                    time.sleep(pausa)
        else:
            errores.append({
                "publicacion_id": identificador,
                "enlace": publicacion["enlace"],
                "error": str(ultimo_error),
                "tipo_error": type(ultimo_error).__name__,
            })
        informar(indice)
    guardar_checkpoint(forzar=True)
    filas_actualizables = [fila for fila in resultados if fila["publicacion_id"]]
    filas_afectadas = 0
    backup = None
    data_version = None
    pendientes_persistencia = [
        fila for fila in filas_actualizables
        if estado_proceso["publicaciones"].get(fila["publicacion_id"], {}).get("estado") != "PERSISTIDO"
    ]
    if aplicar and pendientes_persistencia:
        backup = base_datos.crear_backup(ruta_bd, directorio_backup)
        conexion = base_datos.conectar(ruta_bd)
        try:
            metadata = base_datos.leer_metadata(conexion)
            with base_datos.transaccion(conexion):
                for fila in pendientes_persistencia:
                    cursor = conexion.execute(
                        "UPDATE oposiciones SET plazo_solicitudes=?,fecha_inicio_plazo=?,"
                        "fecha_fin_plazo=?,plazo_calculo=?,evidencia_plazo=? "
                        "WHERE publicacion_id=?",
                        tuple(fila[campo] for campo in (
                            "Plazo_solicitudes", "Fecha_inicio_plazo", "Fecha_fin_plazo",
                            "Plazo_calculo", "Evidencia_plazo",
                        )) + (fila["publicacion_id"],),
                    )
                    filas_afectadas += cursor.rowcount
                if filas_afectadas:
                    data_version = int(metadata["data_version"]) + 1
                    base_datos.guardar_metadata(conexion, data_version=data_version)
                    if base_datos.integrity_check(conexion) != ["ok"] or base_datos.foreign_key_check(conexion):
                        raise base_datos.EspejoSQLiteError("El reprocesado no supera las comprobaciones de integridad")
        finally:
            conexion.close()
        for fila in pendientes_persistencia:
            entrada = estado_proceso["publicaciones"].get(fila["publicacion_id"], {})
            entrada["estado"] = "PERSISTIDO"
            estado_proceso["publicaciones"][fila["publicacion_id"]] = entrada
        if ruta_estado:
            _guardar_estado(ruta_estado, estado_proceso)
    return {
        "aplicar": aplicar,
        "version_extractor_plazos": VERSION,
        "publicaciones_seleccionadas": len(publicaciones),
        "publicaciones_procesadas": len(resultados),
        "publicaciones_con_plazo": sum(bool(fila["Fecha_fin_plazo"]) for fila in resultados),
        "filas_oposiciones_actualizadas": filas_afectadas,
        "solicitudes_http": solicitudes,
        "publicaciones_reanudadas": reanudadas,
        "errores": errores,
        "backup": str(backup) if backup else None,
        "data_version": data_version,
        "estado": str(ruta_estado) if ruta_estado else None,
        "calendarios": resumen_calendarios,
        "recalculo_calendarios": resumen_recalculo_calendarios,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-datos", default="datos/boe.db")
    parser.add_argument("--desde")
    parser.add_argument("--hasta")
    parser.add_argument("--publicacion-id")
    parser.add_argument("--limite", type=int)
    parser.add_argument("--solo-sin-plazo", action="store_true")
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--dry-run", action="store_true", help="Analiza sin escribir SQLite (predeterminado)")
    modo.add_argument("--aplicar", action="store_true", help="Persiste los plazos calculados")
    parser.add_argument("--directorio-backup", default="backups/sqlite")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--reintentos", type=int, default=3)
    parser.add_argument("--pausa", type=float, default=0.2, help="Segundos mínimos entre peticiones")
    parser.add_argument("--estado", default="backups/plazos/reprocesado.json")
    parser.add_argument("--guardar-cada", type=int, default=100,
                        help="Publicaciones entre checkpoints del estado")
    parser.add_argument("--forzar", action="store_true", help="Ignora el estado guardado y vuelve a descargar")
    parser.add_argument("--sin-progreso", action="store_true")
    parser.add_argument(
        "--sin-descubrir-calendarios", action="store_true",
        help="No buscar resoluciones oficiales de calendarios antes del reproceso",
    )
    args = parser.parse_args(argv)
    print(json.dumps(reprocesar(
        args.base_datos, desde=args.desde, hasta=args.hasta,
        publicacion_id=args.publicacion_id, limite=args.limite,
        solo_sin_plazo=args.solo_sin_plazo, aplicar=args.aplicar,
        directorio_backup=args.directorio_backup, timeout=args.timeout,
        reintentos=args.reintentos, pausa=args.pausa, estado=args.estado,
        forzar=args.forzar, mostrar_progreso=not args.sin_progreso,
        guardar_cada=args.guardar_cada,
        descubrir_calendarios=args.aplicar and not args.sin_descubrir_calendarios,
    ), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
