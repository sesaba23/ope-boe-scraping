import fechas
import coincidencias
import barraprogreso
import impresiones
import preparar_archivo_datos
import base_datos
from boe_api import ErrorAPIBOE, extraer_publicaciones_2b_api, obtener_sumario_api
from cobertura import (crear_verificador_cobertura_indice, registrar_cobertura,
                       normalizar_cobertura)
from trazabilidad import añadir_trazabilidad_convocatorias
from trazabilidad import extraer_publicacion_id
from publicaciones import (
    crear_registro_publicacion,
    puede_reutilizar_publicacion,
    registrar_publicacion,
)
from entradas_datos import solicitar_fechas_y_validar
from mapa_plazas import enriquecer_filas_sin_coordenadas, generar_mapa_municipios
from extractor_historico_boe import extraer_desde_contenido
from procesamiento_historico import procesar_intervalo_historico
from resolucion_administraciones import enriquecer_convocatorias

from datetime import datetime
import requests
from bs4 import BeautifulSoup, ParserRejectedMarkup
from urllib.parse import parse_qs, urljoin, urlparse
import sys  # Importar sys para manejar argumentos de línea de comandos
import argparse
from colorama import Fore
import pandas as pd
import time
from tqdm import tqdm

MAX_REINTENTOS = 3
RETRASO_SEGUNDOS = 2
VERSION_EXTRACTOR_HISTORICO = "historico-experimental-2004"


def seleccionar_extractor(fecha_boe):
    """Centraliza la selección temporal; ampliable por rangos futuros."""
    texto = str(fecha_boe)
    return "historico" if "2004" in texto else "actual"


def _convocatorias_historicas_validas(publicacion_id, contenido_xml, enlace, momento):
    resultado = extraer_desde_contenido(
        publicacion_id, contenido_xml, enlace.replace("txt.php", "xml.php"), enlace)
    if resultado["clasificacion_documento"] == "INDETERMINADO":
        return resultado, []
    filas = []
    for fila in resultado["convocatorias"]:
        if not fila.get("Puesto") or not isinstance(fila.get("Num_plazas"), int):
            continue
        fila = dict(fila)
        for campo in ("Turno", "Sistema", "Escala", "Subescala", "Clase"):
            fila.setdefault(campo, "--")
            if fila[campo] is None: fila[campo] = "--"
        fila.update({"Version_extractor": VERSION_EXTRACTOR_HISTORICO,
                     "Fecha_analisis": momento.strftime("%Y-%m-%d %H:%M:%S")})
        filas.append(fila)
    return resultado, filas


def ejecutar_flujo_historico(fecha_inicio, fecha_fin, *, limite_publicaciones=None,
                             reintentar_errores=False, descubrir=None, procesar=None,
                             commit=None):
    """Única entrada histórica; el orquestador decide estado y commit."""
    if descubrir is None or procesar is None or commit is None:
        raise RuntimeError("El flujo histórico requiere callbacks transaccionales explícitos")
    return procesar_intervalo_historico(
        fecha_inicio, fecha_fin, descubrir=descubrir, procesar_publicacion=procesar,
        commit_final=commit, limite_publicaciones=limite_publicaciones,
        reintentar_errores=reintentar_errores)


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


def _añadir_publicacion_unica(enlaces, claves_vistas, enlace):
    clave = extraer_publicacion_id(enlace) or enlace
    if clave not in claves_vistas:
        enlaces.append(enlace)
        claves_vistas.add(clave)


