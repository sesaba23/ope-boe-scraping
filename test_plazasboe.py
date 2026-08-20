import importlib
import runpy
import sys

import pandas as pd
import pytest
import requests

import coincidencias
import entradas_datos
import impresiones
import mapa_plazas
import preparar_archivo_datos


def test_importar_plazasboe_no_ejecuta_el_flujo_principal(monkeypatch):
    def ejecucion_inesperada(*args, **kwargs):
        raise AssertionError("El flujo principal se ejecutó durante la importación")

    monkeypatch.setattr(
        preparar_archivo_datos, "preparar_excel_y_dataframes", ejecucion_inesperada
    )
    monkeypatch.setattr(requests, "get", ejecucion_inesperada)
    monkeypatch.setattr("builtins.input", ejecucion_inesperada)
    sys.modules.pop("plazasboe", None)

    modulo = importlib.import_module("plazasboe")

    assert callable(modulo.main)


def test_no_reutiliza_respuesta_anterior_si_un_enlace_agota_reintentos(monkeypatch):
    enlace_correcto = "https://www.boe.es/diario_boe/txt.php?id=uno"
    enlace_fallido = "https://www.boe.es/diario_boe/txt.php?id=dos"
    html_indice = f"""
        <a href="/diario_boe/txt.php?id=uno">Primero</a>
        <a href="/diario_boe/txt.php?id=dos">Segundo</a>
    """
    html_documento = """
        <div class="documento-tit">Documento correcto</div>
        <div class="metadatos">1 de enero de 2025</div>
        <div id="textoxslt">Contenido correcto</div>
    """

    class Respuesta:
        def __init__(self, contenido):
            self.content = contenido.encode()

        def raise_for_status(self):
            pass

    def obtener_url(url, timeout):
        if "index.php" in url:
            return Respuesta(html_indice)
        if url == enlace_correcto:
            return Respuesta(html_documento)
        if url == enlace_fallido:
            raise requests.exceptions.Timeout
        raise AssertionError(f"URL inesperada: {url}")

    columnas = [
        "Num_plazas",
        "Puesto",
        "Administración",
        "Escala",
        "Subescala",
        "Clase",
        "Sistema",
        "Turno",
        "Fecha_boe",
        "Publicación",
        "Enlace",
    ]
    oposiciones = pd.DataFrame(columns=columnas)
    busquedas = pd.DataFrame({"Código": []})
    log_errores = pd.DataFrame(columns=["Fecha", "Tipo de error", "Enlace Web"])
    enlaces_analizados = []
    codigos_guardados = []

    def combinar_dataframes(
        diccionario_puestos,
        diccionario_busquedas,
        df_opo_guardadas,
        df_busquedas,
    ):
        codigos_guardados.extend(diccionario_busquedas["Código"])
        return oposiciones, busquedas

    monkeypatch.setattr(sys, "argv", ["plazasboe.py"])
    monkeypatch.setattr(
        entradas_datos,
        "solicitar_fechas_y_validar",
        lambda *args: ("", "01/01/2025", "01/01/2025", ["2025/01/01"]),
    )
    monkeypatch.setattr(
        preparar_archivo_datos,
        "preparar_excel_y_dataframes",
        lambda: {
            "Búsquedas": busquedas,
            "Oposiciones": oposiciones,
            "Log-errores": log_errores,
        },
    )
    monkeypatch.setattr(
        preparar_archivo_datos,
        "combinar_dataframes",
        combinar_dataframes,
    )
    monkeypatch.setattr(preparar_archivo_datos, "guardar_excel", lambda *args: None)
    monkeypatch.setattr(
        preparar_archivo_datos,
        "prepara_data_frame_mostrar_resultados",
        lambda *args: oposiciones,
    )
    monkeypatch.setattr(requests, "get", obtener_url)
    monkeypatch.setattr("time.sleep", lambda *args: None)
    monkeypatch.setattr(
        coincidencias,
        "buscar_coincidencias_local",
        lambda texto, contenido, titulo, fecha, enlace: enlaces_analizados.append(
            enlace
        ),
    )
    monkeypatch.setattr(coincidencias, "buscar_coincidencias_estado", lambda *args: None)
    monkeypatch.setattr(impresiones, "imprimir_diccionario_puestos", lambda *args, **kwargs: None)
    monkeypatch.setattr(mapa_plazas, "generar_mapa_municipios", lambda *args: None)

    import plazasboe

    monkeypatch.setattr(
        plazasboe,
        "solicitar_fechas_y_validar",
        lambda *args: ("", "01/01/2025", "01/01/2025", ["2025/01/01"]),
    )
    plazasboe.main()

    assert enlaces_analizados == [enlace_correcto]
    assert codigos_guardados == [enlace_correcto]


