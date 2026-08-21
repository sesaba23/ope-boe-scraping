from preparar_archivo_datos import preparar_excel_y_dataframes

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
            fila = fila.iloc[0]
            return {
                "Municipio": fila["Población"],
                "Provincia": fila["Provincia"],
                "Latitud": float(fila["Latitud"].replace(",", ".")),
                "Longitud": float(fila["Longitud"].replace(",", ".")),
                "Habitantes": int(fila["Habitantes"]),
            }
        else:
            return None


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


def generar_mapa_municipios(df=None):

    # Si no pasa un Dataframe, por defecto carga el histórico de plazas guardadas
    # en el archivo Excel
    if df is None:
        dataframes_dict = preparar_excel_y_dataframes()
        df = dataframes_dict["Oposiciones"]

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
            <b>Fecha:</b> {escape(str(row['Fecha_boe']), quote=True)}, {enlace_html}<br>
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
            <b>Fecha:</b> {escape(str(row['Fecha_boe']), quote=True)}, {enlace_html}<br>
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
