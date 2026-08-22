"""Simulación de reprocesamiento de publicaciones con extractores anteriores."""

from collections import Counter
from datetime import datetime
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import tempfile

import pandas as pd
import requests
from bs4 import BeautifulSoup, ParserRejectedMarkup

import coincidencias
import preparar_archivo_datos
from fechas import convertir_fecha
from mapa_plazas import enriquecer_filas_sin_coordenadas
from publicaciones import normalizar_publicaciones
from trazabilidad import enriquecer_historico_oposiciones
from trazabilidad import VERSION_EXTRACTOR, necesita_reprocesamiento


CAMPOS_CONVOCATORIA = [
    "Puesto",
    "Fecha_boe",
    "Administración",
    "Enlace",
    "Num_plazas",
    "Turno",
    "Sistema",
    "Escala",
    "Subescala",
    "Clase",
]
CLASIFICACIONES = [
    "SIN_CAMBIOS",
    "AMPLIADA",
    "REDUCIDA",
    "MODIFICADA",
    "SIN_RESULTADOS_NUEVOS",
    "ERROR",
]
CLASIFICACIONES_ESCRIBIBLES = {"SIN_CAMBIOS", "AMPLIADA"}


class ReprocesamientoNoSeguroError(RuntimeError):
    pass


class BackupInvalidoError(RuntimeError):
    pass


class VerificacionAplicacionError(RuntimeError):
    pass


def leer_datos_legacy(ruta_excel="BOE-oposiciones.xlsx"):
    """Lee las hojas necesarias desde una instantánea no mutante en memoria."""
    ruta = Path(ruta_excel)
    contenido = ruta.read_bytes()
    try:
        libro = pd.ExcelFile(BytesIO(contenido))
        return (
            pd.read_excel(libro, sheet_name="Publicaciones"),
            pd.read_excel(libro, sheet_name="Oposiciones"),
        )
    except (ValueError, OSError) as error:
        raise ValueError(f"No se pudo leer el histórico: {error}") from error


def seleccionar_publicaciones(
    publicaciones,
    desde=None,
    hasta=None,
    publicacion_id=None,
    limite=None,
):
    """Selecciona publicaciones cuya versión necesita el extractor actual."""
    resultado = publicaciones.copy(deep=True)
    resultado = resultado[
        resultado["Version_extractor"].map(necesita_reprocesamiento)
    ].copy()
    resultado["_Fecha_dt"] = resultado["Fecha_BOE"].map(_convertir_fecha_segura)

    fecha_desde = _fecha_iso(desde) if desde else None
    fecha_hasta = _fecha_iso(hasta) if hasta else None
    if fecha_desde is not None:
        resultado = resultado[resultado["_Fecha_dt"] >= fecha_desde]
    if fecha_hasta is not None:
        resultado = resultado[resultado["_Fecha_dt"] <= fecha_hasta]
    if publicacion_id:
        resultado = resultado[resultado["Publicacion_ID"] == publicacion_id]
    if limite is not None:
        if limite < 1:
            raise ValueError("--limite debe ser un entero mayor que cero")
        resultado = resultado.head(limite)
    return resultado.drop(columns="_Fecha_dt")


def comparar_convocatorias(historicas, nuevas):
    """Compara convocatorias sin considerar campos de trazabilidad."""
    anteriores = [_fila_funcional(fila) for fila in _registros(historicas)]
    actuales = [_fila_funcional(fila) for fila in _registros(nuevas)]
    if anteriores and not actuales:
        return _comparacion(
            "SIN_RESULTADOS_NUEVOS", [], anteriores, [], anteriores, actuales
        )

    contador_anteriores = Counter(_tupla(fila) for fila in anteriores)
    contador_actuales = Counter(_tupla(fila) for fila in actuales)
    ausentes = _expandir(contador_anteriores - contador_actuales)
    añadidas = _expandir(contador_actuales - contador_anteriores)
    if not ausentes and not añadidas:
        return _comparacion("SIN_CAMBIOS", [], [], [], anteriores, actuales)
    if añadidas and not ausentes:
        return _comparacion("AMPLIADA", añadidas, [], [], anteriores, actuales)
    if ausentes and not añadidas:
        return _comparacion("REDUCIDA", [], ausentes, [], anteriores, actuales)

    modificaciones, añadidas, ausentes = _emparejar_diferencias(
        añadidas, ausentes
    )
    return _comparacion(
        "MODIFICADA", añadidas, ausentes, modificaciones, anteriores, actuales
    )


