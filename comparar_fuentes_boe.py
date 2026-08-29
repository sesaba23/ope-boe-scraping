"""Comparación experimental y no mutante entre API y sumario HTML del BOE."""

from datetime import date, datetime
import re
from statistics import mean, median
import time
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup, ParserRejectedMarkup
import requests

from boe_api import ErrorAPIBOE, extraer_publicaciones_2b_api, obtener_sumario_api


BASE = "https://www.boe.es"
PATRON_ID = re.compile(r"BOE-[A-Z]-\d{4}-\d+")


def obtener_publicaciones_html(fecha, obtener=requests.get, timeout=10):
    fecha_texto = _fecha_ruta(fecha)
    url = f"{BASE}/boe/dias/{fecha_texto}/index.php?s=2B"
    try:
        respuesta = obtener(url, timeout=timeout)
        if respuesta.status_code == 404:
            return {"estado": "SIN_EDICION", "publicaciones": []}
        if respuesta.status_code == 400:
            general = obtener(url.split("?", 1)[0], timeout=timeout)
            if general.status_code == 404:
                return {"estado": "SIN_EDICION", "publicaciones": []}
            general.raise_for_status()
            soup = BeautifulSoup(general.content, "html.parser")
            enlaces = _enlaces_2b_indice_general(soup)
            return _normalizar_enlaces_html(enlaces)
        respuesta.raise_for_status()
        soup = BeautifulSoup(respuesta.content, "html.parser")
    except (requests.exceptions.RequestException, ParserRejectedMarkup) as error:
        raise RuntimeError(f"Error HTML: {error}") from error
    return _normalizar_enlaces_html(soup.find_all("a", href=True))


def comparar_fechas(fechas):
    """Compara secuencialmente las mismas fechas en ambas fuentes."""
    return [comparar_fecha(fecha) for fecha in fechas]


def generar_informe(resultados, destino="informe_comparacion_api_html.md", integridad=None):
    """Genera un informe Markdown de la comparación ya ejecutada."""
    coincidencias = sum(r["clasificacion"] == "COINCIDEN" for r in resultados)
    errores_api = sum(bool(r["error_api"]) for r in resultados)
    errores_html = sum(bool(r["error_html"]) for r in resultados)
    lineas = [
        "# Comparación experimental API oficial BOE vs HTML",
        "", "## Resumen", "",
        f"- Fechas comparadas: {len(resultados)}",
        f"- Coincidencias exactas: {coincidencias}",
        f"- Errores API: {errores_api}",
        f"- Errores HTML: {errores_html}",
        "", "## Fechas probadas", "",
        "| Fecha | API | HTML | Resultado |",
        "|---|---:|---:|---|",
    ]
    lineas.extend(
        f"| {r['fecha']} | {r['numero_api']} | {r['numero_html']} | {r['clasificacion']} |"
        for r in resultados
    )
    lineas.extend(["", "## Coincidencias", "", f"{coincidencias} fechas coincidieron exactamente.", "", "## Diferencias", ""])
    diferencias = False
    for r in resultados:
        for origen in ("solo_api", "solo_html"):
            for p in r[origen]:
                diferencias = True
                lineas.append(
                    f"- {r['fecha']} · {origen.upper()} · {p.get('Publicacion_ID', 'sin ID')} · "
                    f"{p.get('titulo', 'sin título')} · {p.get('url_html') or p.get('url_xml') or p.get('url_pdf', 'sin URL')}"
                )
    if not diferencias:
        lineas.append("No se encontraron diferencias de identificadores.")
    lineas.extend(["", "## Errores", ""])
    errores = [r for r in resultados if r["error_api"] or r["error_html"]]
    if errores:
        for r in errores:
            lineas.append(f"- {r['fecha']}: API={r['error_api'] or 'correcta'}; HTML={r['error_html'] or 'correcto'}")
    else:
        lineas.append("No se produjeron errores.")
    lineas.extend(_seccion_tiempos("API", [r["tiempo_api"] for r in resultados]))
    lineas.extend(_seccion_tiempos("HTML", [r["tiempo_html"] for r in resultados]))
    if coincidencias == len(resultados) and not errores:
        recomendacion = (
            "La muestra respalda usar la API como fuente principal de descubrimiento: "
            "ofrece estructura e identificadores explícitos y coincidió con HTML en todas "
            "las fechas. Conviene mantener HTML como fallback independiente."
        )
    else:
        recomendacion = (
            "No conviene sustituir todavía HTML sin investigar las diferencias o errores "
            "anteriores; la API puede seguir evaluándose manteniendo HTML como contraste."
        )
    lineas.extend([
        "", "## Ventajas/inconvenientes", "",
        "La API aporta códigos estructurados de sección e identificadores documentales; el HTML conserva valor como fuente alternativa independiente.",
        "", "## Recomendación", "",
        recomendacion,
    ])
    if integridad:
        lineas.extend(["", "## Integridad del Excel", "", f"- Antes: `{integridad['antes']}`", f"- Después: `{integridad['despues']}`", f"- Sin cambios: **{integridad['antes'] == integridad['despues']}**"])
    from pathlib import Path
    ruta = Path(destino)
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return ruta


