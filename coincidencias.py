import re
from word2number_es import w2n


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


def buscar_coincidencias_todas(
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
            (?P<puesto>[\w/áéíóúñÁÉÍÓÚÑ\s\-]+?),\s+
            perteneciente(?:s)?\s+a\s+la\s+escala\s+de\s+
            (?P<escala>[\w\sáéíóúÁÉÍÓÚñÑ]+?),\s+
            subescala\s+
            (?P<subescala>[\w\sáéíóúÁÉÍÓÚñÑ]+?)
            (?:\s+y\s+clase\s+
            (?P<clase>[\w\sáéíóúÁÉÍÓÚñÑ]+?))?,\s+
            mediante\s+el\s+sistema\s+de\s+
            (?P<sistema>[\w\s\-]+?),\s+
            en\s+turno\s+
            (?P<turno>[\w\s]+?)\.
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
        valor_raw = datos["num_plazas"].lower()

        try:
            if valor_raw.isdigit():
                numero = int(valor_raw)
            else:
                # la librería w2n no reconoce "una" o "un" como número
                if valor_raw in ["una", "un"]:
                    valor_raw = "uno"
                numero = w2n.word_to_num(valor_raw)
        except:
            numero = valor_raw  # Deja la palabra si no se puede convertir

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
                    else texto_no_disponible
                ),
                "Fecha_boe": (
                    fecha_publicacion if fecha_publicacion else texto_no_disponible
                ),
                "Publicacion": (
                    "«" + texto_publicacion
                    if texto_publicacion
                    else texto_no_disponible
                ),
                "Enlace": enlace if enlace else "Enlace " + texto_no_disponible,
            }
            resultados.append(resultado)

    if len(resultados) == 0:
        return None
    else:
        return resultados