def reprocesar_publicacion(publicacion, oposiciones, obtener=requests.get):
    """Descarga y compara una publicación, sin persistir ningún resultado."""
    publicacion_id = publicacion["Publicacion_ID"]
    enlace = publicacion["Enlace"]
    historicas = oposiciones[oposiciones["Publicacion_ID"] == publicacion_id]
    base = {
        "Publicacion_ID": publicacion_id,
        "Fecha_BOE": publicacion["Fecha_BOE"],
        "Enlace": enlace,
        "Version_anterior": publicacion["Version_extractor"],
        "Version_actual": VERSION_EXTRACTOR,
        "filas_historicas": len(historicas),
    }
    try:
        respuesta = obtener(enlace, timeout=5)
        respuesta.raise_for_status()
        soup = BeautifulSoup(respuesta.content, "html.parser")
        contenidos = soup.find_all("div", id="textoxslt")
        titulo = soup.find(class_="documento-tit")
        fecha = soup.find("div", class_="metadatos")
        if not contenidos or titulo is None or fecha is None:
            raise ValueError("Faltan elementos esperados en el HTML")
        nuevas = []
        for contenido in contenidos:
            extraidas = coincidencias.extraer_convocatorias_local(
                contenido.text, titulo.text.strip(), fecha.text.strip(), enlace
            )
            if not extraidas:
                extraidas = coincidencias.extraer_convocatorias_estatal(
                    contenido.text, titulo.text.strip(), fecha.text.strip(), enlace
                )
            nuevas.extend(extraidas)
        comparacion = comparar_convocatorias(historicas, nuevas)
        return {**base, "filas_nuevas": len(nuevas), **comparacion}
    except (
        requests.exceptions.RequestException,
        ParserRejectedMarkup,
        TypeError,
        ValueError,
    ) as error:
        return {
            **base,
            "filas_nuevas": 0,
            "clasificacion": "ERROR",
            "filas_añadidas": [],
            "filas_ausentes": [],
            "campos_modificados": [],
            "filas_historicas_funcionales": [
                _fila_funcional(fila) for fila in _registros(historicas)
            ],
            "filas_nuevas_funcionales": [],
            "tipo_error": type(error).__name__,
            "error": str(error),
        }


def ejecutar_dry_run(
    ruta_excel="BOE-oposiciones.xlsx",
    desde=None,
    hasta=None,
    publicacion_id=None,
    limite=None,
    obtener=requests.get,
):
    """Ejecuta la simulación completa y devuelve detalle y resumen."""
    publicaciones, oposiciones = leer_datos_legacy(ruta_excel)
    seleccionadas = seleccionar_publicaciones(
        publicaciones, desde, hasta, publicacion_id, limite
    )
    detalles = [
        reprocesar_publicacion(fila, oposiciones, obtener)
        for fila in seleccionadas.to_dict(orient="records")
    ]
    resumen = {clave: 0 for clave in CLASIFICACIONES}
    for detalle in detalles:
        resumen[detalle["clasificacion"]] += 1
    resumen.update(
        {
            "Publicaciones analizadas": len(detalles),
            "filas históricas": sum(d["filas_historicas"] for d in detalles),
            "filas obtenidas actualmente": sum(d["filas_nuevas"] for d in detalles),
            "filas añadidas": sum(len(d["filas_añadidas"]) for d in detalles),
            "filas ausentes": sum(len(d["filas_ausentes"]) for d in detalles),
        }
    )
    return detalles, resumen


def calcular_integridad_excel(ruta_excel="BOE-oposiciones.xlsx"):
    """Calcula los controles no mutantes usados por el informe de auditoría."""
    ruta = Path(ruta_excel)
    contenido = ruta.read_bytes()
    estado = ruta.stat()
    return {
        "sha256": hashlib.sha256(contenido).hexdigest(),
        "tamano": estado.st_size,
        "mtime_ns": estado.st_mtime_ns,
    }