def test_procesa_dias_posteriores_si_el_primero_no_tiene_publicaciones(monkeypatch):
    enlace_publicacion = "https://www.boe.es/diario_boe/txt.php?id=posterior"
    html_indice_vacio = "<html><body>Sin publicaciones</body></html>"
    html_indice_con_publicacion = (
        '<a href="/diario_boe/txt.php?id=posterior">Publicación</a>'
    )
    html_documento = """
        <div class="documento-tit">Documento posterior</div>
        <div class="metadatos">2 de enero de 2025</div>
        <div id="textoxslt">Contenido posterior</div>
    """

    class Respuesta:
        def __init__(self, contenido):
            self.content = contenido.encode()

        def raise_for_status(self):
            pass

    def obtener_url(url, timeout):
        if "2025/01/01" in url:
            return Respuesta(html_indice_vacio)
        if "2025/01/02" in url:
            return Respuesta(html_indice_con_publicacion)
        if url == enlace_publicacion:
            return Respuesta(html_documento)
        raise AssertionError(f"URL inesperada: {url}")

    columnas = [
        "Num_plazas",
        "Puesto",
        "Administración",
        "Escala",
        "Subescala",
        "Clase",
        "Sistema",
        "Turno",
        "Fecha_boe",
        "Publicación",
        "Enlace",
    ]
    oposiciones = pd.DataFrame(columns=columnas)
    busquedas = pd.DataFrame({"Código": []})
    log_errores = pd.DataFrame(columns=["Fecha", "Tipo de error", "Enlace Web"])
    enlaces_analizados = []

    monkeypatch.setattr(sys, "argv", ["plazasboe.py"])
    monkeypatch.setattr(
        entradas_datos,
        "solicitar_fechas_y_validar",
        lambda *args: (
            "",
            "01/01/2025",
            "02/01/2025",
            ["2025/01/01", "2025/01/02"],
        ),
    )
    monkeypatch.setattr(
        preparar_archivo_datos,
        "preparar_excel_y_dataframes",
        lambda: {
            "Búsquedas": busquedas,
            "Oposiciones": oposiciones,
            "Log-errores": log_errores,
        },
    )
    monkeypatch.setattr(
        preparar_archivo_datos,
        "combinar_dataframes",
        lambda *args: (oposiciones, busquedas),
    )
    monkeypatch.setattr(preparar_archivo_datos, "guardar_excel", lambda *args: None)
    monkeypatch.setattr(
        preparar_archivo_datos,
        "prepara_data_frame_mostrar_resultados",
        lambda *args: oposiciones,
    )
    monkeypatch.setattr(requests, "get", obtener_url)
    monkeypatch.setattr(
        coincidencias,
        "buscar_coincidencias_local",
        lambda texto, contenido, titulo, fecha, enlace: enlaces_analizados.append(
            enlace
        ),
    )
    monkeypatch.setattr(coincidencias, "buscar_coincidencias_estado", lambda *args: None)
    monkeypatch.setattr(impresiones, "imprimir_diccionario_puestos", lambda *args, **kwargs: None)
    monkeypatch.setattr(mapa_plazas, "generar_mapa_municipios", lambda *args: None)

    runpy.run_path("plazasboe.py", run_name="__main__")

    assert enlaces_analizados == [enlace_publicacion]


def test_respuesta_http_no_exitosa_no_se_analiza_como_html(monkeypatch):
    comprobaciones_estado = []
    errores_guardados = []

    class RespuestaError:
        content = b'<a href="/diario_boe/txt.php?id=no-valido">No valido</a>'

        def raise_for_status(self):
            comprobaciones_estado.append(True)
            raise requests.exceptions.HTTPError("500 Server Error")

    _configurar_fallo_indice(
        monkeypatch,
        lambda *args, **kwargs: RespuestaError(),
        errores_guardados,
    )

    with pytest.raises(SystemExit):
        runpy.run_path("plazasboe.py", run_name="__main__")

    assert len(comprobaciones_estado) == 3
    assert errores_guardados


def test_fallo_total_del_indice_no_se_informa_como_ausencia_de_publicaciones(
    monkeypatch, capsys
):
    errores_guardados = []

    def obtener_url(*args, **kwargs):
        raise requests.exceptions.ConnectionError("BOE no disponible")

    _configurar_fallo_indice(monkeypatch, obtener_url, errores_guardados)

    with pytest.raises(SystemExit):
        runpy.run_path("plazasboe.py", run_name="__main__")

    salida = capsys.readouterr().out
    assert "No se pudo consultar el BOE" in salida
    assert "no se ha publicado ningún proceso selectivo" not in salida
    assert errores_guardados


def test_error_de_programacion_en_peticion_no_se_oculta(monkeypatch):
    errores_guardados = []

    def obtener_url(*args, **kwargs):
        raise KeyError("error de programación simulado")

    _configurar_fallo_indice(monkeypatch, obtener_url, errores_guardados)

    with pytest.raises(KeyError, match="error de programación simulado"):
        runpy.run_path("plazasboe.py", run_name="__main__")

    assert errores_guardados == []


def test_codigo_del_historico_se_reconoce_como_procesado(monkeypatch):
    enlace = "https://www.boe.es/diario_boe/txt.php?id=repetido"

    enlaces_analizados, codigos_guardados = _ejecutar_con_codigo_repetido(
        monkeypatch, enlace, [enlace]
    )

    assert enlaces_analizados == []
    assert codigos_guardados == []


