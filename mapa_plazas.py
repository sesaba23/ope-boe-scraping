from consultas_boe import COLUMNAS_MAPA, oposiciones

import pandas as pd
import re
import folium
from folium.plugins import MarkerCluster

import webbrowser
import os
import unicodedata
from pathlib import Path
from functools import lru_cache
from html import escape
from urllib.parse import urlparse

from alias_municipios import ALIAS_MUNICIPIOS


@lru_cache(maxsize=1)
def _cargar_catalogo_municipios():
    # Ruta al archivo (ajusta si está en otra carpeta)
    ruta = Path(__file__).resolve().parent / "assets" / "resources" / "municipios.csv"

    # Leer el archivo CSV en un DataFrame separado por ';'
    df = pd.read_csv(ruta, sep=";")
    df.columns = df.columns.str.strip()

    municipios = []
    for municipio in df["Población"]:
        municipio = municipio.strip()
        municipios.append(municipio)
        # Variante invertida si contiene "/"
        if "/" in municipio:
            izq, der = municipio.split("/", 1)
            invertido = f"{der.strip()}/{izq.strip()}"
            municipios.append(invertido)
            # Añadir también cada parte individual como variante
            municipios.append(izq.strip())
            municipios.append(der.strip())
        # Variante con preposición delante si contiene paréntesis
        if "(" in municipio and ")" in municipio:
            base = municipio[: municipio.index("(")].strip()
            prep = municipio[municipio.index("(") + 1 : municipio.index(")")].strip()
            variante = f"{prep} {base}"
            municipios.append(variante)

    return df, municipios


def buscar_municipio(administracion):
    """Compatibilidad del mapa: sólo delega en el resolutor exacto v4.

    La implementación histórica de subcadenas queda intencionadamente
    inaccesible: nunca debe convertir una coincidencia parcial en ubicación.
    """
    from resolucion_geografica import resolver_administracion_geografia
    resolucion = resolver_administracion_geografia(administracion)
    if resolucion.confianza == "ALTA" and resolucion.municipio and resolucion.provincia:
        # Sólo adaptación de formato: el municipio ya fue decidido por el
        # resolutor. Las variantes del CSV antiguo no participan en decidirlo.
        df, _ = _cargar_catalogo_municipios()
        candidatas = df[df["Provincia"].map(normaliza) == normaliza(resolucion.provincia)]
        for _, antigua in candidatas.iterrows():
            if normaliza(resolucion.municipio) in {normaliza(x) for x in _variantes_nombre_catalogo(antigua["Población"])}:
                return _datos_municipio(antigua)
        from resolucion_geografica import catalogo
        fila = next((x for x in catalogo().municipios if x["Codigo_INE"] == resolucion.codigo_ine), None)
        if fila is None:
            return {"Municipio": resolucion.municipio, "Provincia": resolucion.provincia}
        return {"Municipio": fila["Municipio"], "Provincia": fila["Provincia"],
                "Latitud": float(fila["Latitud"]), "Longitud": float(fila["Longitud"]),
                "Habitantes": int(float(fila["Habitantes"]))}
    return None

