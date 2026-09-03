import argparse
from datetime import datetime, timedelta
from pathlib import Path
import re

from flask import Flask, abort, jsonify, render_template, request

from actualizacion_boe import GestorActualizaciones, determinar_actualizacion_intervalo

from consultas_boe import (
    ErrorConsultaSQLite, buscar_municipios, buscar_oposiciones,
    buscar_sugerencias_puesto, metadata, obtener_oposicion,
    opciones_busqueda, opciones_filtros, cobertura_mes, detalle_cobertura_dia,
    resumen_cobertura,
)
from estadisticas import calcular_estadisticas_sqlite


def crear_app(ruta_bd=None, gestor_actualizaciones=None):
    app = Flask(__name__)
    ruta_fijada = Path(ruta_bd or Path.cwd() / "datos/boe.db").expanduser()
    app.config["RUTA_BD"] = ruta_fijada.resolve()
    app.config["GESTOR_ACTUALIZACIONES"] = gestor_actualizaciones or GestorActualizaciones(app.config["RUTA_BD"])

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

    @app.get("/oposiciones")
    def oposiciones():
        nombres = (
            "texto", "fecha_desde", "fecha_hasta", "administracion", "ambito",
            "comunidad_autonoma", "provincia", "municipio", "tipo_entidad",
            "sistema", "turno", "escala", "subescala", "clase",
        )
        filtros = {nombre: (request.args.get(nombre) or "").strip() for nombre in nombres}
        municipio_exacto = (request.args.get("municipio_exacto") or "").strip()
        municipio_provincia_exacto = (request.args.get("municipio_provincia_exacto") or "").strip()
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
            hay_criterio = request.args.get("ver_todas") == "1" or any(filtros.values())
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
        avanzados = ("tipo_entidad", "municipio", "sistema", "turno", "escala", "subescala", "clase")
        return render_template(
            "oposiciones.html", seccion_activa="oposiciones", filtros=filtros,
            opciones=opciones, resultados=resultados, error=None, hay_criterio=hay_criterio,
            orden=orden, tamano_pagina=tamano_pagina, query_actual=query_actual,
            avanzados_activos=any(filtros[nombre] for nombre in avanzados),
            actualizacion_pendiente=pendientes_actualizacion,
            advertencia_actualizacion=request.args.get("actualizacion") == "error",
        )

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
        return render_template("detalle_oposicion.html", seccion_activa="oposiciones", oposicion=oposicion)

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
        return render_template("mapas.html", seccion_activa="mapas")

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
    if argumentos.host == "0.0.0.0":
        print(f"Acceso LAN habilitado. Accede desde otro dispositivo mediante http://IP_LOCAL_DEL_SERVIDOR:{argumentos.port}")
    crear_app(argumentos.bd).run(host=argumentos.host, port=argumentos.port, debug=False)