def _normalizar_enlaces_html(enlaces):
    publicaciones = []
    vistos = set()
    for enlace in enlaces:
        href = enlace["href"]
        if "txt" not in href:
            continue
        url_html = urljoin(BASE, href)
        publicacion_id = _id_desde_url(url_html)
        clave = publicacion_id or url_html
        if clave in vistos:
            continue
        vistos.add(clave)
        item = {"url_html": url_html}
        if publicacion_id:
            item["Publicacion_ID"] = publicacion_id
        titulo = enlace.get_text(" ", strip=True)
        if titulo:
            item["titulo"] = titulo
        publicaciones.append(item)
    return {
        "estado": "CON_PUBLICACIONES" if publicaciones else "SIN_SECCION_2B",
        "publicaciones": publicaciones,
    }


def _enlaces_2b_indice_general(soup):
    encabezado = next(
        (h for h in soup.find_all(["h2", "h3"])
         if "II. Autoridades y personal. - B. Oposiciones y concursos" in h.get_text(" ", strip=True)),
        None,
    )
    if encabezado is None:
        secciones = [a for a in soup.find_all("a", href=True) if "s=" in a["href"]]
        if secciones:
            return []
        raise RuntimeError("No se reconoce la estructura de secciones del índice general")
    enlaces = []
    for elemento in encabezado.find_all_next():
        if elemento.name == encabezado.name:
            break
        if elemento.name == "a" and elemento.has_attr("href") and "txt" in elemento["href"]:
            enlaces.append(elemento)
    return enlaces


def _seccion_tiempos(nombre, valores):
    titulo = f"## Rendimiento {nombre}"
    if not valores:
        return ["", titulo, "", "Sin mediciones."]
    return [
        "", titulo, "",
        f"- Total: {sum(valores):.3f} s",
        f"- Media por fecha: {mean(valores):.3f} s",
        f"- Mediana: {median(valores):.3f} s",
        f"- Máximo: {max(valores):.3f} s",
    ]


def comparar_fecha(fecha, obtener_api=obtener_sumario_api, obtener_html=obtener_publicaciones_html):
    inicio = time.perf_counter()
    try:
        api = extraer_publicaciones_2b_api(obtener_api(fecha))
        error_api = None
    except (ErrorAPIBOE, ValueError) as error:
        api = {"estado": "ERROR", "publicaciones": []}
        error_api = str(error)
    tiempo_api = time.perf_counter() - inicio

    inicio = time.perf_counter()
    try:
        html = obtener_html(fecha)
        error_html = None
    except (RuntimeError, ValueError) as error:
        html = {"estado": "ERROR", "publicaciones": []}
        error_html = str(error)
    tiempo_html = time.perf_counter() - inicio

    mapa_api = _por_id(api["publicaciones"])
    mapa_html = _por_id(html["publicaciones"])
    ids_api, ids_html = set(mapa_api), set(mapa_html)
    if error_api:
        clasificacion = "ERROR_API"
    elif error_html:
        clasificacion = "ERROR_HTML"
    elif ids_api == ids_html:
        clasificacion = "COINCIDEN"
    elif ids_api - ids_html:
        clasificacion = "SOLO_API"
    else:
        clasificacion = "SOLO_HTML"
    return {
        "fecha": _fecha_iso(fecha),
        "clasificacion": clasificacion,
        "estado_api": api["estado"],
        "estado_html": html["estado"],
        "numero_api": len(mapa_api),
        "numero_html": len(mapa_html),
        "ids_comunes": sorted(ids_api & ids_html),
        "solo_api": [mapa_api[x] for x in sorted(ids_api - ids_html)],
        "solo_html": [mapa_html[x] for x in sorted(ids_html - ids_api)],
        "error_api": error_api,
        "error_html": error_html,
        "tiempo_api": tiempo_api,
        "tiempo_html": tiempo_html,
    }


def _por_id(publicaciones):
    return {
        p["Publicacion_ID"]: p
        for p in publicaciones
        if p.get("Publicacion_ID")
    }


def _id_desde_url(url):
    valores = parse_qs(urlparse(url).query).get("id", [])
    if valores and PATRON_ID.fullmatch(valores[0]):
        return valores[0]
    encontrado = PATRON_ID.search(url)
    return encontrado.group(0) if encontrado else None


def _fecha_iso(valor):
    if isinstance(valor, datetime):
        valor = valor.date()
    if isinstance(valor, date):
        return valor.isoformat()
    texto = str(valor)
    if re.fullmatch(r"\d{8}", texto):
        return datetime.strptime(texto, "%Y%m%d").date().isoformat()
    return datetime.strptime(texto, "%Y-%m-%d").date().isoformat()


def _fecha_ruta(valor):
    return _fecha_iso(valor).replace("-", "/")