def guardar_informe_auditoria(
    detalles,
    resumen,
    filtros,
    integridad_antes,
    integridad_despues,
    directorio="logs/reprocesamiento_legacy",
    momento=None,
    modo="dry-run",
    datos_escritura=None,
    destino=None,
):
    """Guarda atómicamente el informe completo del dry-run en JSON."""
    fecha_ejecucion = momento or datetime.now()
    controles_iguales = integridad_antes == integridad_despues
    informe = {
        "fecha_ejecucion": fecha_ejecucion.strftime("%Y-%m-%d %H:%M:%S"),
        "version_extractor": VERSION_EXTRACTOR,
        "modo": modo,
        "filtros_utilizados": filtros,
        "total_publicaciones": resumen["Publicaciones analizadas"],
        **{clave: resumen[clave] for clave in CLASIFICACIONES},
        "filas_historicas": resumen["filas históricas"],
        "filas_actuales": resumen["filas obtenidas actualmente"],
        "filas_anadidas": resumen["filas añadidas"],
        "filas_ausentes": resumen["filas ausentes"],
        "excel_sha256_antes": integridad_antes["sha256"],
        "excel_sha256_despues": integridad_despues["sha256"],
        "excel_tamano_antes": integridad_antes["tamano"],
        "excel_tamano_despues": integridad_despues["tamano"],
        "excel_mtime_ns_antes": integridad_antes["mtime_ns"],
        "excel_mtime_ns_despues": integridad_despues["mtime_ns"],
        "excel_modificado": not controles_iguales,
        "publicaciones": [_detalle_para_json(detalle) for detalle in detalles],
    }
    if datos_escritura:
        informe.update(datos_escritura)
    if not controles_iguales and modo == "dry-run":
        informe["anomalia_integridad"] = (
            "El Excel cambió durante la ejecución del dry-run."
        )

    ruta_directorio = Path(directorio)
    ruta_directorio.mkdir(parents=True, exist_ok=True)
    if destino is None:
        marca = fecha_ejecucion.strftime("%Y%m%d_%H%M%S")
        destino = _ruta_informe_unica(
            ruta_directorio / f"reprocesamiento_legacy_{marca}.json"
        )
    else:
        destino = Path(destino)
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=ruta_directorio,
            prefix=f".{destino.stem}_",
            suffix=".tmp",
            delete=False,
        ) as archivo:
            temporal = Path(archivo.name)
            json.dump(
                informe,
                archivo,
                ensure_ascii=False,
                indent=2,
                default=_json_default,
            )
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(temporal, destino)
    except BaseException:
        if temporal is not None:
            temporal.unlink(missing_ok=True)
        raise
    return destino


def asignar_acciones(detalles):
    """Asigna la única acción permitida para cada clasificación."""
    acciones = {
        "SIN_CAMBIOS": "ACTUALIZAR_TRAZABILIDAD",
        "AMPLIADA": "AÑADIR_Y_ACTUALIZAR",
    }
    for detalle in detalles:
        detalle["accion"] = acciones.get(detalle["clasificacion"], "NO_ESCRIBIR")
    return bool(detalles) and all(
        detalle["clasificacion"] in CLASIFICACIONES_ESCRIBIBLES
        for detalle in detalles
    )


def crear_backup_verificado(
    ruta_excel="BOE-oposiciones.xlsx",
    directorio="backups/reprocesamiento_legacy",
    momento=None,
):
    """Crea y verifica una copia del Excel antes de la escritura."""
    origen = Path(ruta_excel)
    instante = momento or datetime.now()
    carpeta = Path(directorio)
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = _ruta_informe_unica(
        carpeta / f"BOE-oposiciones_{instante.strftime('%Y%m%d_%H%M%S')}.xlsx"
    )
    shutil.copy2(origen, destino)
    original = calcular_integridad_excel(origen)
    copia = calcular_integridad_excel(destino)
    if original["sha256"] != copia["sha256"] or original["tamano"] != copia["tamano"]:
        raise BackupInvalidoError("La copia de seguridad no coincide con el Excel original")
    return destino, copia


