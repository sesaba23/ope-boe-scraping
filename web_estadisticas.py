import argparse
import calendar
from datetime import datetime, timedelta
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlsplit

from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, url_for
from werkzeug.datastructures import MultiDict
from werkzeug.exceptions import BadRequest

from actualizacion_boe import GestorActualizaciones, determinar_actualizacion_intervalo

from consultas_boe import (
    ErrorConsultaSQLite, buscar_municipios, buscar_oposiciones,
    buscar_sugerencias_puesto, metadata, obtener_data_version, obtener_oposicion,
    opciones_busqueda, opciones_filtros, cobertura_mes, detalle_cobertura_dia,
    resumen_cobertura, resumen_cobertura_y_mes, resumen_mapa_oposiciones, buscar_oposiciones_sin_coordenadas,
    opciones_dias_inhabiles, calendario_dias_inhabiles, detalle_dia_inhabil,
)
from cache_estadisticas import CacheEstadisticas, clave_estadisticas
from estadisticas import (
    calcular_comparacion_puestos, calcular_estadisticas, cargar_datos_estadisticas_sqlite,
    filtrar_datos,
)
from gestion_exportacion import GestorExportacionXlsx
import servicio_exportacion
from tipo_personal import TIPOS_PERSONAL


_FILTROS_RETORNO_OPOSICIONES = (
    "texto", "fecha_desde", "fecha_hasta", "administracion", "ambito",
    "comunidad_autonoma", "provincia", "municipio", "municipio_exacto",
    "municipio_provincia_exacto", "tipo_entidad", "sistema", "turno",
    "escala", "subescala", "clase", "tipo_personal", "plazo",
)
_ORDENES_RETORNO_OPOSICIONES = {
    "fecha_desc", "fecha_asc", "puesto_asc", "administracion_asc", "plazas_desc",
}

_MESES_FECHA_LARGA = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)
_MESES_COBERTURA = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def _fecha_larga(valor):
    """Formatea fechas ISO para las fichas de oposición."""
    if not valor:
        return ""
    texto = str(valor).strip()
    if re.search(r"\bde\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+de\s+\d{4}\b", texto, re.IGNORECASE):
        return texto
    fecha = None
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%Y%m%d"):
        try:
            fecha = datetime.strptime(texto[:10] if formato == "%Y-%m-%d" else texto, formato)
            break
        except ValueError:
            continue
    if fecha is None:
        return texto
    return f"{fecha.day} de {_MESES_FECHA_LARGA[fecha.month - 1]} de {fecha.year}"


def _meses_dias_inhabiles(anio, filas):
    """Construye los doce paneles mensuales para la vista del calendario."""
    por_fecha = {}
    for fila in filas:
        por_fecha.setdefault(fila["fecha"], []).append(fila)
    nombres = ("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
               "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre")
    meses = []
    for mes, nombre in enumerate(nombres, 1):
        semanas = []
        for semana in calendar.monthcalendar(int(anio), mes):
            celdas = []
            for dia in semana:
                if not dia:
                    celdas.append(None)
                    continue
                fecha = f"{int(anio):04d}-{mes:02d}-{dia:02d}"
                celdas.append({"dia": dia, "fecha": fecha, "entradas": por_fecha.get(fecha, [])})
            semanas.append(celdas)
        meses.append({"numero": mes, "nombre": nombre, "semanas": semanas})
    return meses


def _url_retorno_oposiciones(argumentos):
    """Reconstruye un destino interno con filtros y estado visual permitidos."""
    parametros = {}
    for nombre in _FILTROS_RETORNO_OPOSICIONES:
        valores = argumentos.getlist(nombre) if hasattr(argumentos, "getlist") else argumentos.get(nombre)
        if nombre == "tipo_personal":
            valores = valores if isinstance(valores, (list, tuple)) else ([valores] if valores else [])
            valores = [valor.strip() for valor in valores if str(valor).strip() in TIPOS_PERSONAL]
            if valores:
                parametros[nombre] = valores
            continue
        valor = valores[0] if isinstance(valores, (list, tuple)) and valores else valores
        if valor and str(valor).strip():
            parametros[nombre] = str(valor).strip()
    try:
        pagina = int(argumentos.get("pagina", 0))
    except (TypeError, ValueError):
        pagina = 0
    if pagina > 0:
        parametros["pagina"] = pagina
    if argumentos.get("tamano_pagina") in {"25", "50", "100"}:
        parametros["tamano_pagina"] = argumentos["tamano_pagina"]
    if argumentos.get("orden") in _ORDENES_RETORNO_OPOSICIONES:
        parametros["orden"] = argumentos["orden"]
    if argumentos.get("ver_todas") == "1":
        parametros["ver_todas"] = "1"
    if argumentos.get("vista") == "mapa":
        parametros["vista"] = "mapa"
    if argumentos.get("sin_coordenadas") == "1":
        parametros["sin_coordenadas"] = "1"
        try:
            pagina_sin_coordenadas = int(argumentos.get("pagina_sin_coordenadas", 1))
        except (TypeError, ValueError):
            pagina_sin_coordenadas = 1
        if pagina_sin_coordenadas > 0:
            parametros["pagina_sin_coordenadas"] = pagina_sin_coordenadas
    return url_for("oposiciones", **parametros)


