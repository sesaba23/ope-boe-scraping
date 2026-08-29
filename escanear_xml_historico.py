"""Escáner experimental y reanudable de expresiones estructurales en XML BOE."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

import requests

from analizar_xml_boe import analizar_xml, integridad_excel
from boe_api import extraer_publicaciones_2b_api, obtener_sumario_api
from extractor_historico_boe import detectar_cantidades


VERSION_FORMATO = 1
VERSION_REGLA_DESCUBRIMIENTO = "2"
DIRECTORIO_DEFECTO = Path("informes/escaneo_xml_2004")
PATRONES_ESTRUCTURALES = {
    "distribucion": r"\b(?:con la siguiente distribuci[oó]n|distribuidas? de la siguiente forma|distribuidas? del siguiente modo|las \d+ plazas se distribuyen)\b",
    "inclusion": r"\b(?:de las cuales|de ellas|de las que|se reservan \d+ plazas|incluidas? \d+ plazas|del total de \d+ plazas)\b",
    "turnos": r"\b(?:\d+ plazas? (?:de |por )?(?:turno libre|acceso libre).{0,100}\d+ plazas? (?:de |por )?(?:promoci[oó]n interna|movilidad)|correspondiendo \d+ a)\b",
}
PATRON_DEBIL = re.compile(r"\b(?:plazas?|vacantes?|reserva|promoci[oó]n interna|movilidad|distribuci[oó]n)\b", re.I)
PATRON_CANDIDATA = re.compile(r"\b(?:plaza\w*|vacante\w*|convoc\w*|provisi\w*)\b", re.I)


def _ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ruta_estado(directorio=DIRECTORIO_DEFECTO):
    return Path(directorio) / "estado_escaneo_2004.json"


def escribir_json_atomico(ruta, datos):
    ruta = Path(ruta); ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporal = tempfile.mkstemp(prefix=f".{ruta.name}.", suffix=".tmp", dir=ruta.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
            json.dump(datos, archivo, ensure_ascii=False, indent=2)
            archivo.flush(); os.fsync(archivo.fileno())
        with open(temporal, encoding="utf-8") as archivo:
            json.load(archivo)
        os.replace(temporal, ruta)
    except BaseException:
        try: os.unlink(temporal)
        except FileNotFoundError: pass
        raise


def crear_estado(anio, publicaciones):
    unicas = {}
    for publicacion in publicaciones:
        identificador = publicacion.get("Publicacion_ID")
        if identificador:
            unicas.setdefault(identificador, publicacion)
    return {"version_formato": VERSION_FORMATO, "anio": anio, "fecha_inicio": _ahora(),
            "version_regla_descubrimiento": VERSION_REGLA_DESCUBRIMIENTO,
            "fecha_descubrimiento": _ahora(),
            "ultima_actualizacion": _ahora(), "publicaciones_totales": len(unicas),
            "publicaciones_procesadas": 0, "publicaciones_pendientes": len(unicas),
            "publicaciones_error": 0, "candidatas": list(unicas.values()), "resultados": {}}


def actualizar_contadores(estado):
    resultados = estado["resultados"].values()
    estado["publicaciones_procesadas"] = sum(r["clasificacion"] != "ERROR" for r in resultados)
    estado["publicaciones_error"] = sum(r["clasificacion"] == "ERROR" for r in resultados)
    estado["publicaciones_pendientes"] = estado["publicaciones_totales"] - len(estado["resultados"])
    estado["ultima_actualizacion"] = _ahora()


def descubrir_publicaciones(anio, consultar_api=obtener_sumario_api):
    """Descubre II.B por API oficial; filtra solo candidatas textuales amplias."""
    actual, fin = date(anio, 1, 1), date(anio, 12, 31)
    fechas = []
    while actual <= fin:
        fechas.append(actual)
        actual += timedelta(days=1)

    def consultar(fecha):
        try:
            publicaciones = extraer_publicaciones_2b_api(consultar_api(fecha))["publicaciones"]
            return [{**publicacion, "Fecha_BOE": fecha.isoformat()} for publicacion in publicaciones
                    if PATRON_CANDIDATA.search(str(publicacion.get("titulo", "")))]
        except Exception:
            return []
    with ThreadPoolExecutor(max_workers=16) as executor:
        resultado = {}
        for lote in executor.map(consultar, fechas):
            for publicacion in lote:
                resultado.setdefault(publicacion["Publicacion_ID"], publicacion)
        return list(resultado.values())


def analizar_publicacion(publicacion, obtener=requests.get):
    base = {k: publicacion.get(k) for k in ("Publicacion_ID", "Fecha_BOE", "titulo", "departamento", "url_xml")}
    try:
        respuesta = obtener(publicacion["url_xml"], timeout=10); respuesta.raise_for_status()
        estructura = analizar_xml(respuesta.content); texto = estructura["texto_relevante"]
        expresiones, fragmentos = [], []
        for nombre, patron in PATRONES_ESTRUCTURALES.items():
            for coincidencia in re.finditer(patron, texto, re.I):
                expresiones.append(nombre)
                fragmentos.append(" ".join(texto[max(0, coincidencia.start()-120):coincidencia.end()+180].split()))
        expresiones = list(dict.fromkeys(expresiones)); fragmentos = list(dict.fromkeys(fragmentos))
        clasificacion = "EVIDENCIA_ESTRUCTURAL" if expresiones else "SENALES_DEBILES" if PATRON_DEBIL.search(texto) else "SIN_SENALES"
        cantidades = detectar_cantidades(texto)
        return {**base, "clasificacion": clasificacion, "expresiones_encontradas": expresiones,
                "fragmentos": fragmentos, "cantidades_detectadas": cantidades,
                "posible_total": [c for c in cantidades if c["tipo_inicial"] == "TOTAL"],
                "posibles_componentes": [c for c in cantidades if c["tipo_inicial"] == "COMPONENTE"],
                "posibles_subcupos": [c for c in cantidades if c["tipo_inicial"] == "SUBCUPO"],
                "error": None, "fecha_analisis": _ahora()}
    except Exception as error:
        return {**base, "clasificacion": "ERROR", "expresiones_encontradas": [], "fragmentos": [],
                "cantidades_detectadas": [], "posible_total": [], "posibles_componentes": [],
                "posibles_subcupos": [], "error": {"tipo": type(error).__name__, "mensaje": str(error)},
                "fecha_analisis": _ahora()}


def pendientes(estado, reintentar_errores=False):
    hechos = estado["resultados"]
    if reintentar_errores:
        return [p for p in estado["candidatas"] if hechos.get(p["Publicacion_ID"], {}).get("clasificacion") == "ERROR"]
    return [p for p in estado["candidatas"] if p["Publicacion_ID"] not in hechos]


def ejecutar_escaneo(estado, limite=None, obtener=requests.get, ruta=None, reintentar_errores=False):
    seleccion = pendientes(estado, reintentar_errores)
    if limite is not None: seleccion = seleccion[:limite]
    procesadas = 0
    try:
        for publicacion in seleccion:
            resultado = analizar_publicacion(publicacion, obtener)
            estado["resultados"][publicacion["Publicacion_ID"]] = resultado
            procesadas += 1; actualizar_contadores(estado)
            if ruta: escribir_json_atomico(ruta, estado)
    except KeyboardInterrupt:
        actualizar_contadores(estado)
        if ruta: escribir_json_atomico(ruta, estado)
        raise
    actualizar_contadores(estado)
    if ruta: escribir_json_atomico(ruta, estado)
    return procesadas


def resumen_estado(estado):
    conteo = Counter(r["clasificacion"] for r in estado["resultados"].values())
    return {**{k: conteo[k] for k in ("EVIDENCIA_ESTRUCTURAL", "SENALES_DEBILES", "SIN_SENALES", "ERROR")},
            "procesadas": len(estado["resultados"]), "pendientes": estado["publicaciones_pendientes"]}


def seleccionar_prioritarias(estado, limite=30):
    def puntuacion(resultado):
        return (10 * len(resultado["expresiones_encontradas"]) + 4 * len(resultado["posible_total"])
                + 3 * len(resultado["posibles_componentes"]) + 2 * len(resultado["posibles_subcupos"]))
    candidatas = [r for r in estado["resultados"].values() if r["clasificacion"] == "EVIDENCIA_ESTRUCTURAL"]
    return sorted(candidatas, key=lambda r: (-puntuacion(r), r["Publicacion_ID"]))[:limite]


def guardar_informe_final(estado, directorio=DIRECTORIO_DEFECTO):
    directorio = Path(directorio); resumen = resumen_estado(estado); top = seleccionar_prioritarias(estado)
    datos = {"resumen": resumen, "cobertura": {k: estado[k] for k in ("publicaciones_totales", "publicaciones_procesadas", "publicaciones_pendientes", "publicaciones_error")},
             "resultados": list(estado["resultados"].values()), "candidatos_prioritarios": top}
    ruta_json = directorio / "informe_escaneo_xml_2004.json"; ruta_md = directorio / "informe_escaneo_xml_2004.md"
    escribir_json_atomico(ruta_json, datos)
    lineas = ["# Escaneo XML BOE 2004", "", "## Resumen", "", *[f"- {k}: {v}" for k, v in resumen.items()], "", "## Candidatos prioritarios", ""]
    lineas += [f"- {r['Publicacion_ID']}: {', '.join(r['expresiones_encontradas'])}" for r in top]
    ruta_md.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return ruta_json, ruta_md


def cargar_o_crear(anio, directorio, reiniciar=False, confirmar=False, descubrir=descubrir_publicaciones):
    ruta = ruta_estado(directorio)
    if reiniciar and not confirmar: raise ValueError("--reiniciar requiere --confirmar")
    if ruta.exists() and not reiniciar:
        estado = json.loads(ruta.read_text(encoding="utf-8"))
        if estado.get("version_regla_descubrimiento") != VERSION_REGLA_DESCUBRIMIENTO:
            raise RuntimeError("El estado fue creado con una regla de descubrimiento anterior. Debe migrarse antes de continuar.")
        return estado, ruta
    estado = crear_estado(anio, descubrir(anio)); escribir_json_atomico(ruta, estado)
    return estado, ruta


def migrar_estado(anio, directorio=DIRECTORIO_DEFECTO, descubrir=descubrir_publicaciones):
    """Reconstruye candidatas con la regla actual y reutiliza resultados compatibles."""
    ruta = ruta_estado(directorio)
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el estado a migrar: {ruta}")
    antiguo = json.loads(ruta.read_text(encoding="utf-8"))
    if antiguo.get("anio") != anio:
        raise ValueError("El año del estado no coincide con --anio")
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = ruta.with_name(f"estado_escaneo_{anio}_pre_migracion_{sello}.json")
    shutil.copy2(ruta, backup)
    candidatas = descubrir(anio)
    nuevo = crear_estado(anio, candidatas)
    ids_actuales = {p["Publicacion_ID"] for p in nuevo["candidatas"]}
    fuera = {}
    for identificador, resultado in antiguo.get("resultados", {}).items():
        if identificador in ids_actuales:
            nuevo["resultados"][identificador] = resultado
        else:
            fuera[identificador] = resultado
    nuevo["resultados_fuera_catalogo_actual"] = fuera
    nuevo["migracion"] = {
        "fecha": _ahora(), "candidatas_regla_anterior": antiguo.get("publicaciones_totales", len(antiguo.get("candidatas", []))),
        "candidatas_regla_actual": len(nuevo["candidatas"]), "procesadas_reutilizadas": len(nuevo["resultados"]),
        "procesadas_fuera_catalogo": len(fuera), "errores_conservados": sum(r.get("clasificacion") == "ERROR" for r in nuevo["resultados"].values()),
        "backup": str(backup),
    }
    actualizar_contadores(nuevo)
    escribir_json_atomico(ruta, nuevo)
    return nuevo, backup


def main(argumentos=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anio", type=int, default=2004); parser.add_argument("--limite", type=int)
    parser.add_argument("--reanudar", action="store_true"); parser.add_argument("--reintentar-errores", action="store_true")
    parser.add_argument("--reiniciar", action="store_true"); parser.add_argument("--confirmar", action="store_true")
    parser.add_argument("--migrar-estado", action="store_true")
    args = parser.parse_args(argumentos)
    if args.migrar_estado:
        estado, backup = migrar_estado(args.anio, DIRECTORIO_DEFECTO)
        datos = estado["migracion"]
        print(f"Backup creado: {backup}")
        for clave in ("candidatas_regla_anterior", "candidatas_regla_actual", "procesadas_reutilizadas", "procesadas_fuera_catalogo", "errores_conservados"):
            print(f"{clave}: {datos[clave]}")
        print(f"Pendientes nuevas: {estado['publicaciones_pendientes']}")
        return
    estado, ruta = cargar_o_crear(args.anio, DIRECTORIO_DEFECTO, args.reiniciar, args.confirmar)
    try: hechas = ejecutar_escaneo(estado, args.limite, ruta=ruta, reintentar_errores=args.reintentar_errores)
    except KeyboardInterrupt:
        print(f"Interrumpido. Pendientes: {estado['publicaciones_pendientes']}"); return
    resumen = resumen_estado(estado)
    print(f"Procesadas esta ejecución: {hechas}")
    print(f"Procesadas acumuladas: {resumen['procesadas']} / {estado['publicaciones_totales']}")
    for clave in ("EVIDENCIA_ESTRUCTURAL", "SENALES_DEBILES", "SIN_SENALES", "ERROR", "pendientes"): print(f"{clave}: {resumen[clave]}")
    if estado["publicaciones_pendientes"] == 0: print(f"Informes: {guardar_informe_final(estado, DIRECTORIO_DEFECTO)}")


if __name__ == "__main__":
    main()
