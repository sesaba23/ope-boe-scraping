import fechas
import coincidencias
import barraprogreso
import impresiones
import preparar_archivo_datos
from trazabilidad import añadir_trazabilidad_convocatorias
from publicaciones import crear_registro_publicacion, registrar_publicacion
from entradas_datos import solicitar_fechas_y_validar
from mapa_plazas import enriquecer_filas_sin_coordenadas, generar_mapa_municipios

from datetime import datetime
import requests
from bs4 import BeautifulSoup, ParserRejectedMarkup
from urllib.parse import parse_qs, urljoin, urlparse
import sys  # Importar sys para manejar argumentos de línea de comandos
from colorama import Fore
import pandas as pd
import time
from tqdm import tqdm

MAX_REINTENTOS = 3
RETRASO_SEGUNDOS = 2


def _buscar_enlaces_2b_en_indice_general(contenido):
    soup = BeautifulSoup(contenido, "html.parser")
    enlaces_secciones = [
        enlace
        for enlace in soup.find_all("a", href=True)
        if urlparse(enlace["href"]).path.endswith("index.php")
        and "s" in parse_qs(urlparse(enlace["href"]).query)
    ]
    enlace_seccion_2b = next(
        (
            enlace
            for enlace in enlaces_secciones
            if parse_qs(urlparse(enlace["href"]).query).get("s") == ["2B"]
        ),
        None,
    )
    encabezado_2b = next(
        (
            encabezado
            for encabezado in soup.find_all(["h2", "h3"])
            if "II. Autoridades y personal. - B. Oposiciones y concursos"
            in encabezado.get_text(" ", strip=True)
        ),
        None,
    )

    if enlace_seccion_2b is None and encabezado_2b is None:
        if enlaces_secciones:
            return []
        raise ValueError("No se reconoce la estructura de secciones del índice")
    if encabezado_2b is None:
        raise ValueError("Se enlaza la sección II.B pero no se encuentra su contenido")

    enlaces = []
    enlaces_vistos = set()
    for elemento in encabezado_2b.find_all_next():
        if elemento.name == encabezado_2b.name:
            break
        if elemento.name == "a" and elemento.has_attr("href"):
            href = elemento["href"]
            if "txt" in href and href not in enlaces_vistos:
                enlaces.append(elemento)
                enlaces_vistos.add(href)
    return enlaces


