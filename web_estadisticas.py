import argparse
from datetime import datetime, timedelta
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlsplit

from flask import Flask, abort, jsonify, redirect, render_template, request, url_for

from actualizacion_boe import GestorActualizaciones, determinar_actualizacion_intervalo

from consultas_boe import (
    ErrorConsultaSQLite, buscar_municipios, buscar_oposiciones,
    buscar_sugerencias_puesto, metadata, obtener_oposicion,
    opciones_busqueda, opciones_filtros, cobertura_mes, detalle_cobertura_dia,
    resumen_cobertura, resumen_mapa_oposiciones, buscar_oposiciones_sin_coordenadas,
)
from estadisticas import calcular_estadisticas_sqlite


_FILTROS_RETORNO_OPOSICIONES = (
    "texto", "fecha_desde", "fecha_hasta", "administracion", "ambito",
    "comunidad_autonoma", "provincia", "municipio", "municipio_exacto",
    "municipio_provincia_exacto", "tipo_entidad", "sistema", "turno",
    "escala", "subescala", "clase",
)
_ORDENES_RETORNO_OPOSICIONES = {
    "fecha_desc", "fecha_asc", "puesto_asc", "administracion_asc", "plazas_desc",
}


def _url_retorno_oposiciones(argumentos):
    """Reconstruye un destino interno con filtros y estado visual permitidos."""
    parametros = {
        nombre: valor for nombre in _FILTROS_RETORNO_OPOSICIONES
        if (valor := (argumentos.get(nombre) or "").strip())
    }
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


def crear_app(ruta_bd=None, gestor_actualizaciones=None):
    app = Flask(__name__)
    ruta_fijada = Path(ruta_bd or Path.cwd() / "datos/boe.db").expanduser()
    app.config["RUTA_BD"] = ruta_fijada.resolve()
    app.config["GESTOR_ACTUALIZACIONES"] = gestor_actualizaciones or GestorActualizaciones(app.config["RUTA_BD"])
    import gestion_base
    app.config["GESTOR_PUBLICACION"] = gestion_base.GestorPublicacion()
    app.config["GESTOR_ACTUALIZACION_BASE"] = gestion_base.GestorActualizacionBase()

    def filtros_oposiciones_desde_request():
        """Lee una sola vez los filtros lógicos compartidos por listado y mapa."""
        nombres = (
            "texto", "fecha_desde", "fecha_hasta", "administracion", "ambito",
            "comunidad_autonoma", "provincia", "municipio", "tipo_entidad",
            "sistema", "turno", "escala", "subescala", "clase",
        )
        filtros = {nombre: (request.args.get(nombre) or "").strip() for nombre in nombres}
        exactos = {
            "municipio_exacto": (request.args.get("municipio_exacto") or "").strip(),
            "municipio_provincia_exacto": (request.args.get("municipio_provincia_exacto") or "").strip(),
        }
        return filtros, exactos

    @app.get("/")
    def inicio():
        return render_template("inicio.html", seccion_activa="inicio")

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
            resumen = resumen_cobertura(app.config["RUTA_BD"])
            calendario = cobertura_mes(app.config["RUTA_BD"], anio=anio, mes=mes)
        except (ErrorConsultaSQLite, ValueError) as error:
            return render_template("error.html", seccion_activa="cobertura", codigo=400, mensaje=str(error)), 400
        return render_template("cobertura.html", seccion_activa="cobertura", resumen=resumen, calendario=calendario)

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
            hay_criterio = request.args.get("ver_todas") == "1" or any(filtros.values()) or vista_mapa
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
        avanzados = ("tipo_entidad", "municipio", "sistema", "turno", "escala", "subescala", "clase")
        return render_template(
            "oposiciones.html", seccion_activa="oposiciones", filtros=filtros,
            opciones=opciones, resultados=resultados, error=None, hay_criterio=hay_criterio,
            orden=orden, tamano_pagina=tamano_pagina, query_actual=query_actual,
            volver_detalle=_url_retorno_oposiciones(request.args),
            avanzados_activos=any(filtros[nombre] for nombre in avanzados),
            actualizacion_pendiente=pendientes_actualizacion,
            advertencia_actualizacion=request.args.get("actualizacion") == "error",
        )

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
            volver = _url_retorno_oposiciones(dict(parse_qsl(destino.query, keep_blank_values=True)))
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
            opciones = opciones_filtros(ruta)
            estadisticas = calcular_estadisticas_sqlite(
                ruta, desde=fecha_inicio, hasta=fecha_final, puesto=puesto,
                provincia=provincia, ambito=ambito, sistema=sistema, turno=turno)
            datos_metadata = metadata(ruta)
        except (ErrorConsultaSQLite, OSError, ValueError) as error:
            return jsonify({"error": f"No se pudieron cargar las estadísticas: {error}"}), 503

        return jsonify(
            {
                "filtros": {
                    "fecha_inicio": fecha_inicio,
                    "fecha_final": fecha_final,
                    "puesto": puesto,
                    "provincia": provincia,
                    "ambito": ambito,
                    "sistema": sistema,
                    "turno": turno,
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
                "plazas_por_provincia": estadisticas["plazas_por_provincia"],
                "evolucion_mensual": estadisticas["evolucion_mensual"],
                "calidad_datos": estadisticas["calidad_datos"],
                "archivo": {
                    "nombre": ruta.name,
                    "ultima_modificacion": datos_metadata.get("updated_at"),
                },
            }
        )

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
