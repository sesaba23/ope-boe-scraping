"""Estado transaccional, reanudable y sin escrituras parciales para históricos."""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile

VERSION_FORMATO = 1
VERSION_EXTRACTOR_HISTORICO = "historico-experimental-2004"


def ruta_estado(inicio, fin, directorio="informes/procesamiento_historico_2004"):
    return Path(directorio) / f"estado_{inicio}_{fin}.json"


def crear_estado(inicio, fin, publicaciones, indices_diarios, ahora=None):
    ahora = (ahora or datetime.now()).isoformat(timespec="seconds")
    catalogo = {p["Publicacion_ID"]: {"Publicacion_ID": p["Publicacion_ID"], "Fecha_boe": p.get("Fecha_boe"),
                "Enlace": p.get("Enlace"), "titulo": p.get("titulo", ""),
                "departamento": p.get("departamento", ""), "estado": "PENDIENTE"} for p in publicaciones}
    estado = {"version_formato": VERSION_FORMATO, "estado": "EN_PROGRESO", "excel_escrito": False,
              "fecha_inicio": inicio, "fecha_fin": fin, "version_extractor_historico": VERSION_EXTRACTOR_HISTORICO,
              "fecha_creacion": ahora, "fecha_ultima_actualizacion": ahora, "indices_diarios": indices_diarios,
              "resultados": catalogo}
    return actualizar_resumen(estado)


def actualizar_resumen(estado, ahora=None):
    resultados = estado["resultados"].values()
    estado["publicaciones_totales"] = len(estado["resultados"])
    # Una publicación ya fue tratada cuando alcanzó cualquier resultado
    # terminal; los contadores específicos conservan los bloqueos aparte.
    estado["publicaciones_procesadas"] = sum(x["estado"] != "PENDIENTE" for x in resultados)
    estado["publicaciones_pendientes"] = sum(x["estado"] == "PENDIENTE" for x in resultados)
    estado["publicaciones_error"] = sum(x["estado"] == "ERROR" for x in resultados)
    estado["publicaciones_indeterminadas"] = sum(x["estado"] == "INDETERMINADO" for x in resultados)
    estado["fecha_ultima_actualizacion"] = (ahora or datetime.now()).isoformat(timespec="seconds")
    return estado


def guardar_estado(ruta, estado):
    actualizar_resumen(estado); ruta = Path(ruta); ruta.parent.mkdir(parents=True, exist_ok=True)
    contenido = json.dumps(estado, ensure_ascii=False, indent=2) + "\n"
    # La validación se hace antes de reemplazar el fichero vigente: un estado
    # inválido nunca debe ocultar el último punto de reanudación correcto.
    json.loads(contenido)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=ruta.parent, delete=False) as tmp:
        tmp.write(contenido); tmp.flush(); os.fsync(tmp.fileno()); nombre = tmp.name
    os.replace(nombre, ruta)


def cargar_estado(ruta, inicio, fin):
    estado = json.loads(Path(ruta).read_text(encoding="utf-8"))
    if estado.get("fecha_inicio") != inicio or estado.get("fecha_fin") != fin or estado.get("version_formato") != VERSION_FORMATO:
        raise ValueError("Estado histórico incompatible con el intervalo solicitado")
    return actualizar_resumen(estado)


def pendientes(estado, reintentar_errores=False):
    admisibles = {"ERROR"} if reintentar_errores else {"PENDIENTE"}
    return [x for x in estado["resultados"].values() if x["estado"] in admisibles]


def registrar_resultado(estado, publicacion_id, clasificacion, convocatorias=None, metadatos=None, evidencias=None, error=None):
    if clasificacion not in {"CONVOCATORIA", "NO_CONVOCATORIA", "INDETERMINADO", "ERROR"}:
        raise ValueError("Clasificación histórica inválida")
    fila = estado["resultados"][publicacion_id]
    fila.update({"estado": clasificacion, "clasificacion_documental": clasificacion,
                 "convocatorias": convocatorias or [], "metadatos": metadatos or {},
                 "evidencias": evidencias or [], "error": error,
                 "fecha_analisis": datetime.now().isoformat(timespec="seconds"),
                 "version_extractor_historico": VERSION_EXTRACTOR_HISTORICO})
    return actualizar_resumen(estado)


def puede_escribir_excel(estado):
    actualizar_resumen(estado)
    return (estado["estado"] != "COMPLETADO" and estado["publicaciones_pendientes"] == 0
            and estado["publicaciones_error"] == 0 and estado["publicaciones_indeterminadas"] == 0)


def integridad_excel(ruta):
    ruta = Path(ruta); dato = ruta.read_bytes(); s = ruta.stat()
    return {"sha256": hashlib.sha256(dato).hexdigest(), "tamano": s.st_size, "mtime": s.st_mtime}


def marcar_completado(estado, ahora=None):
    if not puede_escribir_excel(estado): raise RuntimeError("El intervalo no está listo para escritura final")
    estado.update({"estado": "COMPLETADO", "excel_escrito": True,
                   "fecha_escritura": (ahora or datetime.now()).isoformat(timespec="seconds")})
    return actualizar_resumen(estado)


def ejecutar_intervalo(inicio, fin, descubrir, procesar, commit, *, directorio="informes/procesamiento_historico_2004", limite=None, reintentar_errores=False):
    """Orquestador sin Excel parcial: descubre/persiste antes de toda descarga."""
    ruta = ruta_estado(inicio, fin, directorio)
    if ruta.exists():
        estado = cargar_estado(ruta, inicio, fin)
        if estado.get("estado") == "COMPLETADO": return estado, False
    else:
        publicaciones, indices = descubrir()
        estado = crear_estado(inicio, fin, publicaciones, indices)
        guardar_estado(ruta, estado)
    objetivo = pendientes(estado, reintentar_errores)
    if limite is not None: objetivo = objetivo[:limite]
    for ficha in objetivo:
        try:
            dato = procesar(ficha)
            metadatos = {"titulo": ficha.get("titulo", ""), "departamento": ficha.get("departamento", ""),
                         **(dato.get("metadatos") or {})}
            registrar_resultado(estado, ficha["Publicacion_ID"], dato["clasificacion"], dato.get("convocatorias"),
                                metadatos, dato.get("evidencias"), dato.get("error"))
        except KeyboardInterrupt:
            guardar_estado(ruta, estado); raise
        except Exception as error:
            registrar_resultado(estado, ficha["Publicacion_ID"], "ERROR", error=str(error))
        guardar_estado(ruta, estado)
    if puede_escribir_excel(estado):
        commit(estado)
        marcar_completado(estado); guardar_estado(ruta, estado)
        return estado, True
    return estado, False


def procesar_intervalo_historico(fecha_inicio, fecha_fin, *, descubrir, procesar_publicacion,
                                 commit_final, limite_publicaciones=None,
                                 reintentar_errores=False, directorio="informes/procesamiento_historico_2004"):
    """Interfaz pública única para el flujo histórico transaccional."""
    return ejecutar_intervalo(fecha_inicio, fecha_fin, descubrir, procesar_publicacion,
                              commit_final, directorio=directorio,
                              limite=limite_publicaciones,
                              reintentar_errores=reintentar_errores)