def _buscar_municipio_historico_no_usar(administracion):
    df, municipios = _cargar_catalogo_municipios()

    # Priorizar los contenidos entre paréntesis que coincidan con el catálogo
    candidatos_parentesis = re.findall(r"\(([^()]*)\)", administracion)
    provincias = {normaliza(provincia) for provincia in df["Provincia"].dropna()}
    administracion_sin_parentesis = administracion
    municipios_encontrados = [
        municipio
        for candidato in candidatos_parentesis
        for municipio in municipios
        if normaliza(municipio) == normaliza(candidato)
        and (
            normaliza(candidato) not in provincias
            or set(re.findall(r"\w{3,}", normaliza(candidato)))
            & set(
                re.findall(
                    r"\w{3,}", normaliza(administracion.split("(", 1)[0])
                )
            )
        )
    ]
    for candidato in candidatos_parentesis:
        if normaliza(candidato) in provincias and not any(
            normaliza(municipio) == normaliza(candidato)
            for municipio in municipios_encontrados
        ):
            administracion_sin_parentesis = administracion_sin_parentesis.replace(
                f"({candidato})", ""
            )

    if not municipios_encontrados:
        nombre_ayuntamiento = extraer_nombre_municipal(
            administracion_sin_parentesis
        )
        if nombre_ayuntamiento:
            provincia_parentetica = next(
                (
                    candidato
                    for candidato in candidatos_parentesis
                    if normaliza(candidato) in provincias
                ),
                None,
            )
            fila_ayuntamiento = _buscar_fila_municipal_exacta(
                df, nombre_ayuntamiento, provincia_parentetica
            )
            if fila_ayuntamiento is not None:
                return _datos_municipio(fila_ayuntamiento)
            if (
                provincia_parentetica is not None
                and _buscar_fila_municipal_exacta(df, nombre_ayuntamiento)
                is not None
            ):
                return None

    # Buscar coincidencias exactas (case-insensitive) en el texto de administración
    if not municipios_encontrados:
        municipios_encontrados = [
            municipio
            for municipio in municipios
            if municipio.lower() == administracion_sin_parentesis.strip().lower()
        ]
    if not municipios_encontrados:
        # Si no hay coincidencia exacta, buscar si alguna variante está contenida como palabra completa
        municipios_encontrados = [
            municipio
            for municipio in municipios
            if re.search(
                rf"(?<!\w){re.escape(municipio)}(?!\w)",
                administracion_sin_parentesis,
                flags=re.IGNORECASE,
            )
        ]
    if not municipios_encontrados:
        municipios_encontrados = [
            municipio
            for municipio in municipios
            if normaliza(municipio) in normaliza(administracion_sin_parentesis)
        ]

    if municipios_encontrados:
        municipio_final = max(municipios_encontrados, key=len)
        # Buscar la fila original (sin invertir) que coincide
        fila = df[df["Población"].str.strip().str.lower() == municipio_final.lower()]
        if fila.empty and "/" in municipio_final:
            # Si es una variante invertida, buscar la original
            izq, der = municipio_final.split("/", 1)
            original = f"{der.strip()}/{izq.strip()}"
            fila = df[df["Población"].str.strip().str.lower() == original.lower()]
        # Si es una variante con preposición delante, buscar la original con paréntesis
        if (
            fila.empty
            and "(" not in municipio_final
            and ")" not in municipio_final
            and " " in municipio_final
        ):
            # Ejemplo: municipio_final = "A Coruña" y en el CSV está "Coruña (A)"
            partes = municipio_final.split(" ", 1)
            if len(partes) == 2:
                prep, base = partes
                original = f"{base} ({prep})"
                fila = df[df["Población"].str.strip().str.lower() == original.lower()]
        if fila.empty:
            # Buscar si municipio_final es una de las partes separadas por "/"
            mask = (
                df["Población"]
                .str.split("/")
                .apply(
                    lambda partes: any(
                        p.strip().lower() == municipio_final.lower() for p in partes
                    )
                )
            )
            fila = df[mask]
        if not fila.empty:
            return _datos_municipio(fila.iloc[0])
        else:
            return None


def extraer_nombre_municipal(administracion):
    """Extrae de forma controlada el nombre tras un prefijo municipal conocido."""
    texto = re.sub(r"\s*\([^()]*\)\s*$", "", str(administracion)).strip()
    patrones = [
        (r"^ayuntamiento\s+de\s+la\s+", "La "),
        (r"^ayuntamiento\s+del\s+", "El "),
        (r"^ayuntamiento\s+de\s+", ""),
        (r"^ajuntament\s+de\s+la\s+", "La "),
        (r"^ajuntament\s+del\s+", "El "),
        (r"^ajuntament\s+de\s+", ""),
        (r"^ajuntament\s+d\s*['’‘`´]\s*", ""),
    ]
    for patron, articulo in patrones:
        if re.search(patron, texto, flags=re.IGNORECASE):
            nombre = re.sub(
                patron, "", texto, count=1, flags=re.IGNORECASE
            ).strip()
            return f"{articulo}{nombre}"
    return None