def _ejecutar_aplicacion():
    tiempo_inicio = time.time()

    # Un ejemplo cualquiera de la dirección de la sección 'oposiciones y concursos'
    # de la página del BOE
    URL_BASE_OPOSICIONES = "https://www.boe.es/boe/dias/2025/04/03/index.php?s=2B"
    # Obtengo los componentes de la URL anterior
    URL_COMPONENTES = urlparse(URL_BASE_OPOSICIONES)
    # URL base que da acceso al calendario del BOE
    URL_BASE = "https://www.boe.es/boe/dias/"
    URL_BASE_ENLACES = "https://www.boe.es"

    texto_busqueda = ""  # guarda el texto de búsqueda introducido por el usuario

    # Inicializo el archivo donde se va guardando la información para usar como BD
    dataframes_dict = preparar_archivo_datos.preparar_excel_y_dataframes()

    """df_busquedas almacena el histórico de búsquedas para evitar volver a buscar en el BOE
       df_opo_guardadas almacena el histórico de oposiciones buscadas para futuras consultas"""
    df_busquedas = dataframes_dict["Búsquedas"]
    df_opo_guardadas = dataframes_dict["Oposiciones"]
    df_log_errores = dataframes_dict["Log-errores"]
    df_publicaciones = dataframes_dict.get("Publicaciones", pd.DataFrame())

    if df_busquedas.empty:
        df_busquedas = pd.DataFrame({"Código": []})  # Inicializar con una estructura básica
    codigos_procesados = set(df_busquedas["Código"].dropna())

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
        urljoin(URL_BASE, f"{fecha}/index.php?{URL_COMPONENTES.query}")
        for fecha in lista_fechas
    ]

    # Lista para almacenar los enlaces a otros formatos
    enlaces_oposiciones = []
    # lista de diccionarios para guardar un registro de errores al acceder a los enlaces
    lista_diccionario_errores = []

    print(f"\n{Fore.BLUE}Obteniendo URLs de los días seleccionados...{Fore.RESET}")
    """ Se mantiene a efectos ilustrativos: barra personalizada de progreso
    for i, url in enumerate(
        barraprogreso.barra_progreso_color(urls_dias, total=len(urls_dias))
    ):
    """
    barra = tqdm(urls_dias, desc="", colour="blue")
    for url in barra:
        reintentos = 0
        page = None
        while reintentos < MAX_REINTENTOS:
            try:
                page = requests.get(url, timeout=10)  # 10 segundos de espera máximo
                page.raise_for_status()
                break  # ëxito, salir del bucle
            except requests.exceptions.HTTPError as e:
                page = None
                if e.response is not None and e.response.status_code == 404:
                    break
                if e.response is not None and e.response.status_code == 400:
                    url_indice_general = url.split("?", 1)[0]
                    try:
                        page_indice_general = requests.get(
                            url_indice_general, timeout=10
                        )
                        page_indice_general.raise_for_status()
                    except requests.exceptions.RequestException as error_fallback:
                        barra.set_description(
                            f"Error al acceder a {url_indice_general}: {error_fallback}"
                        )
                        lista_diccionario_errores.append(
                            {"Error al acceder": url_indice_general}
                        )
                        break
                    try:
                        enlaces_fallback = _buscar_enlaces_2b_en_indice_general(
                            page_indice_general.content
                        )
                    except (ParserRejectedMarkup, ValueError) as error_estructura:
                        barra.set_description(
                            f"Error procesando el HTML de {url_indice_general}: "
                            f"{error_estructura}"
                        )
                        lista_diccionario_errores.append(
                            {"Error de estructura": url_indice_general}
                        )
                        break
                    for enlace in enlaces_fallback:
                        enlaces_oposiciones.append(
                            urljoin(URL_BASE_ENLACES, enlace["href"])
                        )
                    break
                reintentos += 1
                barra.set_description(
                    f"Error al acceder a {url}: {e} (reintento {reintentos})"
                )
                if reintentos == MAX_REINTENTOS:
                    lista_diccionario_errores.append({"Error al acceder": url})
                time.sleep(RETRASO_SEGUNDOS)
            except requests.exceptions.Timeout:
                page = None
                reintentos += 1
                barra.set_description(
                    f"Timeout al acceder a {url} (reintento {reintentos})"
                )
                if reintentos == MAX_REINTENTOS:
                    lista_diccionario_errores.append({"Timeout al acceder": url})
                time.sleep(RETRASO_SEGUNDOS)
            except requests.exceptions.RequestException as e:
                page = None
                reintentos += 1
                barra.set_description(
                    f"Error al acceder a {url}: {e} (reintento {reintentos})"
                )
                if reintentos == MAX_REINTENTOS:
                    lista_diccionario_errores.append({"Error al acceder": url})
                time.sleep(RETRASO_SEGUNDOS)
        if page is not None:
            # Si no se pudo acceder tras los reintentos, pasar al siguiente
            try:
                soup = BeautifulSoup(page.content, "html.parser")
                # Buscar todos los enlaces a "otros formatos" (txt, es decir, html)
                #   suponiendo que los enlaces tienen un atributo 'href' que contiene la URL
                enlaces = soup.find_all("a", href=True)
            except ParserRejectedMarkup as e:
                barra.set_description(f"Error procesando el HTML de {url}: {e}")
                lista_diccionario_errores.append({"Error de estructura": url})
                continue

            for enlace in enlaces:
                if any(formato in enlace["href"] for formato in ["txt"]):
                    enlaces_oposiciones.append(URL_BASE_ENLACES + enlace["href"])

    # Si no hay publicaciones y la consulta fue correcta, mostramos mensaje y paramos
    if not enlaces_oposiciones and not lista_diccionario_errores:
        if fecha_fin == fecha_inicio:
            print(
                f"\n\n{Fore.RED}❌ El {Fore.WHITE}{fecha_inicio} {Fore.RED}no se ha publicado ningún proceso selectivo\n"
            )
        else:
            print(
                f"\n\n{Fore.RED}❌ Entre el {Fore.WHITE}{fecha_inicio}{Fore.RED} y {Fore.WHITE}{fecha_fin}{Fore.RED} no se ha publicado ningún proceso selectivo\n"
            )
        sys.exit(0)

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
    publicaciones_analizadas = 0
    publicaciones_fallidas = set()

    """ 
    Empezar a buscar contenido en los enlaces encontrados
    """
    print(f"\n{Fore.GREEN}Procesando enlaces...{Fore.RESET}")
    # Mostrar progreso mientras se procesan los enlaces encontrados
    """ Se mantiene a efectos ilustrativos: barra personalizada de progreso
    for i, enlace in enumerate(
        barraprogreso.barra_progreso_color(
            enlaces_oposiciones,
            total=len(enlaces_oposiciones),
        )
    ):"""
    barra = tqdm(
        enlaces_oposiciones,
        desc="",
        colour="green",
        dynamic_ncols=True,
    )
    for enlace in barra:
        barra.set_description(f"{enlace[:19]}...{enlace[-15:]}")
        # Genero el código único para cada búsqueda
        if not texto_busqueda:  # Si no se pasa un argumento, el código es el enlace
            codigo = enlace
        else:
            codigo_busqueda = texto_busqueda.replace(" ", "+")
            codigo = f"{enlace}_{codigo_busqueda}"

        # Comprobar si el enlace ya ha sido procesado
        if codigo not in codigos_procesados:
            page = None
            reintentos = 0
            while reintentos < MAX_REINTENTOS:
                try:
                    page = requests.get(enlace, timeout=5)
                    page.raise_for_status()
                    break  # Si la petición tiene éxito, salimos del bucle
                except requests.exceptions.Timeout:
                    page = None
                    reintentos += 1
                    barra.set_description(
                        f"Timeout al acceder a {enlace[-15:]} (reintento: {reintentos})"
                    )
                    if reintentos == MAX_REINTENTOS:
                        lista_diccionario_errores.append({"Timeout al acceder": enlace})
                        continue
                    time.sleep(RETRASO_SEGUNDOS)
                except requests.exceptions.RequestException as e:
                    page = None
                    reintentos += 1
                    barra.set_description(
                        f"{Fore.RED}Error al acceder a {enlace[-15:]}: {e}{Fore.RESET}"
                    )
                    if reintentos == MAX_REINTENTOS:
                        lista_diccionario_errores.append({"Error al acceder": enlace})
                        continue
                    time.sleep(RETRASO_SEGUNDOS)

            if page is None:
                publicaciones_fallidas.add(enlace)

            if page is not None:
                try:
                    soup = BeautifulSoup(page.content, "html.parser")
                    # El texto que contiene la información de interés está dentro de un
                    #   div con el id "textoxslt" y en las clases "documento-tit" y "metadatos"
                    contenidos = soup.find_all("div", id="textoxslt")
                    elemento_titulo = soup.find(class_="documento-tit")
                    elemento_fecha = soup.find("div", class_="metadatos")
                    if not contenidos:
                        barra.set_description(
                            f"Error procesando el HTML de {enlace[-15:]}: "
                            "falta el contenido principal"
                        )
                        lista_diccionario_errores.append(
                            {"Error de estructura": enlace}
                        )
                        publicaciones_fallidas.add(enlace)
                        continue
                    if elemento_titulo is None or elemento_fecha is None:
                        raise ValueError("Faltan elementos esperados en el HTML")
                    titulo = elemento_titulo.text.strip()
                    fecha_boe = elemento_fecha.text.strip()
                except (ValueError, ParserRejectedMarkup) as e:
                    barra.set_description(
                        f"Error procesando el HTML de {enlace[-15:]}: {e}"
                    )
                    lista_diccionario_errores.append({"Error procesando el HTML": enlace})
                    publicaciones_fallidas.add(enlace)
                    continue

                # Comienzo a buscar las coincidencias en el objeto Match devuelto por findall
                analisis_correcto = True
                momento_analisis = datetime.now()
                coincidencias_publicacion = 0
                for contenido in contenidos:
                    try:
                        # La función devuelve una lista de diccionarios con las coincidencias y
                        # None si no se encuentra nada
                        lista_diccionarios_local = coincidencias.buscar_coincidencias_local(
                            texto_busqueda, contenido.text, titulo, fecha_boe, enlace
                        )
                        # Si se encuentra una coincidencia en LOCAL, se añade al diccionario
                        if lista_diccionarios_local:
                            coincidencias_publicacion += len(lista_diccionarios_local)
                            lista_diccionarios_local = añadir_trazabilidad_convocatorias(
                                lista_diccionarios_local, enlace, momento_analisis
                            )
                            lista_diccionarios_puestos.extend(lista_diccionarios_local)
                            for diccionario in lista_diccionarios_local:
                                tqdm.write(
                                    f"{diccionario["Num_plazas"]} x {diccionario["Puesto"]} en {diccionario["Administración"]}"
                                )
                        else:  # Si no, busca en ESTADO
                            diccionario_estado = coincidencias.buscar_coincidencias_estado(
                                texto_busqueda, contenido.text, titulo, fecha_boe, enlace
                            )
                            if diccionario_estado:
                                coincidencias_publicacion += 1
                                diccionario_estado = añadir_trazabilidad_convocatorias(
                                    [diccionario_estado], enlace, momento_analisis
                                )[0]
                                lista_diccionarios_puestos.append(diccionario_estado)
                                tqdm.write(
                                    f"Convocatoria del Estado encontrada: {diccionario_estado["Puesto"]}"
                                )

                    except (TypeError, ValueError) as e:
                        analisis_correcto = False
                        barra.set_description(
                            f"Error buscando coincidencias en {enlace}: {e}"
                        )
                        lista_diccionario_errores.append(
                            {"Error buscando coincidencias": enlace}
                        )
                        continue

                if analisis_correcto:
                    diccionario_busquedas["Código"].append(codigo)
                    codigos_procesados.add(codigo)
                    publicaciones_analizadas += 1
                    df_publicaciones = registrar_publicacion(
                        df_publicaciones,
                        crear_registro_publicacion(
                            enlace,
                            fecha_boe,
                            titulo,
                            coincidencias_publicacion,
                            momento_analisis,
                        ),
                    )
                else:
                    publicaciones_fallidas.add(enlace)

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
    df_combinado = enriquecer_filas_sin_coordenadas(df_combinado)

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
        df_combinado, df_busquedas_combinado, df_log_errores, df_publicaciones
    )

    if not enlaces_oposiciones:
        print(f"\n{Fore.RED}❌ No se pudo consultar el BOE para el periodo seleccionado.{Fore.RESET}")
        sys.exit(1)

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
        publicaciones_analizadas=publicaciones_analizadas,
        publicaciones_fallidas=len(publicaciones_fallidas),
    )

    # Mostramos en un mapa web los municipios encontrados en la búsqueda
    if not df_filtrado_por_patron.empty:
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


def main():
    try:
        with preparar_archivo_datos.bloqueo_excel():
            _ejecutar_aplicacion()
    except preparar_archivo_datos.ExcelBloqueadoError as error:
        print(f"\n{Fore.RED}❌ {error}{Fore.RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