def _descubrir_indice_html(url, obtener=None, dormir=None):
    """Ejecuta el mecanismo HTML existente y devuelve un resultado común."""
    obtener = obtener or requests.get
    dormir = dormir or time.sleep
    reintentos = 0
    page = None
    estado = "error"
    enlaces_dia = []
    claves_dia = set()
    errores = []
    mensaje = None
    while reintentos < MAX_REINTENTOS:
        try:
            page = obtener(url, timeout=10)
            page.raise_for_status()
            break
        except requests.exceptions.HTTPError as error:
            page = None
            if error.response is not None and error.response.status_code == 404:
                estado = "sin_edicion"
                break
            if error.response is not None and error.response.status_code == 400:
                url_general = url.split("?", 1)[0]
                try:
                    general = obtener(url_general, timeout=10)
                    general.raise_for_status()
                except requests.exceptions.RequestException as error_fallback:
                    mensaje = f"Error al acceder a {url_general}: {error_fallback}"
                    errores.append({"Error al acceder": url_general})
                    break
                try:
                    enlaces = _buscar_enlaces_2b_en_indice_general(general.content)
                except (ParserRejectedMarkup, ValueError) as error_estructura:
                    mensaje = f"Error procesando el HTML de {url_general}: {error_estructura}"
                    errores.append({"Error de estructura": url_general})
                    break
                for enlace in enlaces:
                    _añadir_publicacion_unica(
                        enlaces_dia,
                        claves_dia,
                        urljoin("https://www.boe.es", enlace["href"]),
                    )
                estado = "consultado"
                break
            reintentos += 1
            mensaje = f"Error al acceder a {url}: {error} (reintento {reintentos})"
            if reintentos == MAX_REINTENTOS:
                errores.append({"Error al acceder": url})
            dormir(RETRASO_SEGUNDOS)
        except requests.exceptions.Timeout:
            page = None
            reintentos += 1
            mensaje = f"Timeout al acceder a {url} (reintento {reintentos})"
            if reintentos == MAX_REINTENTOS:
                errores.append({"Timeout al acceder": url})
            dormir(RETRASO_SEGUNDOS)
        except requests.exceptions.RequestException as error:
            page = None
            reintentos += 1
            mensaje = f"Error al acceder a {url}: {error} (reintento {reintentos})"
            if reintentos == MAX_REINTENTOS:
                errores.append({"Error al acceder": url})
            dormir(RETRASO_SEGUNDOS)
    if page is not None:
        try:
            soup = BeautifulSoup(page.content, "html.parser")
            enlaces = soup.find_all("a", href=True)
        except ParserRejectedMarkup as error:
            mensaje = f"Error procesando el HTML de {url}: {error}"
            errores.append({"Error de estructura": url})
        else:
            for enlace in enlaces:
                if "txt" in enlace["href"]:
                    _añadir_publicacion_unica(
                        enlaces_dia,
                        claves_dia,
                        urljoin("https://www.boe.es", enlace["href"]),
                    )
            estado = "consultado"
    fichas = [{"Publicacion_ID": extraer_publicacion_id(enlace), "titulo": "",
               "departamento": "", "url_html": enlace, "url_xml": ""}
              for enlace in enlaces_dia]
    return {
        "estado": estado,
        "enlaces": enlaces_dia,
        "fichas": fichas,
        "errores": errores,
        "mensaje": mensaje,
        "fuente": "html",
    }


