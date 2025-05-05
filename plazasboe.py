import fechas
import coincidencias
import barraprogreso
import impresiones

from datetime import datetime
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re, warnings  # Importar módulos de expresiones regulares
import sys, os  # Importar sys para manejar argumentos de línea de comandos
from colorama import Fore, Style
import pandas as pd
from openpyxl import Workbook

# Un ejemplo cualquiera de la dirección de la sección 'oposiciones y concursos'
# de la página del BOE
URL_base_oposiciones = "https://www.boe.es/boe/dias/2025/04/03/index.php?s=2B"
# obtengo los componentes de la URL anterior
URL_componentes = urlparse(URL_base_oposiciones)
# URL base que da acceso al calendario del BOE
URL_base = "https://www.boe.es/boe/dias/"
URL_base_enlaces = "https://www.boe.es"

# Cargamos un Excel con las fechas de los días que nos interesan

# Verificar si el archivo Excel existe. Si no, crearlo
if not os.path.exists("BOE-oposiciones.xlsx"):
    # Crear un nuevo libro de Excel
    wb = Workbook()
    # Renombrar la hoja activa a "busquedas"
    ws1 = wb.active
    ws1.title = "Búsquedas"
    # ws1["A1"] = "Código"
    # Crear la segunda hoja
    ws2 = wb.create_sheet(title="Oposiciones")
    # Guardar el archivo
    wb.save("BOE-oposiciones.xlsx")

# Cargamos el archivo Excel
excel_file = pd.ExcelFile("BOE-oposiciones.xlsx")

# Leer todas las hojas como diccionario de DataFrames
dataframes_dict = {
    sheet_name: excel_file.parse(sheet_name) for sheet_name in excel_file.sheet_names
}

"""df_busquedas almacena el histórico de búsquedas para evitar volver a buscar en el BOE
   df_opo_guardadas almacena el histórico de oposiciones buscadas para futuras consultas"""
df_busquedas = dataframes_dict["Búsquedas"]
df_opo_guardadas = dataframes_dict["Oposiciones"]
if df_busquedas.empty:
    df_busquedas = pd.DataFrame({"Código": []})  # Inicializar con una estructura básica

""" Código para solicitar al usuario la fecha de inicio y fin de la búsqueda
   y comprobar que son válidas """

# Si no paso argumentos, busca todas las convocatorias publicadas en un día concreto
if len(sys.argv) < 2:
    fecha_inicio = input(
        f"Introduzca la fecha de publicación del B.O.E (dd/mm/yyyy) [Por defecto: {fechas.fecha_hoy()} (Hoy)]: "
    )
    if not fecha_inicio:
        fecha_inicio = fechas.fecha_hoy()
    fecha_fin = fecha_inicio
# Si paso argumentos, busca las convocatorias que coincidan en el rango de fechas
else:
    fecha_inicio = input(
        f"Introduzca la fecha de inicio (dd/mm/yyyy) [Por defecto: {fechas.fecha_hoy()} (Hoy)]: "
    )
    # Si se elige la fecha por defecto, se asigna la fecha de hoy y no preguntamos
    #   la fecha_fin. Asumimos que sólo se quiere buscar en el día actual
    if not fecha_inicio:
        fecha_inicio = fechas.fecha_hoy()
        fecha_fin = fechas.fecha_hoy()
    else:  # En caso contrario pregunta por la fecha de fin
        fecha_fin = input(
            f"Introduzca la fecha de fin (dd/mm/yyyy) [Por defecto: {fechas.fecha_hoy()} (Hoy)]: "
        )
    if not fecha_fin:  # Por defecto la fecha_fin es la fecha de hoy
        fecha_fin = fechas.fecha_hoy()

# Comprobar si la fecha de inicio es válida
try:
    # Calculo las direcciones necesarias en función de las fechas en las que se
    #   van a buscar las distintas oposiciones
    lista_fechas = fechas.generar_rango_fechas(fecha_inicio, fecha_fin)