def normalizar_nombre_municipal(texto):
    """Genera una clave ortográfica exacta sin alterar el nombre almacenado."""
    # Sustituir antes de NFKC: el acento agudo espaciado (´) puede convertirse
    # en espacio durante la normalización Unicode y romper un apóstrofo real.
    texto = re.sub(r"[’‘`´]", "'", str(texto))
    texto = unicodedata.normalize("NFKC", texto)
    texto = "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caracter) != "Mn"
    ).casefold()
    texto = re.sub(r"\s*'\s*", "'", texto)
    texto = re.sub(r"[-‐‑‒–—]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _variantes_nombre_catalogo(nombre):
    nombre = str(nombre).strip()
    variantes = [nombre]
    if "/" in nombre:
        izquierda, derecha = nombre.split("/", 1)
        variantes.extend(
            [
                f"{derecha.strip()}/{izquierda.strip()}",
                izquierda.strip(),
                derecha.strip(),
            ]
        )
    if "(" in nombre and ")" in nombre:
        base = nombre[: nombre.index("(")].strip()
        articulo = nombre[nombre.index("(") + 1 : nombre.index(")")].strip()
        separador = "" if articulo.endswith(("'", "’")) else " "
        variantes.append(f"{articulo}{separador}{base}")
    # Denominación oficial con artículo pospuesto: «Puig de Santa Maria, el».
    # Se conserva la grafía del catálogo y se expone exclusivamente la variante
    # equivalente con el artículo antepuesto, sin aproximaciones léxicas.
    variantes.extend(_variantes_articulo_pospuesto(nombre))
    return variantes


def _variantes_articulo_pospuesto(nombre):
    partes = [x.strip() for x in str(nombre).split("/")]
    alternativas = []
    for indice, parte in enumerate(partes):
        coincidencia = re.fullmatch(r"(.+?),\s*(la|el|los|las|a|o|l['’])", parte, flags=re.IGNORECASE)
        if not coincidencia:
            continue
        nuevas = partes.copy()
        articulo = coincidencia.group(2)
        separador = "" if articulo.endswith(("'", "’")) else " "
        nuevas[indice] = f"{articulo.title()}{separador}{coincidencia.group(1).strip()}"
        alternativas.append("/".join(nuevas))
        # En una denominación bilingüe con '/', la otra grafía puede omitir
        # el artículo; exponerla es seguro. En una denominación única no se
        # elimina el artículo, para no confundir «Granada» y «La Granada».
        if len(partes) > 1:
            nuevas_sin_articulo = partes.copy()
            nuevas_sin_articulo[indice] = coincidencia.group(1).strip()
            alternativas.append("/".join(nuevas_sin_articulo))
    return alternativas


def _buscar_fila_municipal_exacta(df, nombre, provincia=None):
    clave = normalizar_nombre_municipal(nombre)
    alias_normalizados = {
        normalizar_nombre_municipal(origen): destino
        for origen, destino in ALIAS_MUNICIPIOS.items()
    }
    destino_alias = alias_normalizados.get(clave)
    clave_buscada = normalizar_nombre_municipal(destino_alias or nombre)
    coincidencias = df[
        df["Población"].map(
            lambda poblacion: clave_buscada
            in {
                normalizar_nombre_municipal(variante)
                for variante in _variantes_nombre_catalogo(poblacion)
            }
        )
    ]
    if provincia is not None:
        clave_provincia = normalizar_nombre_municipal(provincia)
        coincidencias = coincidencias[
            coincidencias["Provincia"].map(normalizar_nombre_municipal)
            == clave_provincia
        ]
    return coincidencias.iloc[0] if not coincidencias.empty else None


def _datos_municipio(fila):
    return {
        "Municipio": fila["Población"],
        "Provincia": fila["Provincia"],
        "Latitud": float(str(fila["Latitud"]).replace(",", ".")),
        "Longitud": float(str(fila["Longitud"]).replace(",", ".")),
        "Habitantes": int(fila["Habitantes"]),
    }


def enriquecer_filas_sin_coordenadas(df):
    if df.empty or "Administración" not in df.columns:
        return df

    df_enriquecido = df.copy()
    columnas_geograficas = [
        "Municipio",
        "Provincia",
        "Latitud",
        "Longitud",
        "Habitantes",
    ]
    for columna in columnas_geograficas:
        if columna not in df_enriquecido.columns:
            df_enriquecido[columna] = pd.NA

    administraciones = df_enriquecido["Administración"].astype(str).str.strip()
    filas_sin_coordenadas = df_enriquecido[
        df_enriquecido["Administración"].notna()
        & ~administraciones.str.lower().isin(["", "--", "no disponible", "none", "nan"])
        & (
            df_enriquecido["Latitud"].isna()
            | df_enriquecido["Longitud"].isna()
        )
    ]

    for indice, fila in filas_sin_coordenadas.iterrows():
        datos_municipio = buscar_municipio(str(fila["Administración"]).strip())
        if datos_municipio:
            for columna in columnas_geograficas:
                valor_actual = df_enriquecido.at[indice, columna]
                if pd.isna(valor_actual) or str(valor_actual).strip() == "":
                    df_enriquecido.at[indice, columna] = datos_municipio[columna]

    return df_enriquecido


def generar_mapa_municipios(df=None, ruta_bd="datos/boe.db", **filtros):

    # Si no pasa un DataFrame, consulta SQLite en modo explícitamente read-only.
    if df is None:
        df = oposiciones(ruta_bd, columnas=COLUMNAS_MAPA, **filtros)

    columnas_faltantes = [
        columna
        for columna in ["Latitud", "Longitud", "Habitantes"]
        if columna not in df.columns
    ]
    if columnas_faltantes:
        df = df.copy()
        for columna in columnas_faltantes:
            df[columna] = pd.NA

    # Crear el mapa centrado en España
    mapa = folium.Map(location=[40.0, -3.7], zoom_start=6)

    # Crear el clúster de marcadores
    marker_cluster = MarkerCluster().add_to(mapa)

    for _, row in df.iterrows():
        lat = row["Latitud"]
        lon = row["Longitud"]
        if (
            pd.notnull(lat)
            and pd.notnull(lon)
            and str(lat).strip() != ""
            and str(lon).strip() != ""
        ):
            enlace_html = crear_enlace_html(row["Enlace"])
            popup_html = f"""
            <b>Puesto:</b> {escape(str(row['Puesto']), quote=True)}<br>
            <b>Nº Plazas:</b> {escape(str(row['Num_plazas']), quote=True)}</br>
            <b>Administración:</b> {escape(str(row['Administración']), quote=True)}<br>
            <b>Sistema:</b> {escape(str(row['Sistema']), quote=True)}<br>
            <b>Fecha:</b> {escape(str(row.get('Fecha_boe_original', row.get('Fecha_boe'))), quote=True)}, {enlace_html}<br>
            {f"{int(row['Habitantes']):,}".replace(",", ".")} habitantes<br>
            """
            folium.Marker(
                location=[lat, lon], popup=folium.Popup(popup_html, max_width=350)
            ).add_to(marker_cluster)

    mostrar_puestos_sin_coordenadas(df)
    # Guardar el mapa
    archivo_mapa = "mapa_municipios.html"
    mapa.save(archivo_mapa)

    if not df.empty:
        # Abrir el mapa en el navegador por defecto
        webbrowser.open("file://" + os.path.realpath(archivo_mapa))

        print("✅ Mapa generado y abierto en el navegador.")


def mostrar_puestos_sin_coordenadas(df):
    # Filtrar los puestos sin latitud o longitud
    sin_coordenadas = df[
        df["Latitud"].isnull()
        | df["Longitud"].isnull()
        | (df["Latitud"].astype(str).str.strip() == "")
        | (df["Longitud"].astype(str).str.strip() == "")
    ]

    if sin_coordenadas.empty:
        return

    # Generar HTML
    html = """
    <html>
    <head>
        <title>Convocatorias sin coordenadas</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .puesto { margin-bottom: 20px; border-bottom: 1px solid #ccc; padding-bottom: 10px; }
        </style>
    </head>
    <body>
        <h3>Convocatorias publicadas que no se han podido representar geográficamente</h3>
    """

    for _, row in sin_coordenadas.iterrows():
        enlace_html = crear_enlace_html(row.get("Enlace", ""))
        html += f"""
        <div class="puesto">
            <b>Puesto:</b> {escape(str(row.get('Puesto', '')), quote=True)}<br>
            <b>Nº Plazas:</b> {escape(str(row.get('Num_plazas', '')), quote=True)}<br>
            <b>Administración:</b> {escape(str(row.get('Administración', '')), quote=True)}<br>
            <b>Fecha:</b> {escape(str(row.get('Fecha_boe_original', row.get('Fecha_boe'))), quote=True)}, {enlace_html}<br>
        </div>
        """

    html += """
    </body>
    </html>
    """

    # Guardar y abrir el HTML
    archivo = "puestos_sin_coordenadas.html"
    with open(archivo, "w", encoding="utf-8") as f:
        f.write(html)

    webbrowser.open("file://" + os.path.realpath(archivo))


def crear_enlace_html(enlace):
    enlace = str(enlace).strip()
    try:
        componentes = urlparse(enlace)
    except ValueError:
        return ""
    if componentes.scheme not in ["http", "https"] or not componentes.netloc:
        return ""
    return f'<a href="{escape(enlace, quote=True)}" target="_blank">Enlace al B.O.E.</a>'


# Quita tildes y compara en minúsculas
def normaliza(texto):
    return (
        "".join(
            c
            for c in unicodedata.normalize("NFD", texto)
            if unicodedata.category(c) != "Mn"
        )
        .lower()
        .strip()
    )


if __name__ == "__main__":
    coincidencia = buscar_municipio("A Coruña")
    print(coincidencia)

    generar_mapa_municipios()