def preparar_aplicacion(detalles, hojas, momento=None):
    """Prepara todo el lote en memoria sin eliminar ni sustituir datos funcionales."""
    if not asignar_acciones(detalles):
        raise ReprocesamientoNoSeguroError(
            "El lote contiene resultados que no permiten escritura"
        )
    fecha_analisis = (momento or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    oposiciones = enriquecer_historico_oposiciones(
        hojas["Oposiciones"]
    ).copy(deep=True)
    oposiciones["Version_extractor"] = oposiciones[
        "Version_extractor"
    ].astype("object")
    oposiciones["Fecha_analisis"] = oposiciones["Fecha_analisis"].astype(
        "object"
    )
    publicaciones = normalizar_publicaciones(hojas["Publicaciones"])
    filas_actualizadas = 0
    filas_nuevas = []

    for detalle in detalles:
        publicacion_id = detalle["Publicacion_ID"]
        claves_actuales = Counter(
            _tupla(fila) for fila in detalle["filas_nuevas_funcionales"]
        )
        indices = oposiciones.index[
            oposiciones["Publicacion_ID"] == publicacion_id
        ]
        for indice in indices:
            clave = _tupla(_fila_funcional(oposiciones.loc[indice].to_dict()))
            if claves_actuales[clave] > 0:
                oposiciones.at[indice, "Version_extractor"] = VERSION_EXTRACTOR
                oposiciones.at[indice, "Fecha_analisis"] = fecha_analisis
                filas_actualizadas += 1

        for fila in detalle["filas_añadidas"]:
            filas_nuevas.append(
                {
                    **fila,
                    "Publicacion_ID": publicacion_id,
                    "Version_extractor": VERSION_EXTRACTOR,
                    "Fecha_analisis": fecha_analisis,
                }
            )

        mascara_publicacion = publicaciones["Publicacion_ID"] == publicacion_id
        if not mascara_publicacion.any():
            raise ReprocesamientoNoSeguroError(
                f"No existe {publicacion_id} en Publicaciones"
            )
        indice_publicacion = publicaciones.index[mascara_publicacion][-1]
        publicaciones.at[indice_publicacion, "Version_extractor"] = VERSION_EXTRACTOR
        publicaciones.at[indice_publicacion, "Fecha_ultimo_analisis"] = fecha_analisis
        publicaciones.at[indice_publicacion, "Estado_analisis"] = "con_coincidencias"
        publicaciones.at[indice_publicacion, "Coincidencias"] = detalle["filas_nuevas"]

    if filas_nuevas:
        nuevas = enriquecer_filas_sin_coordenadas(pd.DataFrame(filas_nuevas))
        for columna in oposiciones.columns:
            if columna not in nuevas.columns:
                nuevas[columna] = pd.NA
        for columna in nuevas.columns:
            if columna not in oposiciones.columns:
                oposiciones[columna] = pd.NA
        oposiciones = pd.concat(
            [
                oposiciones.astype("object"),
                nuevas[oposiciones.columns].astype("object"),
            ],
            ignore_index=True,
        )

    if oposiciones.duplicated(subset=CAMPOS_CONVOCATORIA, keep=False).any():
        raise ReprocesamientoNoSeguroError(
            "La aplicación produciría convocatorias funcionales duplicadas"
        )
    return {
        "Oposiciones": oposiciones,
        "Publicaciones": publicaciones,
        "Búsquedas": hojas["Búsquedas"].copy(deep=True),
        "Cobertura": hojas["Cobertura"].copy(deep=True),
        "Log-errores": hojas["Log-errores"].copy(deep=True),
    }, {
        "filas_anadidas_realmente": len(filas_nuevas),
        "filas_actualizadas_trazabilidad": filas_actualizadas,
        "publicaciones_actualizadas": len(detalles),
        "fecha_analisis": fecha_analisis,
    }


def aplicar_lote(detalles, ruta_excel="BOE-oposiciones.xlsx", momento=None):
    """Prepara y guarda atómicamente un lote previamente comparado y seguro."""
    hojas = _leer_todas_las_hojas(ruta_excel)
    historicas_antes = hojas["Oposiciones"].copy(deep=True)
    preparados, metricas = preparar_aplicacion(detalles, hojas, momento)
    preparar_archivo_datos.guardar_excel(
        preparados["Oposiciones"],
        preparados["Búsquedas"],
        preparados["Log-errores"],
        preparados["Publicaciones"],
        preparados["Cobertura"],
    )
    verificar_aplicacion(ruta_excel, detalles, historicas_antes)
    return metricas


def verificar_aplicacion(ruta_excel, detalles, historicas_antes):
    """Reabre el Excel y valida trazabilidad, adiciones y conservación."""
    hojas = _leer_todas_las_hojas(ruta_excel)
    oposiciones = hojas["Oposiciones"]
    publicaciones = hojas["Publicaciones"]
    contador_despues = Counter(
        _tupla(_fila_funcional(fila))
        for fila in oposiciones.to_dict(orient="records")
    )
    contador_antes = Counter(
        _tupla(_fila_funcional(fila))
        for fila in historicas_antes.to_dict(orient="records")
    )
    if contador_antes - contador_despues:
        raise VerificacionAplicacionError("Han desaparecido filas históricas")
    if oposiciones.duplicated(subset=CAMPOS_CONVOCATORIA, keep=False).any():
        raise VerificacionAplicacionError("Existen convocatorias duplicadas")
    for detalle in detalles:
        publicacion_id = detalle["Publicacion_ID"]
        filas = oposiciones[oposiciones["Publicacion_ID"] == publicacion_id]
        if filas.empty or not filas["Version_extractor"].astype(str).eq(
            VERSION_EXTRACTOR
        ).all():
            raise VerificacionAplicacionError(
                f"Trazabilidad incompleta para {publicacion_id}"
            )
        registro = publicaciones[
            publicaciones["Publicacion_ID"] == publicacion_id
        ]
        if registro.empty or str(registro.iloc[-1]["Version_extractor"]) != VERSION_EXTRACTOR:
            raise VerificacionAplicacionError(
                f"Publicaciones no refleja la versión de {publicacion_id}"
            )
        for añadida in detalle["filas_añadidas"]:
            if contador_despues[_tupla(añadida)] < 1:
                raise VerificacionAplicacionError(
                    f"Falta una fila nueva de {publicacion_id}"
                )


def _leer_todas_las_hojas(ruta_excel):
    contenido = Path(ruta_excel).read_bytes()
    libro = pd.ExcelFile(BytesIO(contenido))
    return {nombre: pd.read_excel(libro, nombre) for nombre in libro.sheet_names}


def imprimir_informe(detalles, resumen, modo="dry-run", datos_escritura=None):
    for detalle in detalles:
        print(
            f"{detalle['Publicacion_ID']} | {detalle['Fecha_BOE']} | "
            f"históricas: {detalle['filas_historicas']} | "
            f"nuevas: {detalle['filas_nuevas']} | {detalle['clasificacion']}"
        )
        for nombre, clave in (
            ("Filas añadidas", "filas_añadidas"),
            ("Filas ausentes", "filas_ausentes"),
            ("Campos modificados", "campos_modificados"),
        ):
            if detalle[clave]:
                print(f"  {nombre}: {detalle[clave]}")
        if detalle.get("error"):
            print(f"  Error: {detalle['error']}")
    titulo_modo = "APLICADO" if modo == "aplicar" else "simulación"
    print(f"\nResumen del reprocesamiento legacy ({titulo_modo})")
    for clave in ["Publicaciones analizadas", *CLASIFICACIONES]:
        print(f"{clave}: {resumen[clave]}")
    for clave in (
        "filas históricas",
        "filas obtenidas actualmente",
        "filas añadidas",
        "filas ausentes",
    ):
        print(f"{clave}: {resumen[clave]}")
    if modo == "aplicar" and datos_escritura:
        print(f"Backup creado: {datos_escritura['backup']}")
        print(
            "Publicaciones actualizadas: "
            f"{datos_escritura['publicaciones_actualizadas']}"
        )
        print(
            "Filas añadidas realmente: "
            f"{datos_escritura['filas_anadidas_realmente']}"
        )
        print(
            "Filas con trazabilidad actualizada: "
            f"{datos_escritura['filas_actualizadas_trazabilidad']}"
        )
        print("Escritura completada correctamente.")
        print("Verificación posterior: correcta.")


def _detalle_para_json(detalle):
    resultado = {
        "Publicacion_ID": detalle["Publicacion_ID"],
        "Fecha_BOE": detalle["Fecha_BOE"],
        "Enlace": detalle["Enlace"],
        "Version_anterior": detalle["Version_anterior"],
        "Version_actual": detalle["Version_actual"],
        "clasificacion": detalle["clasificacion"],
        "filas_historicas": detalle["filas_historicas_funcionales"],
        "filas_actuales": detalle["filas_nuevas_funcionales"],
        "numero_historicas": detalle["filas_historicas"],
        "numero_actuales": detalle["filas_nuevas"],
        "filas_anadidas": detalle["filas_añadidas"],
        "filas_ausentes": detalle["filas_ausentes"],
        "campos_modificados": detalle["campos_modificados"],
        "accion": detalle.get("accion", "NO_ESCRIBIR"),
    }
    if detalle["clasificacion"] == "ERROR":
        resultado["tipo_error"] = detalle["tipo_error"]
        resultado["mensaje"] = detalle["error"]
    return resultado


def _ruta_informe_unica(ruta):
    if not ruta.exists():
        return ruta
    numero = 1
    while True:
        candidata = ruta.with_name(f"{ruta.stem}_{numero}{ruta.suffix}")
        if not candidata.exists():
            return candidata
        numero += 1


def _json_default(valor):
    if hasattr(valor, "item"):
        return valor.item()
    if isinstance(valor, (datetime, pd.Timestamp)):
        return valor.isoformat()
    if pd.isna(valor):
        return None
    raise TypeError(f"Valor no serializable: {type(valor).__name__}")


def _convertir_fecha_segura(valor):
    try:
        return pd.Timestamp(convertir_fecha(str(valor))).normalize()
    except (TypeError, ValueError):
        return pd.NaT


def _fecha_iso(valor):
    try:
        return pd.Timestamp(datetime.strptime(valor, "%Y-%m-%d")).normalize()
    except (TypeError, ValueError) as error:
        raise ValueError(f"Fecha inválida: {valor}; use YYYY-MM-DD") from error


def _registros(datos):
    if isinstance(datos, pd.DataFrame):
        return datos.to_dict(orient="records")
    return list(datos or [])


def _valor(valor):
    return None if pd.isna(valor) else valor


def _fila_funcional(fila):
    return {campo: _valor(fila.get(campo)) for campo in CAMPOS_CONVOCATORIA}


def _tupla(fila):
    return tuple(fila[campo] for campo in CAMPOS_CONVOCATORIA)


def _expandir(contador):
    return [
        dict(zip(CAMPOS_CONVOCATORIA, valores))
        for valores, cantidad in contador.items()
        for _ in range(cantidad)
    ]


def _emparejar_diferencias(añadidas, ausentes):
    pendientes = list(añadidas)
    modificaciones = []
    ausentes_reales = []
    for anterior in ausentes:
        candidatos = [
            (sum(anterior[c] == nueva[c] for c in CAMPOS_CONVOCATORIA), i, nueva)
            for i, nueva in enumerate(pendientes)
        ]
        if not candidatos:
            ausentes_reales.append(anterior)
            continue
        iguales, indice, nueva = max(candidatos, key=lambda item: item[0])
        if iguales == 0:
            ausentes_reales.append(anterior)
            continue
        pendientes.pop(indice)
        cambios = {
            campo: {"anterior": anterior[campo], "nuevo": nueva[campo]}
            for campo in CAMPOS_CONVOCATORIA
            if anterior[campo] != nueva[campo]
        }
        modificaciones.append({"anterior": anterior, "nuevo": nueva, "cambios": cambios})
    return modificaciones, pendientes, ausentes_reales


def _comparacion(clasificacion, añadidas, ausentes, modificaciones, anteriores, actuales):
    return {
        "clasificacion": clasificacion,
        "filas_añadidas": añadidas,
        "filas_ausentes": ausentes,
        "campos_modificados": modificaciones,
        "filas_historicas_funcionales": anteriores,
        "filas_nuevas_funcionales": actuales,
    }
