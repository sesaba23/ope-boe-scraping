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

texto_busqueda = ""  # guarda el texto de búsqueda introducido por el usuario

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
    texto_busqueda = input(
        f"Introduzca el tipo de plaza a buscar [Si deja el campo en blanco se "
        "buscarán todas las plazas publicadas en el día seleccionado]: "
    )
    if not texto_busqueda:
        fecha_inicio = input(
            f"Introduzca la fecha de publicación del B.O.E (dd/mm/yyyy) [Por defecto: {fechas.fecha_hoy()} (Hoy)]: "
        )
        if not fecha_inicio:
            fecha_inicio = fechas.fecha_hoy()
        fecha_fin = fecha_inicio
# Si paso argumentos o introduzco un filtro una vez en ejecución,
# busca las convocatorias que coincidan en el rango de fechas
if len(sys.argv) >= 2 or texto_busqueda:
    # Si paso argumentos en la línea de comandos, los unimos en una cadena
    if len(sys.argv) >= 2:
        texto_busqueda = " ".join(str(x) for x in sys.argv[1:])
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

# Lista para almacenar los Diccionarios de los puestos encontrados temporalmente
lista_diccionarios_puestos = []

# Diccionario de listas donde se van almacenando los puestos encontrados hasta
#   que se crea el DataFrame con el que se trabaja para guardar los resultados
#   en el archivo Excel
diccionario_puestos = {}

# Diccionario de listas donde se guarda un código único para cada búsqueda
#   para evitar volver a buscar en el BOE
#   y así evitar duplicados en el archivo Excel
#   El código está formado por:
# el enlace de cada boe a las opososiciones si la búsqueda es sin argumentos, y
# el enlace+textobusqueda si se pasa un argumento.
#   De esta manera el código es único para cada búsqueda.
#         "Código": [enlace+texto_busqueda]
diccionario_busquedas = {"Código": []}
codigo_busqueda = ""

""" 
Empezar a buscar contenido en los enlaces encontrados
"""

# Mostrar progreso mientras se procesan los enlaces encontrados
print(f"\n{Fore.BLUE}Procesando los enlaces encontrados...{Fore.RESET}")
for i, enlace in enumerate(
    barraprogreso.barra_progreso_color(
        enlaces_oposiciones, total=len(enlaces_oposiciones)
    )
):
    # Genero el código único para cada búsqueda
    if len(sys.argv) < 2:  # Si no se pasa un argumento, el código es el enlace
        codigo = enlace
    if (
        texto_busqueda
    ):  # Si se pasa un argumento, lo añadimos al enlace añadiendo un "+"
        if len(sys.argv) >= 2:
            codigo_busqueda = "+".join(str(x) for x in sys.argv[1:])
        else:
            codigo_busqueda = texto_busqueda.replace(" ", "+")
        codigo = enlace + "_" + codigo_busqueda

    # Comprobar si el enlace ya ha sido procesado
    if codigo not in df_busquedas["Código"].values:
        diccionario_busquedas["Código"].append(codigo)
        page = requests.get(enlace)
        soup = BeautifulSoup(page.content, "html.parser")

        # El texto que contiene la información de interés está dentro de un
        #   div con el id "textoxslt" y en las clases "documento-tit" y "metadatos"
        contenidos = soup.find_all("div", id="textoxslt")
        titulo = soup.find(class_="documento-tit").text.strip()
        fecha_boe = soup.find("div", class_="metadatos").text.strip()

        # Comienzo a buscar las coincidencias en el objeto Match devuelto por findall
        for contenido in contenidos:
            # La función devuelve una lista de diccionarios con las coincidencias y
            # None si no se encuentra nada
            diccionario = coincidencias.buscar_coincidencias_todas(
                texto_busqueda, contenido.text, titulo, fecha_boe, enlace
            )
            # Si se encuentra una coincidencia, se añade al diccionario
            if diccionario:
                lista_diccionarios_puestos.extend(diccionario)

# Convierte "lista_diccionarios_puestos" en diccionario de listas si hay coincidencias
if len(lista_diccionarios_puestos) != 0:
    diccionario_puestos = {
        clave: [d[clave] for d in lista_diccionarios_puestos]
        for clave in lista_diccionarios_puestos[0]
    }


"""
    Código para crear el DataFrame e imprimirlo por pantalla antes de guadarlo en Excell
"""
# Convertimos el "diccionario_puestos" en un DataFrame de pandas
df_diccionario_puestos = pd.DataFrame(diccionario_puestos)
# Combinar el DataFrame existente (df_opo_guardadas) con el nuevo (df_diccionario_puestos)
df_combinado = pd.concat([df_opo_guardadas, df_diccionario_puestos], ignore_index=True)

# Verificar las columnas del DataFrame antes de eliminar duplicados
print(f"Columnas del DataFrame combinado: {df_combinado.columns.tolist()}")

#! Este código es para hacer pruebas. Después borrarlo
# Asegurarse de que las columnas necesarias existen
columnas_necesarias = ["Puesto", "Fecha_boe", "Administración", "Escala"]
for columna in columnas_necesarias:
    if columna not in df_combinado.columns:
        print(
            f"⚠️ La columna '{columna}' no existe en el DataFrame. Se agregará con valores predeterminados."
        )
        df_combinado[columna] = "No disponible"
#! Hasta aquí

# Eliminar duplicados si es necesario, basándonos en columnas clave
#   (por ejemplo, "Puesto" y "Fecha")
df_combinado = df_combinado.drop_duplicates(
    subset=["Puesto", "Fecha_boe", "Administración", "Enlace"], keep="last"
)


"""
    Código para guardar los resultados en un archivo Excel
"""
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
# Guardar los DataFrame en el archivo Excel creado al principio si está cerrado
try:
    with pd.ExcelWriter(
        "BOE-oposiciones.xlsx", mode="a", engine="openpyxl", if_sheet_exists="replace"
    ) as writer:
        df_busquedas_combinado.to_excel(writer, sheet_name="Búsquedas", index=False)
        df_combinado.to_excel(writer, sheet_name="Oposiciones", index=False)
except PermissionError:
    print(
        f"\n{Fore.RED}El archivo 'BOE-oposiciones.xlsx' está abierto. "
        f"Cierre el archivo y vuelva a intentarlo.{Fore.RESET}"
    )
    sys.exit(0)

"""
    Buscamos los resultados buscados por el usuario dentro del propio
     Dataframe, incluidas las fechas de inicio y fin 
"""

# Convertir la columna "Fecha" del DataFrame al formato datetime en una nueva columna
#   "Fecha_dt" para facilitar la comparación de fechas
#   Si cambiamos directamente el formato de la columna fecha, al ejecutar, da un warning
df_combinado["Fecha_dt"] = df_combinado["Fecha_boe"].apply(fechas.convertir_fecha)

# Filtrar el DataFrame por el rango de fechas
# Las fechas de inicio y final son el primer y último elemento de "lista_fechas"
df_combinado_filtrado_por_fecha = df_combinado[
    (df_combinado["Fecha_dt"] >= lista_fechas[0])
    & (df_combinado["Fecha_dt"] <= lista_fechas[-1])
]

# Eliminar la columna auxiliar "Fecha_dt" si no es necesaria
df_combinado_filtrado = df_combinado_filtrado_por_fecha.drop(columns=["Fecha_dt"])

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