def test_codigo_procesado_se_reconoce_durante_la_misma_ejecucion(monkeypatch):
    enlace = "https://www.boe.es/diario_boe/txt.php?id=repetido"

    enlaces_analizados, codigos_guardados = _ejecutar_con_codigo_repetido(
        monkeypatch, enlace, []
    )

    assert enlaces_analizados == [enlace]
    assert codigos_guardados == [enlace]


def _ejecutar_con_codigo_repetido(monkeypatch, enlace, historico):
    html_indice = """
        <a href="/diario_boe/txt.php?id=repetido">Primero</a>
        <a href="/diario_boe/txt.php?id=repetido">Duplicado</a>
    """
    html_documento = """
        <div class="documento-tit">Documento correcto</div>
        <div class="metadatos">1 de enero de 2025</div>
        <div id="textoxslt">Contenido correcto</div>
    """

    class Respuesta:
        def __init__(self, contenido):
            self.content = contenido.encode()

        def raise_for_status(self):
            pass

    def obtener_url(url, timeout):
        if "index.php" in url:
            return Respuesta(html_indice)
        if url == enlace:
            return Respuesta(html_documento)
        raise AssertionError(f"URL inesperada: {url}")

    columnas = [
        "Num_plazas",
        "Puesto",
        "Administración",
        "Escala",
        "Subescala",
        "Clase",
        "Sistema",
        "Turno",
        "Fecha_boe",
        "Publicación",
        "Enlace",
    ]
    oposiciones = pd.DataFrame(columns=columnas)
    busquedas = pd.DataFrame({"Código": historico})
    log_errores = pd.DataFrame(columns=["Fecha", "Tipo de error", "Enlace Web"])
    enlaces_analizados = []
    codigos_guardados = []

    def combinar_dataframes(
        diccionario_puestos,
        diccionario_busquedas,
        df_opo_guardadas,
        df_busquedas,
    ):
        codigos_guardados.extend(diccionario_busquedas["Código"])
        return oposiciones, busquedas

    monkeypatch.setattr(sys, "argv", ["plazasboe.py"])
    monkeypatch.setattr(
        entradas_datos,
        "solicitar_fechas_y_validar",
        lambda *args: ("", "01/01/2025", "01/01/2025", ["2025/01/01"]),
    )
    monkeypatch.setattr(
        preparar_archivo_datos,
        "preparar_excel_y_dataframes",
        lambda: {
            "Búsquedas": busquedas,
            "Oposiciones": oposiciones,
            "Log-errores": log_errores,
        },
    )
    monkeypatch.setattr(
        preparar_archivo_datos, "combinar_dataframes", combinar_dataframes
    )
    monkeypatch.setattr(preparar_archivo_datos, "guardar_excel", lambda *args: None)
    monkeypatch.setattr(
        preparar_archivo_datos,
        "prepara_data_frame_mostrar_resultados",
        lambda *args: oposiciones,
    )
    monkeypatch.setattr(requests, "get", obtener_url)
    monkeypatch.setattr(
        coincidencias,
        "buscar_coincidencias_local",
        lambda texto, contenido, titulo, fecha, url: enlaces_analizados.append(url),
    )
    monkeypatch.setattr(coincidencias, "buscar_coincidencias_estado", lambda *args: None)
    monkeypatch.setattr(impresiones, "imprimir_diccionario_puestos", lambda *args, **kwargs: None)
    monkeypatch.setattr(mapa_plazas, "generar_mapa_municipios", lambda *args: None)

    runpy.run_path("plazasboe.py", run_name="__main__")

    return enlaces_analizados, codigos_guardados


def _configurar_fallo_indice(monkeypatch, obtener_url, errores_guardados):
    columnas = [
        "Num_plazas",
        "Puesto",
        "Administración",
        "Escala",
        "Subescala",
        "Clase",
        "Sistema",
        "Turno",
        "Fecha_boe",
        "Publicación",
        "Enlace",
    ]
    oposiciones = pd.DataFrame(columns=columnas)
    busquedas = pd.DataFrame({"Código": []})
    log_errores = pd.DataFrame(columns=["Fecha", "Tipo de error", "Enlace Web"])

    def guardar_excel(df_combinado, df_busquedas_combinado, df_log_errores):
        errores_guardados.extend(df_log_errores.to_dict(orient="records"))

    monkeypatch.setattr(sys, "argv", ["plazasboe.py"])
    monkeypatch.setattr(
        entradas_datos,
        "solicitar_fechas_y_validar",
        lambda *args: ("", "01/01/2025", "01/01/2025", ["2025/01/01"]),
    )
    monkeypatch.setattr(
        preparar_archivo_datos,
        "preparar_excel_y_dataframes",
        lambda: {
            "Búsquedas": busquedas,
            "Oposiciones": oposiciones,
            "Log-errores": log_errores,
        },
    )
    monkeypatch.setattr(
        preparar_archivo_datos,
        "combinar_dataframes",
        lambda *args: (oposiciones, busquedas),
    )
    monkeypatch.setattr(preparar_archivo_datos, "guardar_excel", guardar_excel)
    monkeypatch.setattr(requests, "get", obtener_url)
    monkeypatch.setattr("time.sleep", lambda *args: None)
