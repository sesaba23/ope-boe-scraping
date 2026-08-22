from mapa_plazas import buscar_municipio

import re
from word2number_es import w2n


def quitar_parentesis(texto):
    return re.sub(r"\s*\(.*?\)", "", texto)


def formatear_texto(texto_contenido):
    """Hace que las palabras de cada cadena empiecen por mayúscula.
    Evita que si acaba en Técnico/a, no capitalice a Técnico/A
    """
    # Dividir el texto en palabras
    palabras = texto_contenido.split()
    palabras_formateadas = []

    for palabra in palabras:
        palabra_formateada = palabra.capitalize()
        palabras_formateadas.append(palabra_formateada)

    # Unir las palabras formateadas en una sola cadena
    return " ".join(palabras_formateadas)


def buscar_coincidencias_local(
    texto_busqueda, texto_contenido, texto_titulo="", texto_fecha_boe="", enlace=""
):
    """
    Busca las plaza publicadass en el BOE.
    Es necesario pasar el texto publicado en un día concreto.
    Está optimizado para encontrar plazas publicadas por la administración local

    Returns:

    resultados  -- lista de diccionarios con la información extraída del BOE

    Arguments:

    texto_busqueda  -- es la plaza que introduce el usuario como parámetro para búsqueda
    texto_contenido -- texto del BOE donde se publican las plazas y sus características
    texto_titulo    --  encabezado de la publicación de donde se obtiene el organismo
                        que publica las plazas
    texto_fecha_boe -- Texto de donde se extrae la fecha de publicación en el BOE
    enlace          -- Enlace a la publicación del BOE

    """

    # El texto que queremos indicar si alguna plaza no define alguna característica
    texto_no_disponible = "No disponible"
    # Tomamos las 4 primeras letras de cada palabra de la expresión
    claves = [palabra[:4].lower() for palabra in texto_busqueda.split()]

    # Patrón REGEX corregido
    patron = r"""
            (?P<num_plazas>\d+|\w+)\s+
            (?:plazas|plaza|puestos|puesto|cuerpo)\s+de\s+
            (?P<puesto>[\w/áéíóúñÁÉÍÓÚÑ\s\-]+?)\s*[,;]\s*
            (?:
                perteneciente(?:s)?\s+a\s+la\s+escala\s+de\s+
                (?P<escala>[\w\sáéíóúÁÉÍÓÚñÑ]+?)
                (?:\s*[,;]\s*subescala\s+
                    (?P<subescala>[\w\sáéíóúÁÉÍÓÚñÑ]+?)
                    (?:\s+y\s+clase\s+
                        (?P<clase>[\w\sáéíóúÁÉÍÓÚñÑ]+?))?
                )?
                \s*[,;]\s*
            )?
            (?:mediante|por)\s+el\s+sistema\s+de\s+
            (?P<sistema>[\w\s\-]+?)
            (?:\s*[,;]\s*(?:
                en\s+turno\s+(?P<turno>[\w\s]+?)
                |(?:de\s+)?(?P<acceso_libre>acceso\s+libre)
            ))?
            \s*\.
    """

    # Usamos re.finditer para obtener los resultados
    match_plazas = re.finditer(
        patron, texto_contenido, flags=re.IGNORECASE | re.VERBOSE
    )

    # Buscamos en el título en que Administración se convoca la plaza
    administracion = texto_no_disponible
    match_administracion = re.search(
        r"(, del|, de la)(.*?)(,|\.)",
        texto_titulo,
        re.IGNORECASE,
    )
    if match_administracion:
        administracion = match_administracion.group(2).strip()

    # Buscamos fecha publicación
    fecha_publicacion = texto_no_disponible
    match_num_boe = re.search(r"(?:de\s+)?(\d{1,2} de \w+ de \d{4})", texto_fecha_boe)
    if match_num_boe:
        fecha_publicacion = match_num_boe.group(1)

    # Buscamos el número de BOE. Texto entre el primer "«" y la siguiente ","
    texto_publicacion = ""
    match_publicacion = re.search(r"(«)([^,]*,[^,]*),", texto_contenido)
    if match_publicacion:
        texto_publicacion = match_publicacion.group(2)
        if texto_publicacion[:5] == "Bolet" or texto_publicacion[:5] == "Diari":
            None

    # Lista de diccionarios para almacenar los resultados
    resultados = []

    # tratamos las plazas encontradas en el texto
    for match in match_plazas:
        datos = match.groupdict()

        # En numero de plazas se convierte a numero
        if datos["num_plazas"]:
            numero = convertir_en_numero(datos["num_plazas"].lower())

        # Filtrar por coincidencia en el puesto
        puesto = datos["puesto"].strip().lower()
        if all(clave in puesto for clave in claves):
            resultado = {
                "Num_plazas": numero,
                "Puesto": datos["puesto"].strip(),
                "Administración": (
                    administracion if administracion else texto_no_disponible
                ),
                "Escala": (
                    datos["escala"].strip() if datos["escala"] else texto_no_disponible
                ),
                "Subescala": (
                    datos["subescala"].strip()
                    if datos["subescala"]
                    else texto_no_disponible
                ),
                "Clase": (
                    datos["clase"].strip() if datos["clase"] else texto_no_disponible
                ),
                "Sistema": (
                    datos["sistema"].strip().title()
                    if datos["sistema"]
                    else texto_no_disponible
                ),
                "Turno": (
                    datos["turno"].strip().title()
                    if datos["turno"]
                    else (
                        datos["acceso_libre"].strip().title()
                        if datos["acceso_libre"]
                        else texto_no_disponible
                    )
                ),
                "Fecha_boe": (
                    fecha_publicacion if fecha_publicacion else texto_no_disponible
                ),
                "Publicación": (
                    "«" + texto_publicacion
                    if texto_publicacion
                    else texto_no_disponible
                ),
                "Enlace": enlace if enlace else "Enlace " + texto_no_disponible,
            }
            # Busco el municipio al que pertenece la administración y su información
            diccionario_municipio = buscar_municipio(administracion)
            # Unir con el diccionario del municipio si existe
            if diccionario_municipio:
                resultado = {**resultado, **diccionario_municipio}
                # print(resultado)
            resultados.append(resultado)

    if len(resultados) == 0:
        return None
    else:
        # print(resultados)
        return resultados


