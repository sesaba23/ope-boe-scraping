"""Cargador histórico reanudable: BOE -> JSON y commit explícito a SQLite."""
import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import time

import requests

from boe_api import extraer_publicaciones_2b_api, obtener_sumario_api
from extractor_historico_boe import extraer_desde_contenido
from procesamiento_historico import (crear_estado, cargar_estado, guardar_estado,
                                     pendientes, registrar_resultado, ruta_estado)
from publicaciones import registrar_publicacion
from cobertura import registrar_cobertura
from mapa_plazas import enriquecer_filas_sin_coordenadas
from resolucion_administraciones import VERSION_RESOLUCION, resolver_administracion
from resolucion_administraciones import enriquecer_convocatorias
import pandas as pd
from tqdm import tqdm

import base_datos


VERSION_EXTRACTOR_HISTORICO = "historico-experimental-2004"
CLASIFICACIONES = {"CONVOCATORIA", "NO_CONVOCATORIA", "INDETERMINADO", "ERROR"}
CLAVE_DEDUPLICACION = ["Puesto", "Fecha_boe", "Administración", "Enlace", "Num_plazas",
                       "Turno", "Sistema", "Escala", "Subescala", "Clase"]


class ProgresoDocumental:
    """Presentación del lote actual, sin formar parte del estado persistido."""
    def __init__(self, total, contadores, stream=None):
        self.total, self.contadores = total, contadores
        self.stream = stream or sys.stdout
        self.inicio = time.monotonic()
        self.actual = 0
        self.tty = bool(getattr(self.stream, "isatty", lambda: False)())
        self.intervalo = max(1, total // 10) if total else 1
        self.barra = tqdm(total=total, desc="Procesando publicaciones", file=self.stream,
                          dynamic_ncols=True, disable=not self.tty) if self.tty else None
        if not self.tty:
            print(f"Lote actual: 0 / {total}", file=self.stream)

    def _resumen(self):
        transcurrido = time.monotonic() - self.inicio
        velocidad = self.actual / transcurrido if transcurrido > 0 else 0.0
        eta = "calculando..." if self.actual < 2 or velocidad <= 0 else f"{(self.total-self.actual)/velocidad:.0f}s"
        return (f"{self.actual}/{self.total} | {velocidad:.1f} pub/s | "
                f"transcurrido {transcurrido:.0f}s | ETA {eta} | "
                f"errores {self.contadores.get('ERROR', 0)} | "
                f"indeterminadas {self.contadores.get('INDETERMINADO', 0)} | "
                f"convocatorias {self.contadores.get('CONVOCATORIA', 0)} | "
                f"no convocatoria {self.contadores.get('NO_CONVOCATORIA', 0)}")

    def actualizar(self):
        self.actual += 1
        if self.barra:
            self.barra.update(1)
            self.barra.set_postfix_str(self._resumen())
        elif self.actual == self.total or self.actual % self.intervalo == 0:
            print(f"Progreso: {self._resumen()}", file=self.stream)

    def cerrar(self):
        if self.barra:
            self.barra.close()


def _fechas(desde, hasta):
    actual = datetime.fromisoformat(desde); fin = datetime.fromisoformat(hasta)
    while actual <= fin:
        yield actual.strftime("%Y/%m/%d"); actual += timedelta(days=1)


def descubrir(desde, hasta, obtener=obtener_sumario_api):
    publicaciones, vistos, dias = [], set(), []
    for fecha in _fechas(desde, hasta):
        resultado = extraer_publicaciones_2b_api(obtener(fecha))
        dias.append({"fecha": fecha, "estado": resultado["estado"], "numero_publicaciones": len(resultado.get("publicaciones", []))})
        for p in resultado.get("publicaciones", []):
            if p["Publicacion_ID"] not in vistos:
                vistos.add(p["Publicacion_ID"]); publicaciones.append({
                    "Publicacion_ID": p["Publicacion_ID"], "Fecha_boe": fecha.replace("/", "-"),
                    "Enlace": p["url_html"], "titulo": p.get("titulo", ""),
                    "departamento": p.get("departamento", ""),
                })
    return publicaciones, dias


def procesar_publicacion(ficha, obtener=requests.get):
    respuesta=obtener(ficha["Enlace"].replace("txt.php","xml.php"), timeout=20); respuesta.raise_for_status()
    resultado=extraer_desde_contenido(ficha["Publicacion_ID"],respuesta.content,ficha["Enlace"].replace("txt.php","xml.php"),ficha["Enlace"])
    filas=[x for x in resultado["convocatorias"] if x.get("Puesto") and isinstance(x.get("Num_plazas"),int)]
    filas, _ = enriquecer_convocatorias(filas, {
        "titulo": ficha.get("titulo", ""), "departamento": ficha.get("departamento", ""),
    })
    return resultado["clasificacion_documento"], filas


def _convocatorias_validas(convocatorias):
    """El estado de fase 1 conserva únicamente filas utilizables aguas abajo."""
    return [fila for fila in (convocatorias or [])
            if fila.get("Puesto") and isinstance(fila.get("Num_plazas"), int)
            and not isinstance(fila.get("Num_plazas"), bool) and fila["Num_plazas"] > 0]


def ejecutar(desde,hasta,limite=None,reintentar=False,directorio="informes/procesamiento_historico_2004", descubrir_fn=descubrir, procesar_fn=procesar_publicacion, progreso_factory=ProgresoDocumental, stream=None):
    ruta=ruta_estado(desde,hasta,directorio)
    existe_estado = ruta.exists()
    if existe_estado: estado=cargar_estado(ruta,desde,hasta)
    else:
        catalogo,dias=descubrir_fn(desde,hasta); estado=crear_estado(desde,hasta,catalogo,dias); guardar_estado(ruta,estado)
    objetivo=pendientes(estado,reintentar)
    if limite is not None: objetivo=objetivo[:limite]
    salida = stream or sys.stdout
    if existe_estado:
        print(f"Estado existente: Procesadas acumuladas: {estado['publicaciones_procesadas']} / {estado['publicaciones_totales']}; Pendientes globales: {estado['publicaciones_pendientes']}", file=salida)
    contadores = {clase: 0 for clase in CLASIFICACIONES}
    for valor in estado["resultados"].values():
        contadores[valor["estado"]] = contadores.get(valor["estado"], 0) + 1
    progreso = progreso_factory(len(objetivo), contadores, salida)
    for ficha in objetivo:
        anterior = ficha["estado"]
        try:
            clase,filas=procesar_fn(ficha)
            registrar_resultado(estado, ficha["Publicacion_ID"], clase, _convocatorias_validas(filas),
                                metadatos={"titulo": ficha.get("titulo", ""),
                                           "departamento": ficha.get("departamento", "")})
        except KeyboardInterrupt:
            guardar_estado(ruta,estado); progreso.cerrar()
            print(f"Procesamiento interrumpido. Procesadas acumuladas: {estado['publicaciones_procesadas']} / {estado['publicaciones_totales']}; Pendientes: {estado['publicaciones_pendientes']}; Errores: {estado['publicaciones_error']}; Estado guardado correctamente.", file=salida)
            raise
        except Exception as e: registrar_resultado(estado,ficha["Publicacion_ID"],"ERROR",error=str(e))
        nuevo = estado["resultados"][ficha["Publicacion_ID"]]["estado"]
        contadores[anterior] = contadores.get(anterior, 0) - 1
        contadores[nuevo] = contadores.get(nuevo, 0) + 1
        guardar_estado(ruta,estado)
        progreso.actualizar()
    progreso.cerrar()
    return estado,ruta


def _validar_estado_aplicable(estado, desde, hasta):
    if estado.get("estado") == "COMPLETADO":
        return
    if estado.get("fecha_inicio") != desde or estado.get("fecha_fin") != hasta:
        raise ValueError("El estado no corresponde al intervalo solicitado")
    resultados = estado.get("resultados")
    if not isinstance(resultados, dict) or not resultados:
        raise ValueError("El catálogo del estado no es válido")
    pendientes = sum(x.get("estado") == "PENDIENTE" for x in resultados.values())
    if pendientes:
        numero = f"{pendientes:,}".replace(",", ".")
        raise RuntimeError(
            "El estado histórico está incompleto: "
            f"quedan {numero} publicaciones pendientes de procesar. "
            "Continúe el procesamiento antes de usar --aplicar."
        )
    errores = sum(x.get("estado") == "ERROR" for x in resultados.values())
    if errores:
        raise RuntimeError(
            f"No se puede aplicar: existen {errores} publicaciones con ERROR"
        )
    ids = set()
    for publicacion_id, resultado in resultados.items():
        if publicacion_id in ids or resultado.get("Publicacion_ID") != publicacion_id:
            raise ValueError("El catálogo contiene Publicacion_ID duplicados o incoherentes")
        ids.add(publicacion_id)
        if resultado.get("estado") not in {"CONVOCATORIA", "NO_CONVOCATORIA", "INDETERMINADO"}:
            raise ValueError("El estado contiene una clasificación inválida")


def _filas_historicas(estado):
    filas = []
    for ficha in estado["resultados"].values():
        if ficha["estado"] != "CONVOCATORIA":
            continue
        for convocatoria in _convocatorias_validas(ficha.get("convocatorias")):
            fila = dict(convocatoria)
            fila.update({
                "Publicacion_ID": ficha["Publicacion_ID"],
                "Enlace": ficha.get("Enlace") or convocatoria.get("Enlace") or "--",
                "Fecha_boe": convocatoria.get("Fecha_boe") or ficha.get("Fecha_boe") or "--",
                "Administración": convocatoria.get("Administración") or "--",
                "Version_extractor": VERSION_EXTRACTOR_HISTORICO,
                "Fecha_analisis": ficha.get("fecha_analisis") or "",
            })
            for campo in ("Turno", "Sistema", "Escala", "Subescala", "Clase"):
                fila[campo] = fila.get(campo) or "--"
            filas.append(fila)
    return filas


def _publicaciones_historicas(estado, df_publicaciones):
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    indeterminadas = 0
    for ficha in estado["resultados"].values():
        clasificacion = ficha["estado"]
        validas = _convocatorias_validas(ficha.get("convocatorias"))
        # Coincidencias siempre significa filas válidas antes de la
        # deduplicación global. Una convocatoria sin filas válidas no prueba
        # ausencia de plazas: queda explícitamente como indeterminada.
        if clasificacion == "CONVOCATORIA" and validas:
            estado_analisis, coincidencias = "con_coincidencias", len(validas)
        elif clasificacion == "CONVOCATORIA":
            estado_analisis, coincidencias = "indeterminado", 0
            indeterminadas += 1
        elif clasificacion == "NO_CONVOCATORIA":
            estado_analisis, coincidencias = "sin_coincidencias", 0
        elif clasificacion == "INDETERMINADO":
            estado_analisis, coincidencias = "indeterminado", 0
            indeterminadas += 1
        else:
            raise RuntimeError("No se puede trasladar una publicación con ERROR")
        metadatos = ficha.get("metadatos") or {}
        titulo = metadatos.get("titulo") or ficha.get("titulo", "")
        departamento = metadatos.get("departamento") or ficha.get("departamento", "")
        resolucion = resolver_administracion(titulo, departamento)
        registro = {
            "Publicacion_ID": ficha["Publicacion_ID"], "Enlace": ficha.get("Enlace"),
            "Fecha_BOE": ficha.get("Fecha_boe"),
            "Titulo_original": titulo,
            "Fecha_ultimo_analisis": ficha.get("fecha_analisis") or ahora,
            "Version_extractor": VERSION_EXTRACTOR_HISTORICO,
            "Estado_analisis": estado_analisis, "Coincidencias": coincidencias,
            "Departamento_BOE": departamento,
            "Administracion_resuelta": resolucion.administracion,
            "Familia_administrativa": resolucion.familia,
            "Estado_resolucion": resolucion.estado,
            "Metodo_resolucion": resolucion.metodo,
            "Confianza_resolucion": resolucion.confianza,
            "Version_resolucion": VERSION_RESOLUCION,
        }
        df_publicaciones = registrar_publicacion(df_publicaciones, registro)
    return df_publicaciones, indeterminadas


def _estados_historicos_2004(directorio):
    """Devuelve el último resultado persistido por ID, respetando solapamientos."""
    resultados = {}
    for ruta in sorted(Path(directorio).glob("estado_2004-*.json")):
        estado = json.loads(ruta.read_text(encoding="utf-8"))
        if estado.get("estado") != "COMPLETADO":
            continue
        resultados.update(estado.get("resultados", {}))
    return resultados


def _semantica_publicacion_historica(ficha):
    validas = _convocatorias_validas(ficha.get("convocatorias"))
    clasificacion = ficha.get("estado")
    if clasificacion == "CONVOCATORIA" and validas:
        return "con_coincidencias", len(validas), "CONVOCATORIA_CON_VALIDAS"
    if clasificacion == "CONVOCATORIA":
        return "indeterminado", 0, "CONVOCATORIA_SIN_VALIDAS"
    if clasificacion == "NO_CONVOCATORIA":
        return "sin_coincidencias", 0, "NO_CONVOCATORIA"
    if clasificacion == "INDETERMINADO":
        return "indeterminado", 0, "INDETERMINADO"
    raise ValueError(f"No se puede migrar clasificación {clasificacion!r}")


def plan_correccion_publicaciones_2004(ruta_bd="datos/boe.db", directorio="informes/procesamiento_historico_2004"):
    """Calcula, sin escribir, la corrección semántica SQLite de 2004."""
    datos = base_datos.cargar_historico_para_aplicar(ruta_bd, "2004-01-01", "2004-12-31")
    publicaciones = datos["Publicaciones"].copy(deep=True)
    oposiciones = datos["Oposiciones"]
    estados = _estados_historicos_2004(directorio)
    mascara = publicaciones["Publicacion_ID"].astype(str).str.match(r"^BOE-[A-Z]-2004-\d+$", na=False)
    reales = oposiciones.groupby("Publicacion_ID").size()
    cambios, origenes, diferencias = [], {}, []
    for indice, fila in publicaciones[mascara].iterrows():
        publicacion_id = fila["Publicacion_ID"]
        ficha = estados.get(publicacion_id)
        if ficha is None:
            raise ValueError(f"Falta estado histórico para {publicacion_id}")
        estado, coincidencias, origen = _semantica_publicacion_historica(ficha)
        origenes[origen] = origenes.get(origen, 0) + 1
        declaradas = int(fila["Coincidencias"])
        finales = int(reales.get(publicacion_id, 0))
        if declaradas != finales:
            tipo = ("DIFERENCIA_POR_DEDUPLICACION"
                    if declaradas == coincidencias and finales < declaradas
                    else "INCONSISTENCIA_REAL")
            diferencias.append({"Publicacion_ID": publicacion_id, "validas_antes_deduplicacion": coincidencias,
                                "Coincidencias_declaradas": declaradas, "filas_finales": finales, "tipo": tipo})
        if fila["Estado_analisis"] != estado or declaradas != coincidencias:
            cambios.append({"indice": indice, "Publicacion_ID": publicacion_id,
                            "desde_estado": fila["Estado_analisis"], "a_estado": estado,
                            "desde_coincidencias": declaradas, "a_coincidencias": coincidencias})
    transiciones = {}
    for cambio in cambios:
        clave = f"{cambio['desde_estado']} → {cambio['a_estado']}"
        transiciones[clave] = transiciones.get(clave, 0) + 1
    return {"datos": datos, "publicaciones": publicaciones, "cambios": cambios, "origenes": origenes,
            "transiciones": transiciones, "diferencias": diferencias}


def corregir_publicaciones_2004(*, ruta_bd="datos/boe.db", directorio="informes/procesamiento_historico_2004",
                                dry_run=True, backup_directorio="backups/sqlite"):
    """Corrige solo Publicaciones 2004; el modo por defecto nunca escribe."""
    plan = plan_correccion_publicaciones_2004(ruta_bd, directorio)
    resumen = {"dry_run": dry_run, "cambios": len(plan["cambios"]), "transiciones": plan["transiciones"],
               "origenes": plan["origenes"], "diferencias": plan["diferencias"],
               "deduplicacion_legitima": sum(x["tipo"] == "DIFERENCIA_POR_DEDUPLICACION" for x in plan["diferencias"]),
               "inconsistencias_reales": sum(x["tipo"] == "INCONSISTENCIA_REAL" for x in plan["diferencias"])}
    if dry_run:
        return resumen
    publicaciones = plan["publicaciones"]
    for cambio in plan["cambios"]:
        publicaciones.at[cambio["indice"], "Estado_analisis"] = cambio["a_estado"]
        publicaciones.at[cambio["indice"], "Coincidencias"] = cambio["a_coincidencias"]
    escritura = base_datos.persistir_lote_historico(
        ruta_bd, pd.DataFrame(columns=datos["Oposiciones"].columns), publicaciones,
        datos["Cobertura"], "2004-01-01", "2004-12-31", backup_directorio)
    resumen.update({"dry_run": False, **escritura})
    return resumen


def _cobertura_historica(estado, df_cobertura):
    momento = datetime.now()
    for indice in estado.get("indices_diarios", []):
        estado_indice = indice.get("estado")
        if estado_indice == "SIN_EDICION":
            estado_cobertura, numero = "sin_edicion", 0
        elif estado_indice in {"CON_PUBLICACIONES", "SIN_SECCION_2B", "consultado"}:
            estado_cobertura, numero = "consultado", indice.get("numero_publicaciones", 0)
        else:
            estado_cobertura, numero = "error", None
        df_cobertura = registrar_cobertura(df_cobertura, indice["fecha"], estado_cobertura,
                                            numero, momento=momento,
                                            version_actual=VERSION_EXTRACTOR_HISTORICO)
    return df_cobertura


def _combinar_oposiciones(df_existentes, filas):
    nuevas = pd.DataFrame(filas)
    combinado = pd.concat([df_existentes, nuevas], ignore_index=True, sort=False)
    clave = [campo for campo in CLAVE_DEDUPLICACION if campo in combinado.columns]
    antes = len(combinado)
    combinado = combinado.drop_duplicates(subset=clave, keep="last")
    return combinado, antes - len(combinado)


def _oposiciones_nuevas(df_existentes, oposiciones_finales):
    """Obtiene del resultado deduplicado únicamente las claves no presentes."""
    clave = [campo for campo in CLAVE_DEDUPLICACION if campo in oposiciones_finales.columns]
    existentes = {
        tuple("" if pd.isna(valor) else str(valor) for valor in fila)
        for fila in df_existentes.loc[:, clave].itertuples(index=False, name=None)
    }
    mascara = [
        tuple("" if pd.isna(valor) else str(valor) for valor in fila) not in existentes
        for fila in oposiciones_finales.loc[:, clave].itertuples(index=False, name=None)
    ]
    return oposiciones_finales.loc[mascara].copy(deep=True)


def _geolocalizar_nuevas(filas):
    """Reutiliza el geolocalizador existente una vez por administración idéntica."""
    nuevas = pd.DataFrame(filas)
    if nuevas.empty or "Administración" not in nuevas:
        return nuevas
    representantes = nuevas.drop_duplicates(subset=["Administración"], keep="last")
    localizadas = enriquecer_filas_sin_coordenadas(representantes)
    campos = [campo for campo in ("Municipio", "Provincia", "Latitud", "Longitud", "Habitantes")
              if campo in localizadas]
    for _, representativa in localizadas.iterrows():
        mascara = nuevas["Administración"] == representativa["Administración"]
        for campo in campos:
            nuevas.loc[mascara, campo] = representativa[campo]
    return nuevas


def _preparar_aplicacion(estado, ruta_bd):
    dataframes = base_datos.cargar_historico_para_aplicar(
        ruta_bd, estado["fecha_inicio"], estado["fecha_fin"])
    filas = _filas_historicas(estado)
    # La geolocalización existente se aplica solo a las filas nuevas; volver a
    # recorrer todo el histórico sería innecesario y alteraría datos previos.
    nuevas = _geolocalizar_nuevas(filas)
    oposiciones, duplicados = _combinar_oposiciones(dataframes["Oposiciones"], nuevas.to_dict(orient="records"))
    publicaciones, indeterminadas = _publicaciones_historicas(estado, dataframes["Publicaciones"])
    cobertura = _cobertura_historica(estado, dataframes["Cobertura"])
    sin_geo = sum(pd.isna(nuevas["Latitud"])) if "Latitud" in nuevas else len(filas)
    resumen = {"convocatorias_validas": len(filas), "filas_anadir": len(oposiciones) - len(dataframes["Oposiciones"]),
               "duplicados": duplicados, "plazas_totales": sum(x["Num_plazas"] for x in filas),
               "convocatoria": sum(x["estado"] == "CONVOCATORIA" for x in estado["resultados"].values()),
               "no_convocatoria": sum(x["estado"] == "NO_CONVOCATORIA" for x in estado["resultados"].values()),
               "indeterminado": indeterminadas, "cobertura": len(cobertura) - len(dataframes["Cobertura"]),
               "sin_geolocalizacion": int(sin_geo)}
    return dataframes, oposiciones, publicaciones, cobertura, resumen


def aplicar(desde, hasta, *, ruta_bd="datos/boe.db", directorio="informes/procesamiento_historico_2004", dry_run=False, backup_directorio="backups/sqlite"):
    ruta = ruta_estado(desde, hasta, directorio)
    estado = cargar_estado(ruta, desde, hasta)
    _validar_estado_aplicable(estado, desde, hasta)
    dataframes, oposiciones, publicaciones, cobertura, resumen = _preparar_aplicacion(estado, ruta_bd)
    if dry_run:
        return {"dry_run": True, "ruta_estado": ruta, **resumen}
    nuevas = base_datos.normalizar_oposiciones_dataframe(
        _oposiciones_nuevas(dataframes["Oposiciones"], oposiciones)
    )
    escritura = base_datos.persistir_lote_historico(
        ruta_bd, nuevas, publicaciones, cobertura, desde, hasta, backup_directorio)
    if not escritura["cambios"]:
        return {"dry_run": False, "ruta_estado": ruta, **escritura, **resumen}
    estado.update({"estado": "COMPLETADO", "sqlite_escrito": escritura["cambios"],
                   "fecha_escritura": datetime.now().isoformat(timespec="seconds"),
                   "backup": escritura["backup"], "data_version": escritura["data_version"],
                   "filas_oposiciones_anadidas": resumen["filas_anadir"],
                   "publicaciones_actualizadas": len(estado["resultados"]),
                   "indeterminadas_registradas": resumen["indeterminado"]})
    guardar_estado(ruta, estado)
    return {"dry_run": False, "ruta_estado": ruta, **escritura, **resumen}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--desde",required=True); p.add_argument("--hasta",required=True); p.add_argument("--limite-publicaciones",type=int); p.add_argument("--reintentar-errores",action="store_true"); p.add_argument("--aplicar", action="store_true"); p.add_argument("--dry-run", action="store_true"); p.add_argument("--corregir-publicaciones-2004", action="store_true"); p.add_argument("--base-datos", default="datos/boe.db")
    a=p.parse_args(argv)
    if a.dry_run and not (a.aplicar or a.corregir_publicaciones_2004): p.error("--dry-run requiere --aplicar o --corregir-publicaciones-2004")
    if a.corregir_publicaciones_2004:
        resultado = corregir_publicaciones_2004(ruta_bd=a.base_datos, dry_run=not a.aplicar or a.dry_run)
        print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str)); return
    if a.aplicar:
        resultado = aplicar(a.desde, a.hasta, ruta_bd=a.base_datos, dry_run=a.dry_run)
        print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str)); return
    estado,ruta=ejecutar(a.desde, a.hasta, a.limite_publicaciones, a.reintentar_errores)
    print(f"Estado: {ruta}; procesadas={estado['publicaciones_procesadas']}/{estado['publicaciones_totales']}; pendientes={estado['publicaciones_pendientes']}; errores={estado['publicaciones_error']}; indeterminadas={estado['publicaciones_indeterminadas']}")

if __name__=="__main__": main()