def _descubrir_indice_api_con_fallback(
    fecha, url_html, consultar_api=None, consultar_html=None
):
    """Usa la API como fuente principal y HTML solo ante error no fiable."""
    consultar_api = consultar_api or obtener_sumario_api
    consultar_html = consultar_html or _descubrir_indice_html
    try:
        resultado_api = extraer_publicaciones_2b_api(consultar_api(fecha))
        estado_api = resultado_api["estado"]
        if estado_api == "SIN_EDICION":
            return {"estado": "sin_edicion", "enlaces": [], "fichas": [], "errores": [], "mensaje": None, "fuente": "api"}
        if estado_api == "SIN_SECCION_2B":
            return {"estado": "consultado", "enlaces": [], "fichas": [], "errores": [], "mensaje": None, "fuente": "api"}
        if estado_api != "CON_PUBLICACIONES":
            raise ErrorAPIBOE("ESTRUCTURA", f"Estado API no fiable: {estado_api}")
        enlaces, fichas = [], []
        vistos = set()
        for publicacion in resultado_api["publicaciones"]:
            publicacion_id = publicacion.get("Publicacion_ID")
            enlace = publicacion.get("url_html")
            if not publicacion_id or not enlace or extraer_publicacion_id(enlace) != publicacion_id:
                raise ErrorAPIBOE("ESTRUCTURA", "Publicación API sin ID/enlace HTML coherente")
            if publicacion_id not in vistos:
                _añadir_publicacion_unica(enlaces, vistos, enlace)
                fichas.append({"Publicacion_ID": publicacion_id, "titulo": publicacion.get("titulo", ""),
                               "departamento": publicacion.get("departamento", ""), "url_html": enlace,
                               "url_xml": publicacion.get("url_xml", "")})
        return {"estado": "consultado", "enlaces": enlaces, "fichas": fichas, "errores": [], "mensaje": None, "fuente": "api"}
    except (ErrorAPIBOE, ValueError, KeyError, TypeError):
        return consultar_html(url_html)


def _lista_fechas_iso(fecha_inicio, fecha_fin):
    inicio = datetime.strptime(str(fecha_inicio), "%Y-%m-%d")
    fin = datetime.strptime(str(fecha_fin), "%Y-%m-%d")
    if inicio > fin:
        raise ValueError("La fecha inicial no puede ser posterior a la final")
    fechas_intervalo = []
    while inicio <= fin:
        fechas_intervalo.append(inicio.strftime("%Y/%m/%d"))
        inicio += pd.Timedelta(days=1)
    return fechas_intervalo


def actualizar_intervalo(fecha_inicio, fecha_fin, *, ruta_bd="datos/boe.db", on_progress=None):
    """Ejecuta el pipeline productivo actual sin interacción de terminal.

    La función no contiene extracción nueva: reutiliza exactamente índice,
    cobertura, publicaciones, normalización y persistencia de ``plazasboe``.
    """
    return actualizar_fechas(
        _lista_fechas_iso(fecha_inicio, fecha_fin), ruta_bd=ruta_bd,
        on_progress=on_progress,
    )


def actualizar_fechas(fechas_pendientes, *, ruta_bd="datos/boe.db", on_progress=None):
    """Actualiza exclusivamente las fechas pendientes ya decididas por cobertura."""
    fechas_normalizadas = sorted({str(fecha).replace("-", "/") for fecha in fechas_pendientes})
    if not fechas_normalizadas:
        return {"persistencia": None, "estados_indices": {}}
    return _ejecutar_aplicacion(
        texto_busqueda="", fechas_explicitamente=fechas_normalizadas,
        ruta_bd=ruta_bd, on_progress=on_progress, generar_mapa=False,
    )


def _notificar_progreso(on_progress, *, fase, actual, total, mensaje, fecha=None):
    """Expone el mismo contador que consume cada ``tqdm`` del pipeline.

    La CLI mantiene sus barras tal cual; la web recibe sus contadores y fases
    sin calcular una métrica paralela basada en días pendientes.
    """
    if on_progress is not None:
        on_progress({
            "fase": fase, "actual": actual, "total": total,
            "mensaje": mensaje, "fecha": fecha,
        })


