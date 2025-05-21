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
import time

MAX_REINTENTOS = 3
RETRASO_SEGUNDOS = 2

tiempo_inicio = time.time()

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
df_log_errores = dataframes_dict["Log-errores"]

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
# lista de diccionarios para guardar un registro de errores al acceder a los enlaces
lista_diccionario_errores = []

print(f"\n{Fore.BLUE}Obteniendo URLs de los días seleccionados...{Fore.RESET}")
for i, url in enumerate(
    barraprogreso.barra_progreso_color(urls_dias, total=len(urls_dias))
):
    reintentos = 0
    page = None
    while reintentos < 3:
        try:
            page = requests.get(url, timeout=10)  # 10 segundos de espera máximo
            break  # ëxito, salir del bucle
        except requests.exceptions.Timeout:
            reintentos += 1
            print(f"Timeout al acceder a {url} (reintento {reintentos})")
            if reintentos == 3:
                lista_diccionario_errores.append({"Timeout al acceder": url})
            time.sleep(RETRASO_SEGUNDOS)
        except Exception as e:
            reintentos += 1
            print(f"Error al acceder a {url}: {e} (reintento {reintentos})")
            if reintentos == 3:
                lista_diccionario_errores.append({"Error al acceder": url})
            time.sleep(RETRASO_SEGUNDOS)
    if page is not None:
        # Si no se pudo acceder tras los reintentos, pasar al siguiente
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
    # Genero el código único para cada búsqueda
    if not texto_busqueda:  # Si no se pasa un argumento, el código es el enlace
        codigo = enlace
    else:
        codigo_busqueda = texto_busqueda.replace(" ", "+")
        codigo = f"{enlace}_{codigo_busqueda}"

    # Comprobar si el enlace ya ha sido procesado
    if codigo not in df_busquedas["Código"].values:
        diccionario_busquedas["Código"].append(codigo)

        reintentos = 0
        while reintentos < MAX_REINTENTOS:
            try:
                print(f"Procesando enlace: {enlace}")
                page = requests.get(enlace, timeout=5)
                break  # Si la petición tiene éxito, salimos del bucle
            except requests.exceptions.Timeout:
                reintentos += 1
                print(f"Timeout al acceder a {enlace} (reintento {reintentos})")
                if reintentos == MAX_REINTENTOS:
                    lista_diccionario_errores.append({"Timeout al acceder": enlace})
                    continue
                time.sleep(RETRASO_SEGUNDOS)
            except Exception as e:
                reintentos += 1
                print(f"Error al acceder a {enlace}: {e} (reintento {reintentos})")
                if reintentos == MAX_REINTENTOS:
                    lista_diccionario_errores.append({"Error al acceder": enlace})
                    continue
                time.sleep(RETRASO_SEGUNDOS)

        if page is not None:
            try:
                soup = BeautifulSoup(page.content, "html.parser")
                # El texto que contiene la información de interés está dentro de un
                #   div con el id "textoxslt" y en las clases "documento-tit" y "metadatos"
                contenidos = soup.find_all("div", id="textoxslt")
                titulo = soup.find(class_="documento-tit").text.strip()
                fecha_boe = soup.find("div", class_="metadatos").text.strip()
            except Exception as e:
                print(f"Error procesando el HTML de {enlace}: {e}")
                lista_diccionario_errores.append({"Error procesando el HTML": enlace})
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
                    lista_diccionario_errores.append(
                        {"Error buscando coincidencias": enlace}
                    )
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

# Guardar los errores en el DataFrame de log de errores
if lista_diccionario_errores:
    fecha_error = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    errores_formateados = []
    for d in lista_diccionario_errores:
        for k, v in d.items():
            errores_formateados.append(
                {"Fecha": fecha_error, "Tipo de error": k, "Enlace Web": v}
            )
    df_log_errores = pd.concat(
        [df_log_errores, pd.DataFrame(errores_formateados)], ignore_index=True
    )

# Guardar los DataFrame en el archivo Excel creado al principio si está cerrado
preparar_archivo_datos.guardar_excel(
    df_combinado, df_busquedas_combinado, df_log_errores
)

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

tiempo_fin = time.time()
duracion = tiempo_fin - tiempo_inicio
if duracion < 60:
    print(
        f"\n{Fore.YELLOW}Tiempo total de ejecución: {duracion:.2f} segundos{Fore.RESET}"
    )
elif duracion < 3600:
    minutos = int(duracion // 60)
    segundos = int(duracion % 60)
    print(
        f"\n{Fore.YELLOW}Tiempo total de ejecución: {minutos} min {segundos} s{Fore.RESET}"
    )
else:
    horas = int(duracion // 3600)
    minutos = int((duracion % 3600) // 60)
    segundos = int(duracion % 60)
    print(
        f"\n{Fore.YELLOW}⌛🕒 Tiempo total de ejecución: {horas} h {minutos} min {segundos} s{Fore.RESET}"
    )