except ValueError:
    print(
        f"\n{Fore.RED}Una de las fechas introducidas no es válida.Asegúrese de usar el formato dd/mm/yyyy."
    )
    sys.exit(0)
    # Con el código "0" se indica que el programa terminó sin errores.
    # No se muestra el mensaje de error en pantalla.
    # con "1" indica el error por el que el programa terminó

""" Código para generar la lista de URLs de los días seleccionados
   y buscar los enlaces a otros formatos (txt) """
# Generar las URLs para cada día en el rango de fechas usando urljoin
urls_dias = [
    urljoin(URL_base, f"{fecha}/index.php?{URL_componentes.query}")
    for fecha in lista_fechas
]

# Lista para almacenar los enlaces a otros formatos
enlaces_oposiciones = []

print(f"\n{Fore.BLUE}Obteniendo URLs de los días seleccionados...{Fore.RESET}")
for i, url in enumerate(
    barraprogreso.barra_progreso_color(urls_dias, total=len(urls_dias))
):
    page = requests.get(url)
    soup = BeautifulSoup(page.content, "html.parser")

    # Buscar todos los enlaces a "otros formatos" (txt, es decir, html)
    #   suponiendo que los enlaces tienen un atributo 'href' que contiene la URL
    enlaces = soup.find_all("a", href=True)
    for enlace in enlaces:
        if any(formato in enlace["href"] for formato in ["txt"]):
            enlaces_oposiciones.append(URL_base_enlaces + enlace["href"])

    if not enlaces_oposiciones:
        print(
            f"\n{Fore.GREEN}Entre el {fecha_inicio} y {fecha_fin} no se ha publicado ningún proceso selectivo"
        )

# Diccionario para almacenar los puestos encontrados
diccionario_puestos = {
    "Fecha": [],
    "Puesto": [],
    "Administración": [],
    "Escala": [],
    "Publicación": [],
    "Enlace": [],
}

""" Creamos el diccionario para guardar la busquedas de cada ejecución
    El código está formado por:
            # el enlace de cada boe a las opososiciones si la búsqueda es sin argumentos, y
            # el enlace+textobusqueda si se pasa un argumento.
         De esta manera el código es único para cada búsqueda.
         "Código": [enlace+texto_busqueda]"""

diccionario_busquedas = {"Código": []}
texto_busqueda = ""

""" Empezar a buscar contenido en los enlaces encontrados"""

