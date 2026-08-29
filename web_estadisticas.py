import argparse
from datetime import datetime
from pathlib import Path
import re

from flask import Flask, jsonify, render_template, request

from consultas_boe import ErrorConsultaSQLite, metadata, opciones_filtros
from estadisticas import calcular_estadisticas_sqlite


def crear_app(ruta_bd=None):
    app = Flask(__name__)
    ruta_fijada = Path(ruta_bd or Path.cwd() / "datos/boe.db").expanduser()
    app.config["RUTA_BD"] = ruta_fijada.resolve()

    @app.get("/")
    def pagina_estadisticas():
        return render_template("estadisticas.html")

    @app.get("/api/estadisticas")
    def api_estadisticas():
        fecha_inicio = request.args.get("fecha_inicio") or None
        fecha_final = request.args.get("fecha_final") or None
        puesto = request.args.get("puesto") or None
        provincia = request.args.get("provincia") or None
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
                provincia=provincia, sistema=sistema, turno=turno)
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


def _analizar_argumentos():
    parser = argparse.ArgumentParser(description="Dashboard estadístico del BOE")
    parser.add_argument(
        "--bd",
        default=Path.cwd() / "datos/boe.db",
        help="Ruta a datos/boe.db",
    )
    return parser.parse_args()


app = crear_app()


if __name__ == "__main__":
    argumentos = _analizar_argumentos()
    crear_app(argumentos.bd).run(host="127.0.0.1", port=5000, debug=False)