def _ejecutar_aplicacion(*, texto_busqueda=None, fecha_inicio=None, fecha_fin=None,
                         fechas_explicitamente=None,
                         ruta_bd="datos/boe.db", on_progress=None, generar_mapa=True):
    tiempo_inicio = time.time()

    # Un ejemplo cualquiera de la dirección de la sección 'oposiciones y concursos'
    # de la página del BOE
    URL_BASE_OPOSICIONES = "https://www.boe.es/boe/dias/2025/04/03/index.php?s=2B"
    # Obtengo los componentes de la URL anterior
    URL_COMPONENTES = urlparse(URL_BASE_OPOSICIONES)
    # URL base que da acceso al calendario del BOE
    URL_BASE = "https://www.boe.es/boe/dias/"
    modo_programatico = fechas_explicitamente is not None or fecha_inicio is not None or fecha_fin is not None
    if fechas_explicitamente is None and modo_programatico and (fecha_inicio is None or fecha_fin is None):
        raise ValueError("La actualización programática requiere ambas fechas")
    texto_busqueda = texto_busqueda or ""  # guarda el texto de búsqueda introducido por el usuario

    """ Código para solicitar al usuario la fecha de inicio y fin de la búsqueda
       y comprobar que son válidas """
    fecha_actual = fechas.fecha_hoy()  # Obtener la fecha actual

    if not modo_programatico and len(sys.argv) >= 2:
        texto_busqueda = " ".join(str(x) for x in sys.argv[1:])

    # Llamar a la función para solicitar al usuario las opciones de búsqueda y validar las fechas
    if fechas_explicitamente is not None:
        lista_fechas = list(fechas_explicitamente)
        fecha_inicio, fecha_fin = lista_fechas[0], lista_fechas[-1]
    elif modo_programatico:
        lista_fechas = _lista_fechas_iso(fecha_inicio, fecha_fin)
    else:
        texto_busqueda, fecha_inicio, fecha_fin, lista_fechas = solicitar_fechas_y_validar(
            texto_busqueda, fecha_actual, fechas
        )

    # SQLite es la fuente de verdad. La validación es ligera y no depende del XLSX.
    base_datos.validar_base_principal(ruta_bd)
    dataframes_dict = base_datos.cargar_para_lectura(
        ruta_bd, lista_fechas[0], lista_fechas[-1],
        fechas=lista_fechas if fechas_explicitamente is not None else None,
    )

    """df_busquedas almacena el histórico de búsquedas para evitar volver a buscar en el BOE
       df_opo_guardadas almacena el histórico de oposiciones buscadas para futuras consultas"""
    df_busquedas = dataframes_dict["Búsquedas"]
    df_opo_guardadas = dataframes_dict["Oposiciones"]
    df_log_errores = dataframes_dict["Log-errores"]
    df_publicaciones = dataframes_dict.get("Publicaciones", pd.DataFrame())
    df_cobertura = dataframes_dict.get("Cobertura", pd.DataFrame())
    cobertura_reutilizable = crear_verificador_cobertura_indice(
        df_cobertura, df_publicaciones
    )

    if df_busquedas.empty:
        df_busquedas = pd.DataFrame({"Código": []})  # Inicializar con una estructura básica
    codigos_procesados = set(df_busquedas["Código"].dropna())

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
    barra = tqdm(zip(lista_fechas, urls_dias), total=len(urls_dias), desc="", colour="blue")
    estados_indices = {"consultado": 0, "sin_edicion": 0, "error": 0}
    indices_reutilizados = 0
    indices_consultados_http = 0
    indices_resueltos_api = 0
    indices_resueltos_fallback = 0
    enlaces_vistos = set()
    fichas_oposiciones = {}
    for indice_actual, (fecha_indice, url) in enumerate(barra, start=1):
        _notificar_progreso(
            on_progress, fase="indices", actual=indice_actual,
            total=len(urls_dias), mensaje="Actualizando datos del BOE…",
            fecha=fecha_indice.replace("/", "-"),
        )
        if cobertura_reutilizable(fecha_indice):
            indices_reutilizados += 1
            continue
        indices_consultados_http += 1
        resultado_indice = _descubrir_indice_api_con_fallback(fecha_indice, url)
        estado_indice = resultado_indice["estado"]
        enlaces_dia = resultado_indice["enlaces"]
        fichas_dia = resultado_indice.get("fichas", [])
        lista_diccionario_errores.extend(resultado_indice["errores"])
        if resultado_indice["mensaje"]:
            barra.set_description(resultado_indice["mensaje"])
        if resultado_indice["fuente"] == "api":
            indices_resueltos_api += 1
        else:
            indices_resueltos_fallback += 1

        if estado_indice in {"consultado", "sin_edicion"}:
            for enlace in enlaces_dia:
                _añadir_publicacion_unica(
                    enlaces_oposiciones, enlaces_vistos, enlace
                )
            for ficha in fichas_dia:
                if ficha.get("url_html"):
                    fichas_oposiciones.setdefault(ficha["url_html"], ficha)
            numero_publicaciones = len(enlaces_dia)
        else:
            numero_publicaciones = None
        df_cobertura = registrar_cobertura(
            df_cobertura,
            fecha_indice,
            estado_indice,
            numero_publicaciones,
            momento=datetime.now(),
        )
        estados_indices[estado_indice] += 1

    # Si no hay publicaciones y la consulta fue correcta, mostramos mensaje y paramos
    # Lista para almacenar los Diccionarios de los puestos encontrados temporalmente
    lista_diccionarios_puestos = []

    # Diccionario de listas donde se almacenan los puestos encontrados hasta
    # crear el DataFrame que se persistirá en SQLite.
    diccionario_puestos = {}

    # Diccionario de listas donde se guarda un código único para cada búsqueda,
    # para evitar volver a buscar en el BOE y duplicar registros en SQLite.
    #   El código está formado por:
    # el enlace de cada boe a las opososiciones si la búsqueda es sin argumentos, y
    # el enlace+textobusqueda si se pasa un argumento.
    #   De esta manera el código es único para cada búsqueda.
    #         "Código": [enlace+texto_busqueda]
    diccionario_busquedas = {"Código": []}
    publicaciones_analizadas = 0
    publicaciones_descargadas = 0
    publicaciones_reutilizadas = 0
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
    total_publicaciones = len(enlaces_oposiciones)
    for publicaciones_actual, enlace in enumerate(barra, start=1):
        _notificar_progreso(
            on_progress, fase="publicaciones", actual=publicaciones_actual,
            total=total_publicaciones, mensaje="Analizando publicaciones…",
        )
        # Metadatos del sumario disponibles para pasos posteriores; el Paso 2
        # no altera aún extracción, administración ni persistencia final.
        metadatos_sumario = fichas_oposiciones.get(enlace, {})
        barra.set_description(f"{enlace[:19]}...{enlace[-15:]}")
        # Genero el código único para cada búsqueda
        if not texto_busqueda:  # Si no se pasa un argumento, el código es el enlace
            codigo = enlace
        else:
            codigo_busqueda = texto_busqueda.replace(" ", "+")
            codigo = f"{enlace}_{codigo_busqueda}"

        publicacion_id = extraer_publicacion_id(enlace)
        reutilizable = puede_reutilizar_publicacion(
            publicacion_id,
            df_publicaciones,
            df_opo_guardadas,
        )
        if reutilizable:
            publicaciones_reutilizadas += 1
            if codigo not in codigos_procesados:
                diccionario_busquedas["Código"].append(codigo)
                codigos_procesados.add(codigo)
            continue

        # Sin identificador válido se conserva la exclusión heredada de Búsquedas.
        debe_descargar = (
            codigo not in codigos_procesados
            if publicacion_id is None
            else True
        )
        if debe_descargar:
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
                publicaciones_descargadas += 1
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
                convocatorias_publicacion = []
                if seleccionar_extractor(fecha_boe) == "historico":
                    raise RuntimeError("La publicación histórica debe entrar por ejecutar_flujo_historico")
                for contenido in contenidos:
                    try:
                        # La función devuelve una lista de diccionarios con las coincidencias y
                        # None si no se encuentra nada
                        convocatorias_extraidas = coincidencias.extraer_convocatorias_local(
                            contenido.text, titulo, fecha_boe, enlace
                        )
                        # Si no se encuentra ninguna convocatoria LOCAL, buscar en ESTADO
                        if not convocatorias_extraidas:
                            convocatorias_extraidas = (
                                coincidencias.extraer_convocatorias_estatal(
                                    contenido.text, titulo, fecha_boe, enlace
                                )
                            )
                        convocatorias_publicacion.extend(convocatorias_extraidas or [])

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
                    # Una única resolución por publicación, antes de que la clave
                    # funcional (que incluye Administración) llegue a deduplicarse.
                    metadatos_publicacion = {
                        "titulo": metadatos_sumario.get("titulo") or titulo,
                        "departamento": metadatos_sumario.get("departamento", ""),
                    }
                    convocatorias_enriquecidas, _ = enriquecer_convocatorias(
                        convocatorias_publicacion, metadatos_publicacion
                    )
                    coincidencias_publicacion = len(convocatorias_enriquecidas)
                    convocatorias_enriquecidas = añadir_trazabilidad_convocatorias(
                        convocatorias_enriquecidas, enlace, momento_analisis
                    )
                    convocatorias_filtradas = coincidencias.filtrar_convocatorias_por_texto(
                        convocatorias_enriquecidas, texto_busqueda
                    )
                    lista_diccionarios_puestos.extend(convocatorias_enriquecidas)
                    for diccionario in convocatorias_filtradas:
                        if diccionario.get("Administración") == "--":
                            tqdm.write(f"Convocatoria del Estado encontrada: {diccionario['Puesto']}")
                        else:
                            tqdm.write(f"{diccionario['Num_plazas']} x {diccionario['Puesto']} en {diccionario['Administración']}")
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
                            VERSION_EXTRACTOR_HISTORICO if seleccionar_extractor(fecha_boe) == "historico" else None,
                            departamento_boe=metadatos_sumario.get("departamento", ""),
                            titulo_sumario=metadatos_sumario.get("titulo", ""),
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

    # Mezclar los resultados con los DataFrames cargados desde SQLite.
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

    df_combinado = base_datos.normalizar_oposiciones_dataframe(df_combinado)
    lote_definitivo = {
        "Búsquedas": df_busquedas_combinado, "Oposiciones": df_combinado,
        "Log-errores": df_log_errores, "Publicaciones": df_publicaciones,
        "Cobertura": df_cobertura,
    }
    resultado_persistencia = base_datos.persistir_lote_principal(
        ruta_bd, lote_definitivo, lista_fechas[0], lista_fechas[-1],
        fechas=lista_fechas if fechas_explicitamente is not None else None,
    )
    print(
        "SQLITE: sin cambios" if not resultado_persistencia["cambios"] else
        f"SQLITE: COMMIT OK (backup: {resultado_persistencia['backup']}; "
        f"data_version: {resultado_persistencia['data_version']})"
    )

    print(f"Índices consultados correctamente: {estados_indices['consultado']}")
    print(f"Días sin edición: {estados_indices['sin_edicion']}")
    print(f"Índices con error: {estados_indices['error']}")
    print(f"Índices reutilizados localmente: {indices_reutilizados}")
    print(f"Índices consultados por HTTP: {indices_consultados_http}")
    print(f"Índices resueltos por API: {indices_resueltos_api}")
    print(f"Índices resueltos por fallback HTML: {indices_resueltos_fallback}")

    if not enlaces_oposiciones and not indices_reutilizados:
        if not lista_diccionario_errores:
            if fecha_fin == fecha_inicio:
                print(
                    f"\n\n{Fore.RED}❌ El {Fore.WHITE}{fecha_inicio} {Fore.RED}no se ha publicado ningún proceso selectivo\n"
                )
            else:
                print(
                    f"\n\n{Fore.RED}❌ Entre el {Fore.WHITE}{fecha_inicio}{Fore.RED} y {Fore.WHITE}{fecha_fin}{Fore.RED} no se ha publicado ningún proceso selectivo\n"
                )
            if modo_programatico:
                raise RuntimeError("El BOE no publicó procesos selectivos en el periodo solicitado")
            sys.exit(0)
        print(f"\n{Fore.RED}❌ No se pudo consultar el BOE para el periodo seleccionado.{Fore.RESET}")
        if modo_programatico:
            raise RuntimeError("No se pudo consultar el BOE para el periodo solicitado")
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
        publicaciones_analizadas=(
            publicaciones_analizadas + publicaciones_reutilizadas
        ),
        publicaciones_fallidas=len(publicaciones_fallidas),
    )

    # Mostramos en un mapa web los municipios encontrados en la búsqueda
    if generar_mapa and not df_filtrado_por_patron.empty:
        generar_mapa_municipios(df_filtrado_por_patron)

    print(f"Publicaciones descargadas: {publicaciones_descargadas}")
    print(
        "Publicaciones reutilizadas localmente: "
        f"{publicaciones_reutilizadas}"
    )

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
    return {"persistencia": resultado_persistencia, "estados_indices": estados_indices,
            "indices_consultados_http": indices_consultados_http,
            "indices_reutilizados": indices_reutilizados,
            "publicaciones_analizadas": publicaciones_analizadas,
            "publicaciones_descargadas": publicaciones_descargadas}