# Mostrar progreso mientras se procesan los enlaces encontrados
print(f"\n{Fore.BLUE}Procesando los enlaces encontrados...{Fore.RESET}")
for i, enlace in enumerate(
    barraprogreso.barra_progreso_color(
        enlaces_oposiciones, total=len(enlaces_oposiciones)
    )
):
    # Generar el código único para cada búsqueda
    if len(sys.argv) < 2:  # Si no se pasa un argumento, el código es el enlace
        codigo = enlace
    else:  # Si se pasa un argumento, lo añadimos al enlace añadiendo un "+"
        texto_busqueda = "+".join(str(x) for x in sys.argv[1:])
        codigo = enlace + "_" + texto_busqueda

    # Comprobar si el enlace ya ha sido procesado
    if codigo not in df_busquedas["Código"].values:
        diccionario_busquedas["Código"].append(codigo)
        page = requests.get(enlace)
        soup = BeautifulSoup(page.content, "html.parser")

        # El texto que contiene la información de interés está dentro de un
        #   div con el id "textoxslt"
        contenidos = soup.find_all("div", id="textoxslt")
        titulo = soup.find(class_="documento-tit").text.strip()
        fecha_boe = soup.find("div", class_="metadatos")

        for contenido in contenidos:
            if len(sys.argv) < 2:  # Si no se pasa un argumento
                # Buscar el texto que sigue a "un puesto de" hasta la siguiente coma
                match_puesto = re.search(
                    r"(un puesto de|plazas de|una plaza de|puestos de|cuerpo de)(.*?)(,|\.)",
                    contenido.text,
                    re.IGNORECASE,
                )
                flag = True
            else:  # Si pasamos argumentos en la linea de comandos para buscar un puesto
                # los transformamos en cadena de texto
                texto_busqueda = " ".join(str(x) for x in sys.argv[1:])
                match_puesto = coincidencias.buscar_coincidencias(
                    texto_busqueda, contenido.text
                )
                flag = False

            # Comenzamos a extraer la información que nos interesa
            # el puesto
            # la escala del puesto, y
            # la fecha de publicación.
            if (
                match_puesto
            ):  # Si se encuentra alguna plaza, sigue extrayendo información
                # group(1) contiene el patrón encontrado (por ejemplo,
                #   "un puesto de").
                # group(2) contiene el texto capturado después del patrón.
                if flag:
                    texto_extraido = match_puesto.group(2).strip()
                else:
                    texto_extraido = (
                        match_puesto.group(0).replace(",", "").strip()
                    )  # Extraer el texto encontrado

                # Buscamos en que Administración se convoca la plaza
                match_administracion = re.search(
                    r"(, del|, de la)(.*?)(,|\.)",
                    titulo,
                    re.IGNORECASE,
                )
                if match_administracion:
                    texto_administracion = match_administracion.group(2).strip()
                else:
                    texto_administracion = "No disponible"

                # Buscar el texto que sigue a "escala de" hasta el siguiente punto
                # match_escala = re.search(
                #    r"escala de (.*?\.)", contenido.text, re.IGNORECASE
                # )

                # Buscar coincidencias que contengan el puesto (texto extraido), seguido de cualquier carácter,
                # y también "escala de" hasta el siguiente punto
                patron_combinado = rf"{re.escape(texto_extraido)}.*?escala de (.*?\.)"
                match_escala = re.search(
                    patron_combinado, contenido.text, re.IGNORECASE
                )

                if match_escala:
                    texto_escala = match_escala.group(
                        1
                    )  # Extraer el texto después del patrón
                else:
                    texto_escala = "No disponible"

                # Buscamos el núm de BOE y fecha publicación
                match_num_boe = re.search(r"(\d{1,2} de \w+ de \d{4})", fecha_boe.text)
                if match_num_boe:
                    fecha_publicacion = match_num_boe.group(1)
                else:
                    fecha_publicacion = "No disponible"

                # Buscar el texto entre el primer « y la primera coma
                match_publicacion = re.search(r"(«)([^,]*,[^,]*),", contenido.text)

                if match_publicacion:
                    texto_publicacion = match_publicacion.group(
                        2
                    )  # Extraer el texto entre corchete y coma
                    if (
                        texto_publicacion[:5] == "Bolet"
                        or texto_publicacion[:5] == "Diari"
                    ):
                        None
                else:
                    texto_publicacion = "No disponible"
                    print(f"{Fore.CYAN}Publicación:{Fore.RESET}\t «{texto_publicacion}")

                # Vamos almacenando los puestos encontrados en el diccionario
                diccionario_puestos["Fecha"].append(fecha_publicacion)
                diccionario_puestos["Puesto"].append(texto_extraido)
                diccionario_puestos["Administración"].append(texto_administracion)
                diccionario_puestos["Escala"].append(texto_escala)
                diccionario_puestos["Publicación"].append(texto_publicacion)
                diccionario_puestos["Enlace"].append(enlace)


"""
    Código para guardar los resultados en un archivo Excel
"""
# Convertimos el "diccionario_puestos" en un DataFrame de pandas
df_diccionario_puestos = pd.DataFrame(diccionario_puestos)
# Combinar el DataFrame existente (df_opo_guardadas) con el nuevo (df_diccionario_puestos)
df_combinado = pd.concat([df_opo_guardadas, df_diccionario_puestos], ignore_index=True)
# Eliminar duplicados si es necesario, basándonos en columnas clave
#   (por ejemplo, "Puesto" y "Fecha")
df_combinado = df_combinado.drop_duplicates(
    subset=["Puesto", "Fecha", "Administración", "Enlace"], keep="last"
)