def buscar_coincidencias_estado(
    texto_busqueda, texto_contenido, texto_titulo="", texto_fecha_boe="", enlace=""
):
    """
    Extrae información de plazas de la Administración del Estado en el BOE.
    Devuelve un diccionario con los campos principales, aunque falten algunos en el texto.
    """

    # El texto que queremos indicar si alguna plaza no define alguna característica
    texto_no_disponible = "--"
    claves = [palabra[:4].lower() for palabra in texto_busqueda.split()]
    datos = {}

    # Número de plazas
    plazas_match = re.search(
        r"convoca proceso selectivo para cubrir\s+(\d+|\w+)\s+plazas",
        texto_contenido,
        re.IGNORECASE,
    )
    # Tipo de plazas convocadas
    tipo_match = re.search(
        r",\s+en\s+(?:el|la)\s+((?:Cuerpo(?:\s+Nacional)?(?:\s+Superior)?|Escala|Subescala)\s+(?:de\s+)?[^,.\n]+)",
        texto_titulo,
        re.IGNORECASE,
    )

    # Si se encuentra un campo de los dos anteriores buscamos el resto de información
    if plazas_match and tipo_match:
        datos["Num_plazas"] = convertir_en_numero(plazas_match.group(1))
        datos["Puesto"] = tipo_match.group(1).strip()
        # Sigue buscando si el puesto encontrado coincide con la búsqueda del usuario
        puesto = datos["Puesto"].strip().lower()
        if all(clave in puesto for clave in claves):
            datos["Administración"] = texto_no_disponible
            datos["Sistema"] = texto_no_disponible
            datos["Fecha_boe"] = texto_no_disponible

            # Administración convocante es la suma de lo indicado en el título + fecha_boe
            admin_match = re.search(
                r"\b\w*secretaría\w*\b",
                texto_titulo,
                re.IGNORECASE,
            )
            if admin_match:
                datos["Administración"] = admin_match.group().strip()

            admin_match = re.search(
                r"(Ministerio [^,.\n]+)",
                texto_fecha_boe,
                re.IGNORECASE,
            )
            if admin_match:
                ministerio = admin_match.group(1).strip()
                if datos["Administración"] == texto_no_disponible:
                    datos["Administración"] = ministerio
                else:
                    datos["Administración"] += f" ({ministerio})"

            # Estos campos no aparecen en la Admon del Estado.
            datos["Escala"] = texto_no_disponible
            datos["Subescala"] = texto_no_disponible
            datos["Clase"] = texto_no_disponible

            # Sistema
            sistema_match = re.search(
                r"Sistema ([^,.\n]+)", texto_titulo, re.IGNORECASE
            )
            if sistema_match:
                datos["Sistema"] = sistema_match.group(1).strip().title()

            # Turno
            turno_match = re.search(
                r"(Turno [^,.\n]+)",
                texto_contenido,
                re.IGNORECASE,
            )
            if turno_match:
                datos["Turno"] = turno_match.group(0).strip()
            else:
                datos["Turno"] = texto_no_disponible

            # Fecha boe
            fecha_encabezado = re.search(
                r"(?:de\s+)?(\d{1,2} de \w+ de \d{4})", texto_fecha_boe
            )
            if fecha_encabezado:
                datos["Fecha_boe"] = fecha_encabezado.group(1).strip()

            datos["Publicación"] = texto_no_disponible
            datos["Enlace"] = enlace if enlace else texto_no_disponible

            # Añado la información del municipio para representarlo en el mapa
            diccionario_municipio = buscar_municipio("Madrid")
            if diccionario_municipio:
                datos = {**datos, **diccionario_municipio}

            return datos
        # Si no coincide con la búsqueda del usuario...
        else:
            return None
    # Si no se encuentran plazas en el enlace....
    else:
        return None