def main():
    if "--reprocesar-legacy" in sys.argv[1:]:
        _main_reprocesamiento_legacy(sys.argv[1:])
        return
    try:
        _ejecutar_aplicacion()
    except base_datos.EspejoSQLiteError as error:
        print(f"\n{Fore.RED}❌ {error}{Fore.RESET}")
        sys.exit(1)


def _main_reprocesamiento_legacy(argumentos):
    from reprocesamiento_legacy import (
        aplicar_lote,
        asignar_acciones,
        calcular_integridad_excel,
        crear_backup_verificado,
        ejecutar_dry_run,
        guardar_informe_auditoria,
        imprimir_informe,
    )

    parser = argparse.ArgumentParser(description="Reprocesamiento controlado legacy")
    parser.add_argument("--reprocesar-legacy", action="store_true")
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--dry-run", action="store_true")
    modo.add_argument("--aplicar", action="store_true")
    parser.add_argument("--limite", type=int)
    parser.add_argument("--desde")
    parser.add_argument("--hasta")
    parser.add_argument("--publicacion")
    opciones = parser.parse_args(argumentos)
    if not opciones.dry_run and not opciones.aplicar:
        parser.error("debe indicar --dry-run o --aplicar")
    if opciones.aplicar and opciones.limite is None:
        parser.error("--aplicar exige --limite")
    if opciones.aplicar and opciones.limite > 25:
        parser.error("--aplicar admite como máximo --limite 25")
    try:
        if opciones.aplicar:
            with preparar_archivo_datos.bloqueo_excel():
                (
                    detalles,
                    resumen,
                    ruta_informe,
                    integridad_antes,
                    integridad_despues,
                    datos_escritura,
                ) = (
                    _ejecutar_aplicacion_legacy(
                        opciones,
                        calcular_integridad_excel,
                        ejecutar_dry_run,
                        guardar_informe_auditoria,
                        asignar_acciones,
                        crear_backup_verificado,
                        aplicar_lote,
                    )
                )
        else:
            integridad_antes = calcular_integridad_excel()
            detalles, resumen = ejecutar_dry_run(
                desde=opciones.desde,
                hasta=opciones.hasta,
                publicacion_id=opciones.publicacion,
                limite=opciones.limite,
            )
            integridad_despues = calcular_integridad_excel()
            ruta_informe = guardar_informe_auditoria(
                detalles,
                resumen,
                _filtros_reprocesamiento(opciones),
                integridad_antes,
                integridad_despues,
            )
    except (FileNotFoundError, ValueError) as error:
        parser.error(str(error))
    except preparar_archivo_datos.ExcelBloqueadoError as error:
        parser.error(str(error))
    except RuntimeError as error:
        print(f"{Fore.RED}❌ {error}{Fore.RESET}")
        raise SystemExit(1) from error
    imprimir_informe(
        detalles,
        resumen,
        modo="aplicar" if opciones.aplicar else "dry-run",
        datos_escritura=datos_escritura if opciones.aplicar else None,
    )
    if opciones.dry_run and integridad_antes != integridad_despues:
        print(f"{Fore.RED}⚠ El Excel cambió durante el dry-run.{Fore.RESET}")
    print(f"\nInforme de auditoría:\n{ruta_informe}")