# Ahora convierto el "diccionario_busquedas" en otro DataFrame
df_diccionario_busquedas = pd.DataFrame(diccionario_busquedas)
# Combinar el DataFrame existente (df_busquedas) con el nuevo (df_diccionario_puestos)
df_busquedas_combinado = pd.concat(
    [df_diccionario_busquedas, df_busquedas], ignore_index=True
)
# Eliminar duplicados si es necesario, basándonos en columnas clave (por ejemplo, "Código")
df_busquedas_combinado = df_busquedas_combinado.drop_duplicates(
    subset=["Código"], keep="last"
)
# Guardar los DataFrame en el archivo Excel creado al principio
with pd.ExcelWriter(
    "BOE-oposiciones.xlsx", mode="a", engine="openpyxl", if_sheet_exists="replace"
) as writer:
    df_busquedas_combinado.to_excel(writer, sheet_name="Búsquedas", index=False)
    df_combinado.to_excel(writer, sheet_name="Oposiciones", index=False)

    # Imprimir el diccionario de convocatorias en la consola si hay resultados


"""
    Ahora buscamos los resultados buscados por el usuario dentro del propio
     Dataframe, incluidas las fechas de inicio y fin 
"""

# Convertir la columna "Fecha" del DataFrame al formato datetime en una nueva columna
#   "Fecha_dt" para facilitar la comparación de fechas
#   Si cambiamos directamente el formato de la columna fecha, al ejecutar, da un warning
df_combinado["Fecha_dt"] = df_combinado["Fecha"].apply(fechas.convertir_fecha)

# Filtrar el DataFrame por el rango de fechas
# Las fechas de inicio y final son el primer y último elemento de "lista_fechas"
df_combinado_filtrado_por_fecha = df_combinado[
    (df_combinado["Fecha_dt"] >= lista_fechas[0])
    & (df_combinado["Fecha_dt"] <= lista_fechas[-1])
]

# Eliminar la columna auxiliar "Fecha_dt" si no es necesaria
df_combinado_filtrado = df_combinado_filtrado_por_fecha.drop(columns=["Fecha_dt"])

# Formatear la columna "Fecha" al formato dd/mm/yy
# df_combinado_filtrado_por_fecha["Fecha"] = df_combinado_filtrado_por_fecha[
#    "Fecha"
# ].dt.strftime("%d/%m/%Y")

# Buscamos las coincidencias con la búsqueda introducida en la terminal
if len(sys.argv) > 1:
    texto_busqueda = " ".join(str(x) for x in sys.argv[1:])
else:
    texto_busqueda = ""

palabras_busqueda = texto_busqueda.split()
patron_regex = (
    r"\b"
    + r"\s+".join([rf"{clave}[\w/@\\]*(es)?" for clave in palabras_busqueda])
    + r"(.*?)"
)
# Desactivar warnings relacionados con expresiones regulares
warnings.filterwarnings("ignore", message="This pattern is interpreted")

# Filtrar el DataFrame por coincidencias en la columna "Puesto"
df_filtrado_por_patron = df_combinado_filtrado_por_fecha[
    df_combinado_filtrado_por_fecha["Puesto"].str.contains(
        patron_regex, flags=re.IGNORECASE, na=False
    )
]
# Restaurar los warnings después de la operación
warnings.filterwarnings("default", message="This pattern is interpreted")

# Finalmente imprimimos en pantalla los resultados
diccionario = df_filtrado_por_patron.to_dict(orient="list")
impresiones.imprimir_diccionario_puestos(
    diccionario,
    f_inicio=fecha_inicio,
    f_fin=fecha_fin,
    busqueda=texto_busqueda,
)
