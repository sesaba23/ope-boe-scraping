import fechas
import coincidencias
import barraprogreso
import impresiones
import preparar_archivo_datos
from entradas_datos import solicitar_fechas_y_validar
from mapa_plazas import generar_mapa_municipios

from datetime import datetime
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re, warnings  # Importar módulos de expresiones regulares
import sys  # Importar sys para manejar argumentos de línea de comandos
from colorama import Fore, Style
import pandas as pd
from openpyxl import Workbook

# Un ejemplo cualquiera de la dirección de la sección 'oposiciones y concursos'
# de la página del BOE
URL_base_oposiciones = "https://www.boe.es/boe/dias/2025/04/03/index.php?s=2B"
# Obtengo los componentes de la URL anterior
URL_componentes = urlparse(URL_base_oposiciones)
# URL base que da acceso al calendario del BOE
URL_base = "https://www.boe.es/boe/dias/"
URL_base_enlaces = "https://www.boe.es"

texto_busqueda = ""  # guarda el texto de búsqueda introducido por el usuario

# Inicializo el archivo donde se va guardando la información para usar como BD
dataframes_dict = preparar_archivo_datos.preparar_excel_y_dataframes()

"""df_busquedas almacena el histórico de búsquedas para evitar volver a buscar en el BOE
   df_opo_guardadas almacena el histórico de oposiciones buscadas para futuras consultas"""
df_busquedas = dataframes_dict["Búsquedas"]
df_opo_guardadas = dataframes_dict["Oposiciones"]
if df_busquedas.empty:
    df_busquedas = pd.DataFrame({"Código": []})  # Inicializar con una estructura básica

""" Código para solicitar al usuario la fecha de inicio y fin de la búsqueda
   y comprobar que son válidas """
fecha_actual = fechas.fecha_hoy()  # Obtener la fecha actual

if len(sys.argv) >= 2:
    texto_busqueda = " ".join(str(x) for x in sys.argv[1:])


# Llamar a la función para solicitar al usuario las opciones de búsqueda y validar las fechas
texto_busqueda, fecha_inicio, fecha_fin, lista_fechas = solicitar_fechas_y_validar(
    texto_busqueda, fecha_actual, fechas
)


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
    try:
        page = requests.get(url, timeout=10)  # 10 segundos de espera máximo
    except requests.exceptions.Timeout:
        print(f"Timeout al acceder a {url}")
        continue
    except Exception as e:
        print(f"Error al acceder a {url}: {e}")
        continue

    try:
        soup = BeautifulSoup(page.content, "html.parser")
        # Buscar todos los enlaces a "otros formatos" (txt, es decir, html)
        #   suponiendo que los enlaces tienen un atributo 'href' que contiene la URL
        enlaces = soup.find_all("a", href=True)
    except Exception as e:
        print(f"Error procesando el HTML de {url}: {e}")
        continue

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
    print(f"Procesando enlace: {enlace}")
    #! Revisar para solo poner los if con texto busqueda
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
    #! fin revisión

    # Comprobar si el enlace ya ha sido procesado
    if codigo not in df_busquedas["Código"].values:
        diccionario_busquedas["Código"].append(codigo)
        # Peticiones HTTP con timeout para evitar bloqueos
        try:
            page = requests.get(enlace, timeout=5)  # 5 segundos de espera máximo
        except requests.exceptions.Timeout:
            print(f"Timeout al acceder a {enlace}")
            continue
        except Exception as e:
            print(f"Error al acceder a {enlace}: {e}")
            continue

        try:
            soup = BeautifulSoup(page.content, "html.parser")
            # El texto que contiene la información de interés está dentro de un
            #   div con el id "textoxslt" y en las clases "documento-tit" y "metadatos"
            contenidos = soup.find_all("div", id="textoxslt")
            titulo = soup.find(class_="documento-tit").text.strip()
            fecha_boe = soup.find("div", class_="metadatos").text.strip()
        except Exception as e:
            print(f"Error procesando el HTML de {enlace}: {e}")
            continue

        # Comienzo a buscar las coincidencias en el objeto Match devuelto por findall
        for contenido in contenidos:
            try:
                # La función devuelve una lista de diccionarios con las coincidencias y
                # None si no se encuentra nada
                diccionario = coincidencias.buscar_coincidencias_todas(
                    texto_busqueda, contenido.text, titulo, fecha_boe, enlace
                )
                # Si se encuentra una coincidencia, se añade al diccionario
                if diccionario:
                    lista_diccionarios_puestos.extend(diccionario)
            except Exception as e:
                print(f"Error buscando coincidencias en {enlace}: {e}")
                continue

"""
    Convierte "lista_diccionarios_puestos" en un diccionario de listas si hay coincidencias
    Trata de obtener todas las claves exitentes en todos los registros y combinarlas
    De otra manera, sólo incluiría las claves del primer registro de la lista de diccionarios
    Se puede dar el caso de que no se haya encontrado el municipio en el csv del primer
    registro y, por tanto, no incluiría el resto de claves, aunque otros registros
    las tuviesen.
    Se mantiene el orden de las claves del diccionario
"""
if len(lista_diccionarios_puestos) != 0:
    # Claves en el primer diccionario (orden principal)
    claves_ordenadas = list(lista_diccionarios_puestos[0].keys())
    # Añadir claves nuevas que puedan aparecer en otros diccionarios
    for d in lista_diccionarios_puestos:
        for k in d.keys():
            if k not in claves_ordenadas:
                claves_ordenadas.append(k)
    diccionario_puestos = {
        clave: [d.get(clave) for d in lista_diccionarios_puestos]
        for clave in claves_ordenadas
    }
    # print(diccionario_puestos)

# Tratar los diccionarios que hemos creado para mezclarlos con los dataframes
#   obtenidos del archivo Excel
df_combinado, df_busquedas_combinado = preparar_archivo_datos.combinar_dataframes(
    diccionario_puestos, diccionario_busquedas, df_opo_guardadas, df_busquedas
)

# Guardar los DataFrame en el archivo Excel creado al principio si está cerrado
preparar_archivo_datos.guardar_excel(df_combinado, df_busquedas_combinado)


# Filtrar el DataFrame por el texto de búsqueda introducido por el usuario y
#  las fechas de inicio y fin
df_filtrado_por_patron = preparar_archivo_datos.prepara_data_frame_mostrar_resultados(
    texto_busqueda, df_combinado, lista_fechas
)

# Imprimimos en pantalla los resultados
diccionario = df_filtrado_por_patron.to_dict(orient="list")
impresiones.imprimir_diccionario_puestos(
    diccionario,
    f_inicio=fecha_inicio,
    f_fin=fecha_fin,
    busqueda=texto_busqueda,
)

# Mostramos en un mapa web los municipios encontrados en la búsqueda
generar_mapa_municipios(df_filtrado_por_patron)
