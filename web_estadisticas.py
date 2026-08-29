import argparse
from datetime import datetime
from pathlib import Path
import re

from flask import Flask, jsonify, render_template, request

from estadisticas import (
    ErrorLecturaOposiciones,
    calcular_estadisticas,
    filtrar_datos,
    leer_oposiciones,
    normalizar_datos,
    obtener_opciones_filtros,
)


def crear_app(ruta_excel=None):
    app = Flask(__name__)
    ruta_fijada = Path(ruta_excel or Path.cwd() / "BOE-oposiciones.xlsx").expanduser()
    app.config["RUTA_EXCEL"] = ruta_fijada.resolve()

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

        ruta = app.config["RUTA_EXCEL"]
        try:
            datos = leer_oposiciones(ruta)
            datos = normalizar_datos(datos)
            opciones = obtener_opciones_filtros(datos)
            datos_filtrados = filtrar_datos(
                datos,
                fecha_inicio,
                fecha_final,
                puesto,
                provincia,
                sistema,
                turno,
            )
            estadisticas = calcular_estadisticas(datos_filtrados)
        except (FileNotFoundError, ErrorLecturaOposiciones, OSError, ValueError) as error:
            return jsonify({"error": f"No se pudieron cargar las estadísticas: {error}"}), 503

        ultima_modificacion = None
        try:
            ultima_modificacion = datetime.fromtimestamp(
                ruta.stat().st_mtime
            ).astimezone().isoformat(timespec="seconds")
        except OSError:
            pass

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
                    "ultima_modificacion": ultima_modificacion,
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
        "--excel",
        default=Path.cwd() / "BOE-oposiciones.xlsx",
        help="Ruta al archivo BOE-oposiciones.xlsx",
    )
    return parser.parse_args()


app = crear_app()


if __name__ == "__main__":
    argumentos = _analizar_argumentos()
    crear_app(argumentos.excel).run(host="127.0.0.1", port=5000, debug=False)