def crear_app(ruta_bd=None, gestor_actualizaciones=None, gestor_exportacion_xlsx=None):
    app = Flask(__name__)
    app.jinja_env.filters["fecha_larga"] = _fecha_larga
    app.extensions["cache_estadisticas"] = CacheEstadisticas()
    ruta_fijada = Path(ruta_bd or Path.cwd() / "datos/boe.db").expanduser()
    app.config["RUTA_BD"] = ruta_fijada.resolve()
    app.config["GESTOR_ACTUALIZACIONES"] = gestor_actualizaciones or GestorActualizaciones(app.config["RUTA_BD"])
    import gestion_base
    app.config["GESTOR_PUBLICACION"] = gestion_base.GestorPublicacion()
    app.config["GESTOR_ACTUALIZACION_BASE"] = gestion_base.GestorActualizacionBase()
    app.config["GESTOR_EXPORTACION_XLSX"] = gestor_exportacion_xlsx or GestorExportacionXlsx()

    def filtros_oposiciones_desde_request():
        """Lee una sola vez los filtros lógicos compartidos por listado y mapa."""
        nombres = (
            "texto", "fecha_desde", "fecha_hasta", "administracion", "ambito",
            "comunidad_autonoma", "provincia", "municipio", "tipo_entidad",
            "sistema", "turno", "escala", "subescala", "clase", "plazo",
        )
        filtros = {nombre: (request.args.get(nombre) or "").strip() for nombre in nombres}
        if filtros["plazo"] not in {"", "todas", "en_plazo"}:
            raise BadRequest("plazo no válido: debe ser 'todas' o 'en_plazo'")
        tipos = [valor.strip() for valor in request.args.getlist("tipo_personal") if valor.strip()]
        invalidos = sorted(set(tipos) - set(TIPOS_PERSONAL))
        if invalidos:
            raise BadRequest("tipo_personal no válido: " + ", ".join(invalidos))
        filtros["tipo_personal"] = list(dict.fromkeys(tipos))
        exactos = {
            "municipio_exacto": (request.args.get("municipio_exacto") or "").strip(),
            "municipio_provincia_exacto": (request.args.get("municipio_provincia_exacto") or "").strip(),
        }
        return filtros, exactos

    def filtros_exportacion_desde_request():
        """Valida los mismos filtros lógicos que el listado, sin paginación."""
        filtros, exactos = filtros_oposiciones_desde_request()
        inicio = _validar_fecha(filtros["fecha_desde"] or None, "fecha_desde")
        final = _validar_fecha(filtros["fecha_hasta"] or None, "fecha_hasta")
        if inicio and final and inicio > final:
            raise ValueError("La fecha desde no puede ser posterior a la fecha hasta.")
        return {
            **{nombre: valor or None for nombre, valor in filtros.items()},
            "municipio_exacto": exactos["municipio_exacto"] or None,
            "municipio_provincia_exacto": exactos["municipio_provincia_exacto"] or None,
            "orden": request.args.get("orden", "fecha_desc"),
        }

    def respuesta_descarga_temporal(ruta, nombre, mimetype):
        """Envía un temporal propio y lo elimina cuando Flask cierra la respuesta."""
        respuesta = send_file(ruta, as_attachment=True, download_name=nombre, mimetype=mimetype)
        respuesta.headers["Cache-Control"] = "no-store"
        respuesta.call_on_close(lambda: Path(ruta).unlink(missing_ok=True))
        return respuesta

    def ruta_temporal_exportacion(sufijo):
        import os
        import tempfile

        descriptor, nombre = tempfile.mkstemp(prefix="boe-exportacion-", suffix=sufijo)
        os.close(descriptor)
        ruta = Path(nombre)
        ruta.unlink(missing_ok=True)
        return ruta

    @app.get("/")
    def inicio():
        return render_template("inicio.html", seccion_activa="inicio")

    @app.get("/acerca-de")
    def acerca_de():
        return render_template("acerca_de.html", seccion_activa="acerca")

    @app.get("/contacto")
    def contacto():
        return render_template("contacto.html", seccion_activa="contacto")

    @app.get("/terminos-y-condiciones")
    def terminos_condiciones():
        return render_template("terminos_condiciones.html", seccion_activa=None)

    @app.get("/politica-de-privacidad")
    def politica_privacidad():
        return render_template("politica_privacidad.html", seccion_activa=None)

    @app.get("/cobertura")
    def cobertura():
        hoy = datetime.today()
        try:
            anio = int(request.args.get("anio", hoy.year))
            mes = int(request.args.get("mes", hoy.month))
            if not 2004 <= anio <= hoy.year or not 1 <= mes <= 12:
                raise ValueError("El periodo de cobertura no es válido.")
            if (anio, mes) > (hoy.year, hoy.month):
                raise ValueError("No se puede consultar un mes futuro.")
            resumen, calendario = resumen_cobertura_y_mes(
                app.config["RUTA_BD"], anio=anio, mes=mes, hoy=hoy.date()
            )
        except (ErrorConsultaSQLite, ValueError) as error:
            return render_template("error.html", seccion_activa="cobertura", codigo=400, mensaje=str(error)), 400
        fecha_hoy = hoy.date().isoformat()
        dias_mes = [dia for dia in calendario["dias"] if not dia.get("vacio") and dia["fecha"] <= fecha_hoy]
        mes_actualizado = bool(dias_mes) and all(dia["cubierto"] for dia in dias_mes)
        todo_actualizado = resumen["dias_pendientes"] == 0
        return render_template(
            "cobertura.html", seccion_activa="cobertura", resumen=resumen, calendario=calendario,
            nombre_mes=_MESES_COBERTURA[mes - 1], mes_actualizado=mes_actualizado,
            todo_actualizado=todo_actualizado, anio_actual=hoy.year, mes_actual=hoy.month,
        )

    @app.get("/dias-inhabiles")
    def dias_inhabiles():
        try:
            opciones = opciones_dias_inhabiles(app.config["RUTA_BD"])
            anios = opciones["anios"]
            if anios:
                anio = int(request.args.get("anio", anios[0]))
                if anio not in anios:
                    raise ValueError("El año de días inhábiles no está disponible.")
            else:
                anio = datetime.today().year
            comunidades_disponibles = opciones["comunidades"]
            recibidas = request.args.getlist("comunidad")
            comunidades = [valor for valor in recibidas if valor in comunidades_disponibles]
            if not request.args.get("comunidades_aplicadas"):
                comunidades = list(comunidades_disponibles)
            filas = calendario_dias_inhabiles(
                app.config["RUTA_BD"], anio=anio, comunidades=comunidades,
            )
        except (ErrorConsultaSQLite, ValueError) as error:
            return render_template("error.html", seccion_activa="dias_inhabiles", codigo=400, mensaje=str(error)), 400
        colores = {
            comunidad: f"dias-inhabiles-color--{indice % 8}"
            for indice, comunidad in enumerate(comunidades_disponibles)
        }
        return render_template(
            "dias_inhabiles.html", seccion_activa="dias_inhabiles", anio=anio,
            anios=anios, comunidades=comunidades_disponibles,
            comunidades_seleccionadas=comunidades, meses=_meses_dias_inhabiles(anio, filas),
            colores=colores,
        )

    @app.get("/administracion/base-datos")
    def administracion_base_datos():
        import gestion_base
        ruta = app.config["RUTA_BD"]
        try:
            estado = gestion_base.estado_local(ruta)
            estado["requiere_actualizacion"] = estado["schema_version"] < gestion_base.SCHEMA_REQUERIDO
        except Exception as error:
            return render_template("error.html", seccion_activa="administracion", codigo=503, mensaje=str(error)), 503
        return render_template("administracion_base_datos.html", seccion_activa="administracion", estado=estado)

    @app.get("/administracion/base-datos/exportar.zip")
    def exportar_base_csv():
        ruta = ruta_temporal_exportacion(".zip")
        try:
            servicio_exportacion.exportar_base_csv_zip(app.config["RUTA_BD"], ruta)
            return respuesta_descarga_temporal(
                ruta, f"boe_base_completa_{datetime.today():%Y%m%d}.zip", "application/zip"
            )
        except ErrorConsultaSQLite:
            ruta.unlink(missing_ok=True)
            return jsonify({"error": "La base de datos no está disponible."}), 503
        except Exception:
            ruta.unlink(missing_ok=True)
            app.logger.exception("No se pudo exportar la base completa como ZIP")
            return jsonify({"error": "No se pudo preparar la exportación."}), 500

    @app.post("/api/administracion/base-datos/exportacion")
    def api_iniciar_exportacion_base_xlsx():
        trabajo, creado = app.config["GESTOR_EXPORTACION_XLSX"].iniciar(app.config["RUTA_BD"])
        return jsonify({"creado": creado, "trabajo": trabajo.serializar()}), 202

    @app.get("/api/administracion/base-datos/exportacion")
    def api_estado_exportacion_base_xlsx():
        estado = app.config["GESTOR_EXPORTACION_XLSX"].obtener()
        return jsonify(estado or {"estado": "sin_trabajo"})

    @app.get("/administracion/base-datos/exportar.xlsx")
    def descargar_exportacion_base_xlsx():
        ruta = app.config["GESTOR_EXPORTACION_XLSX"].archivo_preparado()
        if ruta is None:
            return jsonify({"error": "La exportación XLSX completa todavía no está preparada."}), 409
        respuesta = send_file(
            ruta, as_attachment=True,
            download_name=f"boe_base_completa_{datetime.today():%Y%m%d}.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        respuesta.headers["Cache-Control"] = "no-store"
        return respuesta

    @app.post("/api/administracion/base-datos/verificar")
    def api_verificar_base_datos():
        import gestion_base
        try:
            return jsonify(gestion_base.verificar_integridad(app.config["RUTA_BD"]))
        except gestion_base.GestionBaseError as error:
            return jsonify({"error": str(error)}), 400

    @app.post("/api/administracion/base-datos/preparar-publicacion")
    def api_preparar_publicacion():
        import gestion_base
        try:
            return jsonify({"confirmacion_requerida": True, "manifest": gestion_base.crear_manifest(app.config["RUTA_BD"])})
        except gestion_base.GestionBaseError as error:
            return jsonify({"error": str(error)}), 400

    @app.post("/api/administracion/base-datos/version-publicada")
    def api_version_publicada():
        try:
            import gestion_base
            consulta = gestion_base.consultar_copia_publicada(gestion_base.repositorio_configurado())
            if consulta["estado"] != "publicada":
                return jsonify(consulta)
            respuesta = gestion_base.comparar_manifest_local(app.config["RUTA_BD"], consulta["manifest"])
            respuesta["estado"] = "publicada"
            return jsonify(respuesta)
        except Exception:
            app.logger.exception("No se pudo comprobar la copia publicada")
            return jsonify({"error": "No se pudo comprobar la copia publicada."}), 502

    @app.post("/api/administracion/base-datos/confirmar-publicacion")
    def api_confirmar_publicacion():
        try:
            import gestion_base
            trabajo, creado = app.config["GESTOR_PUBLICACION"].iniciar(app.config["RUTA_BD"], gestion_base.repositorio_configurado())
            return jsonify({"creado": creado, "trabajo": trabajo.serializar()}), 202
        except Exception as error:
            return jsonify({"error": "No se pudo iniciar la publicación."}), 400

    @app.get("/api/administracion/base-datos/publicacion")
    def api_estado_publicacion():
        estado = app.config["GESTOR_PUBLICACION"].obtener()
        return jsonify(estado or {"estado": "sin_trabajo"})

    @app.post("/api/administracion/base-datos/preparar-actualizacion")
    def api_preparar_actualizacion_base():
        import gestion_base
        try:
            comparacion = gestion_base.preparar_actualizacion_github(app.config["RUTA_BD"], gestion_base.repositorio_configurado())
            return jsonify({"confirmacion_requerida": True, **comparacion})
        except gestion_base.GestionBaseError as error:
            return jsonify({"error": str(error)}), 400

    @app.post("/api/administracion/base-datos/confirmar-actualizacion")
    def api_confirmar_actualizacion_base():
        import gestion_base
        try:
            trabajo, creado = app.config["GESTOR_ACTUALIZACION_BASE"].iniciar(app.config["RUTA_BD"], gestion_base.repositorio_configurado())
            return jsonify({"creado": creado, "trabajo": trabajo.serializar()}), 202
        except gestion_base.GestionBaseError as error:
            return jsonify({"error": str(error)}), 409

    @app.get("/api/administracion/base-datos/actualizacion")
    def api_estado_actualizacion_base():
        estado = app.config["GESTOR_ACTUALIZACION_BASE"].obtener()
        return jsonify(estado or {"estado": "sin_trabajo"})

    @app.get("/oposiciones")
    def oposiciones():
        filtros, exactos = filtros_oposiciones_desde_request()
        municipio_exacto = exactos["municipio_exacto"]
        municipio_provincia_exacto = exactos["municipio_provincia_exacto"]
        vista_mapa = request.args.get("vista") == "mapa"
        orden = request.args.get("orden", "fecha_desc")
        try:
            pagina = max(1, int(request.args.get("pagina", 1)))
            tamano_pagina = int(request.args.get("tamano_pagina", 25))
            if tamano_pagina not in (25, 50, 100):
                tamano_pagina = 25
            inicio = _validar_fecha(filtros["fecha_desde"] or None, "fecha_desde")
            final = _validar_fecha(filtros["fecha_hasta"] or None, "fecha_hasta")
            if inicio and final and inicio > final:
                raise ValueError("La fecha desde no puede ser posterior a la fecha hasta.")
            opciones = opciones_busqueda(
                app.config["RUTA_BD"], comunidad_autonoma=filtros["comunidad_autonoma"] or None,
                provincia=filtros["provincia"] or None, municipio=filtros["municipio"] or None,
            )
            hay_criterio = request.args.get("ver_todas") == "1" or any(
                valor for nombre, valor in filtros.items() if nombre != "plazo"
            ) or filtros["plazo"] == "en_plazo" or vista_mapa
            es_navegacion = any(nombre in request.args for nombre in ("pagina", "orden", "tamano_pagina"))
            decision_actualizacion = determinar_actualizacion_intervalo(
                app.config["RUTA_BD"], fecha_desde=filtros["fecha_desde"] or None,
                fecha_hasta=filtros["fecha_hasta"] or None,
            ) if hay_criterio and filtros["fecha_desde"] and not es_navegacion and request.args.get("actualizacion") != "error" else {"fechas_pendientes": []}
            pendientes_actualizacion = decision_actualizacion["fechas_pendientes"]
            resultados = buscar_oposiciones(
                app.config["RUTA_BD"], **{k: v or None for k, v in filtros.items()},
                municipio_exacto=municipio_exacto or None,
                municipio_provincia_exacto=municipio_provincia_exacto or None,
                pagina=pagina, tamano_pagina=tamano_pagina, orden=orden,
            ) if hay_criterio and not pendientes_actualizacion else None
        except (ErrorConsultaSQLite, ValueError) as error:
            return render_template(
                "oposiciones.html", seccion_activa="oposiciones", filtros=filtros,
                opciones={}, resultados=None, error=str(error), hay_criterio=False,
                orden=orden, tamano_pagina=25, query_actual={}, avanzados_activos=False,
                actualizacion_pendiente=[],
            ), 400
        query_actual = {**{k: v for k, v in filtros.items() if v}, "orden": orden,
                         "tamano_pagina": tamano_pagina}
        if municipio_exacto:
            query_actual["municipio_exacto"] = municipio_exacto
        if municipio_provincia_exacto:
            query_actual["municipio_provincia_exacto"] = municipio_provincia_exacto
        if request.args.get("ver_todas") == "1":
            query_actual["ver_todas"] = "1"
        if vista_mapa:
            query_actual["vista"] = "mapa"
        query_exportacion = {
            **{nombre: filtros[nombre] for nombre in _FILTROS_RETORNO_OPOSICIONES if filtros.get(nombre)},
            "orden": orden,
        }
        if municipio_exacto:
            query_exportacion["municipio_exacto"] = municipio_exacto
        if municipio_provincia_exacto:
            query_exportacion["municipio_provincia_exacto"] = municipio_provincia_exacto
        avanzados = ("tipo_entidad", "municipio", "sistema", "turno", "escala", "subescala", "clase")
        return render_template(
            "oposiciones.html", seccion_activa="oposiciones", filtros=filtros,
            opciones=opciones, resultados=resultados, error=None, hay_criterio=hay_criterio,
            orden=orden, tamano_pagina=tamano_pagina, query_actual=query_actual,
            query_exportacion=query_exportacion,
            volver_detalle=_url_retorno_oposiciones(request.args),
            avanzados_activos=any(filtros[nombre] for nombre in avanzados),
            actualizacion_pendiente=pendientes_actualizacion,
            advertencia_actualizacion=request.args.get("actualizacion") == "error",
        )

    @app.get("/oposiciones/exportar.csv")
    def exportar_oposiciones_csv():
        ruta = ruta_temporal_exportacion(".csv")
        try:
            parametros = filtros_exportacion_desde_request()
            servicio_exportacion.exportar_oposiciones_filtradas_csv(
                app.config["RUTA_BD"], ruta, **parametros
            )
            return respuesta_descarga_temporal(
                ruta, f"oposiciones_{datetime.today():%Y%m%d}.csv", "text/csv"
            )
        except ValueError as error:
            ruta.unlink(missing_ok=True)
            return jsonify({"error": str(error)}), 400
        except ErrorConsultaSQLite:
            ruta.unlink(missing_ok=True)
            return jsonify({"error": "La base de datos no está disponible."}), 503
        except Exception:
            ruta.unlink(missing_ok=True)
            app.logger.exception("No se pudieron exportar las oposiciones como CSV")
            return jsonify({"error": "No se pudo preparar la exportación."}), 500

    @app.get("/oposiciones/exportar.xlsx")
    def exportar_oposiciones_xlsx():
        ruta = ruta_temporal_exportacion(".xlsx")
        try:
            parametros = filtros_exportacion_desde_request()
            servicio_exportacion.exportar_oposiciones_filtradas_xlsx(
                app.config["RUTA_BD"], ruta, **parametros
            )
            return respuesta_descarga_temporal(
                ruta, f"oposiciones_{datetime.today():%Y%m%d}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except ValueError as error:
            ruta.unlink(missing_ok=True)
            return jsonify({"error": str(error)}), 400
        except ErrorConsultaSQLite:
            ruta.unlink(missing_ok=True)
            return jsonify({"error": "La base de datos no está disponible."}), 503
        except Exception:
            ruta.unlink(missing_ok=True)
            app.logger.exception("No se pudieron exportar las oposiciones como XLSX")
            return jsonify({"error": "No se pudo preparar la exportación."}), 500

    @app.get("/api/oposiciones/mapa")
    def api_oposiciones_mapa():
        filtros, exactos = filtros_oposiciones_desde_request()
        try:
            inicio = _validar_fecha(filtros["fecha_desde"] or None, "fecha_desde")
            final = _validar_fecha(filtros["fecha_hasta"] or None, "fecha_hasta")
            if inicio and final and inicio > final:
                raise ValueError("La fecha desde no puede ser posterior a la fecha hasta.")
            return jsonify(resumen_mapa_oposiciones(
                app.config["RUTA_BD"], **{nombre: valor or None for nombre, valor in filtros.items()},
                municipio_exacto=exactos["municipio_exacto"] or None,
                municipio_provincia_exacto=exactos["municipio_provincia_exacto"] or None,
            ))
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        except ErrorConsultaSQLite:
            return jsonify({"error": "No se pudo consultar la base de datos."}), 503
        except Exception:
            app.logger.exception("No se pudo preparar el resumen geográfico de oposiciones")
            return jsonify({"error": "No se pudo preparar el resumen geográfico."}), 500

    @app.get("/api/oposiciones/sin-coordenadas")
    def api_oposiciones_sin_coordenadas():
        filtros, exactos = filtros_oposiciones_desde_request()
        try:
            inicio = _validar_fecha(filtros["fecha_desde"] or None, "fecha_desde")
            final = _validar_fecha(filtros["fecha_hasta"] or None, "fecha_hasta")
            if inicio and final and inicio > final:
                raise ValueError("La fecha desde no puede ser posterior a la fecha hasta.")
            return jsonify(buscar_oposiciones_sin_coordenadas(
                app.config["RUTA_BD"], **{nombre: valor or None for nombre, valor in filtros.items()},
                municipio_exacto=exactos["municipio_exacto"] or None,
                municipio_provincia_exacto=exactos["municipio_provincia_exacto"] or None,
                pagina=request.args.get("pagina", 1), tamano=request.args.get("tamano", 50),
            ))
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        except ErrorConsultaSQLite:
            return jsonify({"error": "No se pudo consultar la base de datos."}), 503
        except Exception:
            app.logger.exception("No se pudo consultar las oposiciones sin coordenadas")
            return jsonify({"error": "No se pudieron consultar las oposiciones sin coordenadas."}), 500

    @app.post("/api/actualizar-busqueda")
    def api_actualizar_busqueda():
        datos = request.get_json(silent=True) or {}
        fecha_desde = (datos.get("fecha_desde") or "").strip()
        fecha_hasta = (datos.get("fecha_hasta") or "").strip()
        try:
            _validar_fecha(fecha_desde or None, "fecha_desde")
            _validar_fecha(fecha_hasta or None, "fecha_hasta")
            decision = determinar_actualizacion_intervalo(
                app.config["RUTA_BD"], fecha_desde=fecha_desde or None, fecha_hasta=fecha_hasta or None,
            )
        except (ErrorConsultaSQLite, ValueError) as error:
            return jsonify({"error": str(error)}), 400
        pendientes = decision["fechas_pendientes"]
        if not decision["requiere_actualizacion"]:
            return jsonify({"actualizacion": False})
        trabajo, creado = app.config["GESTOR_ACTUALIZACIONES"].iniciar(pendientes)
        return jsonify({"actualizacion": True, "creado": creado, "trabajo": trabajo.serializar()}), 202

    @app.get("/api/trabajos/<trabajo_id>")
    def api_trabajo_actualizacion(trabajo_id):
        trabajo = app.config["GESTOR_ACTUALIZACIONES"].obtener(trabajo_id)
        if trabajo is None:
            return jsonify({"error": "Trabajo no encontrado."}), 404
        return jsonify(trabajo)

    @app.get("/api/cobertura/dia")
    def api_cobertura_dia():
        try:
            return jsonify(detalle_cobertura_dia(app.config["RUTA_BD"], fecha=request.args.get("fecha", "")))
        except (ErrorConsultaSQLite, ValueError) as error:
            return jsonify({"error": str(error)}), 400

    @app.get("/api/dias-inhabiles/dia")
    def api_dias_inhabiles_dia():
        comunidades = request.args.getlist("comunidad")
        if not comunidades and not request.args.get("comunidades_aplicadas"):
            comunidades = None
        try:
            return jsonify(detalle_dia_inhabil(
                app.config["RUTA_BD"], fecha=request.args.get("fecha", ""),
                comunidades=comunidades,
            ))
        except (ErrorConsultaSQLite, ValueError) as error:
            return jsonify({"error": str(error)}), 400

    @app.post("/api/cobertura/actualizar")
    def api_actualizar_cobertura():
        datos = request.get_json(silent=True) or {}
        try:
            anio, mes = int(datos.get("anio")), int(datos.get("mes"))
            inicio = datetime(anio, mes, 1).date()
            siguiente = datetime(anio + (mes == 12), 1 if mes == 12 else mes + 1, 1).date()
            fin = min(siguiente - timedelta(days=1), datetime.today().date())
            if inicio > fin:
                raise ValueError("El periodo de cobertura no es válido.")
            decision = determinar_actualizacion_intervalo(
                app.config["RUTA_BD"], fecha_desde=inicio.isoformat(), fecha_hasta=fin.isoformat(),
            )
        except (TypeError, ValueError) as error:
            return jsonify({"error": str(error)}), 400
        if not decision["requiere_actualizacion"]:
            return jsonify({"actualizacion": False})
        trabajo, creado = app.config["GESTOR_ACTUALIZACIONES"].iniciar(decision["fechas_pendientes"])
        return jsonify({"actualizacion": True, "creado": creado, "trabajo": trabajo.serializar()}), 202

    @app.post("/api/cobertura/actualizar-todas")
    def api_actualizar_todas_cobertura():
        try:
            decision = determinar_actualizacion_intervalo(
                app.config["RUTA_BD"], fecha_desde="2004-01-01", fecha_hasta=datetime.today().date().isoformat(),
            )
        except (ErrorConsultaSQLite, ValueError) as error:
            return jsonify({"error": str(error)}), 400
        if not decision["requiere_actualizacion"]:
            return jsonify({"actualizacion": False, "alcance": "todas"})
        trabajo, creado = app.config["GESTOR_ACTUALIZACIONES"].iniciar(decision["fechas_pendientes"])
        return jsonify({"actualizacion": True, "alcance": "todas", "creado": creado, "trabajo": trabajo.serializar()}), 202

    @app.get("/oposiciones/<int:oposicion_id>")
    def detalle_oposicion(oposicion_id):
        try:
            oposicion = obtener_oposicion(app.config["RUTA_BD"], oposicion_id)
        except ErrorConsultaSQLite as error:
            abort(503, description=str(error))
        if oposicion is None:
            abort(404)
        destino = urlsplit(request.args.get("volver", ""))
        if not destino.scheme and not destino.netloc and destino.path == "/oposiciones":
            volver = _url_retorno_oposiciones(MultiDict(parse_qsl(destino.query, keep_blank_values=True)))
        else:
            volver = url_for("oposiciones")
        return render_template("detalle_oposicion.html", seccion_activa="oposiciones", oposicion=oposicion, volver=volver)

    @app.get("/api/filtros/provincias")
    def api_provincias():
        comunidad = (request.args.get("comunidad") or "").strip()
        try:
            opciones = opciones_busqueda(app.config["RUTA_BD"], comunidad_autonoma=comunidad or None)
        except ErrorConsultaSQLite as error:
            return jsonify({"error": str(error)}), 503
        return jsonify({"comunidad": comunidad, "provincias": opciones["provincias"]})

    @app.get("/api/filtros/municipios")
    def api_municipios():
        texto = (request.args.get("q") or "").strip()
        comunidad = (request.args.get("comunidad") or "").strip()
        provincia = (request.args.get("provincia") or "").strip()
        try:
            municipios = buscar_municipios(
                app.config["RUTA_BD"], texto, comunidad_autonoma=comunidad or None, provincia=provincia or None,
            )
        except (ErrorConsultaSQLite, ValueError) as error:
            return jsonify({"error": str(error)}), 503
        return jsonify({"q": texto, "comunidad": comunidad, "provincia": provincia, "municipios": municipios})

    @app.get("/api/filtros/puestos")
    def api_puestos():
        texto = (request.args.get("q") or "").strip()
        try:
            puestos = buscar_sugerencias_puesto(app.config["RUTA_BD"], texto)
        except (ErrorConsultaSQLite, ValueError) as error:
            return jsonify({"error": str(error)}), 503
        return jsonify({"q": texto, "puestos": puestos})

    @app.get("/estadisticas")
    def pagina_estadisticas():
        return render_template("estadisticas.html", seccion_activa="estadisticas")

    @app.get("/mapas")
    def mapas():
        filtros, exactos = filtros_oposiciones_desde_request()
        parametros = {
            **{nombre: valor for nombre, valor in filtros.items() if valor},
            **{nombre: valor for nombre, valor in exactos.items() if valor},
            "vista": "mapa",
        }
        return redirect(url_for("oposiciones", **parametros))

    @app.get("/api/estadisticas")
    def api_estadisticas():
        fecha_inicio = request.args.get("fecha_inicio") or None
        fecha_final = request.args.get("fecha_final") or None
        puesto = request.args.get("puesto") or None
        provincia = request.args.get("provincia") or None
        ambito = request.args.get("ambito") or None
        sistema = request.args.get("sistema") or None
        turno = request.args.get("turno") or None
        plazo = (request.args.get("plazo") or "").strip()
        if plazo not in {"", "todas", "en_plazo"}:
            return jsonify({"error": "plazo no válido: debe ser 'todas' o 'en_plazo'"}), 400
        tipo_personal = [valor for valor in request.args.getlist("tipo_personal") if valor]
        invalidos_tipo = sorted(set(tipo_personal) - set(TIPOS_PERSONAL))
        if invalidos_tipo:
            return jsonify({"error": "tipo_personal no válido: " + ", ".join(invalidos_tipo)}), 400
        comparadores = request.args.getlist("comparar")
        if not comparadores:
            comparadores = [request.args.get(f"comparar_{indice}") for indice in range(1, 6)]
        comparadores = [valor.strip() for valor in comparadores if valor and valor.strip()]
        if len(comparadores) > 5 or len(set(comparadores)) != len(comparadores) or (puesto and puesto in comparadores):
            return jsonify({"error": "Los puestos comparativos deben ser como máximo cinco, únicos y distintos del principal."}), 400

        try:
            inicio_dt = _validar_fecha(fecha_inicio, "fecha_inicio")
            final_dt = _validar_fecha(fecha_final, "fecha_final")
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        if inicio_dt is not None and final_dt is not None and inicio_dt > final_dt:
            return (
                jsonify({"error": "La fecha inicial no puede ser posterior a la final."}),
                400,
            )

        ruta = app.config["RUTA_BD"]
        try:
            version = obtener_data_version(ruta)
            clave = clave_estadisticas(
                version, fecha_inicio=fecha_inicio, fecha_final=fecha_final,
                puesto=puesto, provincia=provincia, ambito=ambito,
                sistema=sistema, turno=turno, tipo_personal=tipo_personal,
                comparadores=comparadores, plazo=plazo,
            )
            cache = app.extensions["cache_estadisticas"]
            entrada = cache.obtener(clave)
            if entrada is not None:
                contenido, tipos_originales = entrada
                if tipos_originales == tuple(tipo_personal):
                    return app.response_class(contenido, mimetype="application/json")
                # El orden y duplicados del filtro se reflejan en `filtros`.
                # Se conserva ese contrato aun cuando la selección OR comparte clave.
                respuesta_cacheada = app.json.loads(contenido)
                respuesta_cacheada["filtros"]["tipo_personal"] = tipo_personal
                return jsonify(respuesta_cacheada)
            opciones = opciones_filtros(ruta)
            filtros_carga = {
                "desde": fecha_inicio, "hasta": fecha_final,
                "provincia": provincia, "ambito": ambito, "sistema": sistema, "turno": turno,
                "tipo_personal": tipo_personal, "plazo": plazo,
            }
            datos_preparados = cargar_datos_estadisticas_sqlite(ruta, **filtros_carga)
            datos_principales = filtrar_datos(datos_preparados, puesto=puesto, modo_sql=True) if puesto else datos_preparados
            estadisticas = calcular_estadisticas(datos_principales, puesto_seleccionado=puesto)
            evolucion_comparada = calcular_comparacion_puestos(
                datos_preparados, puesto_principal=puesto, comparadores=comparadores)
            datos_metadata = metadata(ruta)
        except (ErrorConsultaSQLite, OSError, ValueError) as error:
            return jsonify({"error": f"No se pudieron cargar las estadísticas: {error}"}), 503

        respuesta = {
                "filtros": {
                    "fecha_inicio": fecha_inicio,
                    "fecha_final": fecha_final,
                    "puesto": puesto,
                    "provincia": provincia,
                    "ambito": ambito,
                    "sistema": sistema,
                    "turno": turno,
                    "tipo_personal": tipo_personal,
                    "plazo": plazo,
                },
                "opciones": opciones,
                "resumen": {
                    "total_plazas": estadisticas["total_plazas"],
                    "total_registros": estadisticas["total_registros"],
                    "total_provincias": estadisticas["total_provincias"],
                    "total_administraciones": estadisticas[
                        "total_administraciones"
                    ],
                },
                "top_administraciones": estadisticas["top_administraciones"],
                "top_puestos": estadisticas["top_puestos"],
                "plazas_por_comunidad": estadisticas["plazas_por_comunidad"],
                "plazas_por_provincia": estadisticas["plazas_por_provincia"],
                "evolucion_anual": estadisticas["evolucion_anual"],
                "plazas_por_mes": estadisticas["plazas_por_mes"],
                "evolucion_anual_puestos": evolucion_comparada,
                "calidad_datos": estadisticas["calidad_datos"],
                "archivo": {
                    "nombre": ruta.name,
                    "ultima_modificacion": datos_metadata.get("updated_at"),
                },
            }
        if "distribucion_tipo_personal" in estadisticas:
            respuesta["distribucion_tipo_personal"] = estadisticas["distribucion_tipo_personal"]
        salida = jsonify(respuesta)
        cache.guardar(clave, salida.get_data(), tipo_personal)
        return salida

    @app.errorhandler(404)
    def pagina_no_encontrada(error):
        return render_template("error.html", seccion_activa=None, codigo=404, mensaje="La página solicitada no existe."), 404

    return app


def _validar_fecha(valor, nombre):
    if valor is None:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor):
        raise ValueError(f"{nombre} debe tener formato YYYY-MM-DD.")
    try:
        return datetime.strptime(valor, "%Y-%m-%d")
    except ValueError as error:
        raise ValueError(f"{nombre} no es una fecha válida.") from error


def _analizar_argumentos(argv=None):
    parser = argparse.ArgumentParser(description="Dashboard estadístico del BOE")
    parser.add_argument(
        "--bd",
        default=Path.cwd() / "datos/boe.db",
        help="Ruta a datos/boe.db",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    return parser.parse_args(argv)


app = crear_app()


if __name__ == "__main__":
    argumentos = _analizar_argumentos()
    import gestion_base
    gestion_base.asegurar_base_local(argumentos.bd)
    if argumentos.host == "0.0.0.0":
        print(f"Acceso LAN habilitado. Accede desde otro dispositivo mediante http://IP_LOCAL_DEL_SERVIDOR:{argumentos.port}")
    crear_app(argumentos.bd).run(host=argumentos.host, port=argumentos.port, debug=False)