def _filtros_reprocesamiento(opciones):
    return {
        "desde": opciones.desde,
        "hasta": opciones.hasta,
        "publicacion": opciones.publicacion,
        "limite": opciones.limite,
    }


def _ejecutar_aplicacion_legacy(
    opciones,
    calcular_integridad_excel,
    ejecutar_dry_run,
    guardar_informe_auditoria,
    asignar_acciones,
    crear_backup_verificado,
    aplicar_lote,
):
    integridad_antes = calcular_integridad_excel()
    detalles, resumen = ejecutar_dry_run(
        desde=opciones.desde,
        hasta=opciones.hasta,
        publicacion_id=opciones.publicacion,
        limite=opciones.limite,
    )
    integridad_tras_comparacion = calcular_integridad_excel()
    escritura_autorizada = asignar_acciones(detalles)
    datos_escritura = {
        "escritura_autorizada": escritura_autorizada,
        "backup": None,
        "backup_sha256": None,
        "filas_anadidas_realmente": 0,
        "filas_actualizadas_trazabilidad": 0,
        "publicaciones_actualizadas": 0,
        "escritura_completada": False,
    }
    ruta_informe = guardar_informe_auditoria(
        detalles,
        resumen,
        _filtros_reprocesamiento(opciones),
        integridad_antes,
        integridad_tras_comparacion,
        modo="aplicar",
        datos_escritura=datos_escritura,
    )
    if not escritura_autorizada:
        print(
            f"{Fore.RED}❌ Lote abortado: contiene clasificaciones no escribibles."
            f"{Fore.RESET}"
        )
        print(f"{Fore.RED}ESCRITURA NO REALIZADA{Fore.RESET}")
        raise SystemExit(1)

    escritura_iniciada = False
    try:
        backup, integridad_backup = crear_backup_verificado()
        datos_escritura.update(
            backup=str(backup), backup_sha256=integridad_backup["sha256"]
        )
        escritura_iniciada = True
        metricas = aplicar_lote(detalles)
        datos_escritura.update(metricas)
        datos_escritura["escritura_completada"] = True
        datos_escritura["verificacion_posterior"] = True
    except BaseException as error:
        if not escritura_iniciada:
            print(f"{Fore.RED}ESCRITURA NO REALIZADA{Fore.RESET}")
        datos_escritura["error_escritura"] = str(error)
        integridad_despues = calcular_integridad_excel()
        guardar_informe_auditoria(
            detalles,
            resumen,
            _filtros_reprocesamiento(opciones),
            integridad_antes,
            integridad_despues,
            modo="aplicar",
            datos_escritura=datos_escritura,
            destino=ruta_informe,
        )
        raise

    integridad_despues = calcular_integridad_excel()
    guardar_informe_auditoria(
        detalles,
        resumen,
        _filtros_reprocesamiento(opciones),
        integridad_antes,
        integridad_despues,
        modo="aplicar",
        datos_escritura=datos_escritura,
        destino=ruta_informe,
    )
    return (
        detalles,
        resumen,
        ruta_informe,
        integridad_antes,
        integridad_despues,
        datos_escritura,
    )


if __name__ == "__main__":
    main()