def convertir_en_numero(valor_raw):
    try:
        if valor_raw.isdigit():
            numero = int(valor_raw)
        else:
            # la librería w2n no reconoce "una" o "un" como número
            if valor_raw in ["una", "un"]:
                valor_raw = "uno"
            numero = w2n.word_to_num(valor_raw)
    except (TypeError, ValueError):
        return valor_raw  # Deja la palabra si no se puede convertir
    return int(numero)


"""Para Pruebas de test """

import requests
from bs4 import BeautifulSoup


def obtener_texto_boe(url):
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    # El contenido del BOE está en un <div id="textoxs">
    contenido = soup.find("div", id="textoxslt")
    if not contenido:
        raise ValueError("No se pudo encontrar el contenido principal del BOE.")

    contenido = contenido.get_text(separator="\n", strip=True)
    titulo = soup.find(class_="documento-tit").text.strip()
    fecha_boe = soup.find("div", class_="metadatos").text.strip()

    return contenido, titulo, fecha_boe


def analizar_boe_estado(url):
    contenido, titulo, fecha_boe = obtener_texto_boe(url)
    return buscar_coincidencias_estado("", contenido, titulo, fecha_boe, url)


def analizar_boe_local(url):
    contenido, titulo, fecha_boe = obtener_texto_boe(url)
    return buscar_coincidencias_local("", contenido, titulo, fecha_boe, url)


if __name__ == "__main__":
    # 🧪 Prueba con la URL del BOE proporcionado IIE
    url_boe = "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2024-7339"
    datos_extraidos = analizar_boe_estado(url_boe)

    for clave, valor in datos_extraidos.items():
        print(f"{clave}: {valor}")
    print()

    # Minas
    url_boe = "https://boe.es/diario_boe/txt.php?id=BOE-A-2024-27428"
    datos_extraidos = analizar_boe_estado(url_boe)

    for clave, valor in datos_extraidos.items():
        print(f"{clave}: {valor}")
    print()

    # Arquitectos Hacienda
    url_boe = "https://www.boe.es/buscar/doc.php?id=BOE-A-2024-27415"
    datos_extraidos = analizar_boe_estado(url_boe)

    for clave, valor in datos_extraidos.items():
        print(f"{clave}: {valor}")
    print()

    # Abogados
    url_boe = "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2024-23785"
    datos_extraidos = analizar_boe_estado(url_boe)

    for clave, valor in datos_extraidos.items():
        print(f"{clave}: {valor}")
    print()

    # Local: 23/05/2025
    # url_boe = "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2025-10238"
    # datos_extraidos = analizar_boe_local(url_boe)

    # print(datos_extraidos)
