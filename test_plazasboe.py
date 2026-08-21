import importlib
import runpy
import sys

import pandas as pd
import pytest
import requests
import bs4
from bs4 import ParserRejectedMarkup

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


def test_404_en_indice_de_un_unico_dia_es_dia_sin_edicion(monkeypatch, capsys):
    llamadas = []

    def obtener_url(url, timeout):
        llamadas.append(url)
        return _RespuestaHTTP("", 404)

    _configurar_consulta_boe(
        monkeypatch, obtener_url, ["2025/01/05"], "05/01/2025", "05/01/2025"
    )

    with pytest.raises(SystemExit) as salida:
        runpy.run_path("plazasboe.py", run_name="__main__")

    assert salida.value.code == 0
    assert len(llamadas) == 1
    assert "no se ha publicado ningún proceso selectivo" in capsys.readouterr().out


def test_rango_valido_404_valido_continua_hasta_el_final(monkeypatch):
    enlace = "https://www.boe.es/diario_boe/txt.php?id=posterior-al-404"
    llamadas = []

    def obtener_url(url, timeout):
        llamadas.append(url)
        if "2025/01/01" in url:
            return _RespuestaHTTP("<html>Sin publicaciones</html>")
        if "2025/01/02" in url:
            return _RespuestaHTTP("", 404)
        if "2025/01/03" in url:
            return _RespuestaHTTP(
                '<a href="/diario_boe/txt.php?id=posterior-al-404">Publicación</a>'
            )
        if url == enlace:
            return _RespuestaHTTP(
                '<div class="documento-tit">Documento</div>'
                '<div class="metadatos">3 de enero de 2025</div>'
                '<div id="textoxslt">Contenido</div>'
            )
        raise AssertionError(f"URL inesperada: {url}")

    errores_guardados = _configurar_consulta_boe(
        monkeypatch,
        obtener_url,
        ["2025/01/01", "2025/01/02", "2025/01/03"],
        "01/01/2025",
        "03/01/2025",
    )

    runpy.run_path("plazasboe.py", run_name="__main__")

    assert sum("2025/01/02" in url for url in llamadas) == 1
    assert any("2025/01/03" in url for url in llamadas)
    assert enlace in llamadas
    assert errores_guardados == []


@pytest.mark.parametrize("estado", [400, 404])
def test_400_y_404_al_descargar_publicacion_siguen_siendo_error(
    monkeypatch, estado
):
    enlace = "https://www.boe.es/diario_boe/txt.php?id=documento-inexistente"
    llamadas_publicacion = []

    def obtener_url(url, timeout):
        if "index.php" in url:
            return _RespuestaHTTP(
                '<a href="/diario_boe/txt.php?id=documento-inexistente">Publicación</a>'
            )
        if url == enlace:
            llamadas_publicacion.append(url)
            return _RespuestaHTTP("", estado)
        raise AssertionError(f"URL inesperada: {url}")

    errores_guardados = _configurar_consulta_boe(
        monkeypatch, obtener_url, ["2025/01/01"], "01/01/2025", "01/01/2025"
    )

    runpy.run_path("plazasboe.py", run_name="__main__")

    assert len(llamadas_publicacion) == 3
    assert [error["Enlace Web"] for error in errores_guardados] == [enlace]


def test_dias_validos_sin_publicaciones_y_404_terminan_sin_publicaciones(
    monkeypatch, capsys
):
    llamadas = []

    def obtener_url(url, timeout):
        llamadas.append(url)
        if "2025/01/02" in url:
            return _RespuestaHTTP("", 404)
        return _RespuestaHTTP("<html>Sin publicaciones de la sección</html>")

    _configurar_consulta_boe(
        monkeypatch,
        obtener_url,
        ["2025/01/01", "2025/01/02", "2025/01/03"],
        "01/01/2025",
        "03/01/2025",
    )

    with pytest.raises(SystemExit) as salida:
        runpy.run_path("plazasboe.py", run_name="__main__")

    texto_salida = capsys.readouterr().out
    assert salida.value.code == 0
    assert len(llamadas) == 3
    assert "no se ha publicado ningún proceso selectivo" in texto_salida
    assert "No se pudo consultar el BOE" not in texto_salida


def test_400_en_filtro_y_indice_general_sin_2b_es_dia_sin_publicaciones(
    monkeypatch, capsys
):
    llamadas = []
    html_indice_general = """
        <a href="index.php?s=1">I. Disposiciones generales</a>
        <h3>I. Disposiciones generales</h3>
    """

    def obtener_url(url, timeout):
        llamadas.append(url)
        if url.endswith("?s=2B"):
            return _RespuestaHTTP("", 400)
        return _RespuestaHTTP(html_indice_general)

    _configurar_consulta_boe(
        monkeypatch, obtener_url, ["2026/08/09"], "09/08/2026", "09/08/2026"
    )

    with pytest.raises(SystemExit) as salida:
        runpy.run_path("plazasboe.py", run_name="__main__")

    assert salida.value.code == 0
    assert llamadas == [
        "https://www.boe.es/boe/dias/2026/08/09/index.php?s=2B",
        "https://www.boe.es/boe/dias/2026/08/09/index.php",
    ]
    assert "no se ha publicado ningún proceso selectivo" in capsys.readouterr().out


def test_400_en_filtro_recupera_2b_desde_el_indice_general(monkeypatch):
    enlaces = [
        "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-1",
        "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-2",
    ]
    publicaciones_consultadas = []
    html_indice_general = """
        <a href="index.php?s=1">I. Disposiciones generales</a>
        <a href="index.php?s=2B">II. B. Oposiciones y concursos</a>
        <h3>II. Autoridades y personal. - B. Oposiciones y concursos</h3>
        <a href="/diario_boe/txt.php?id=BOE-A-2026-1">Otros formatos</a>
        <a href="/diario_boe/txt.php?id=BOE-A-2026-2">Otros formatos</a>
        <h3>III. Otras disposiciones</h3>
        <a href="/diario_boe/txt.php?id=fuera-de-2b">Otros formatos</a>
    """

    def obtener_url(url, timeout):
        if url.endswith("?s=2B"):
            return _RespuestaHTTP("", 400)
        if url.endswith("index.php"):
            return _RespuestaHTTP(html_indice_general)
        if url in enlaces:
            publicaciones_consultadas.append(url)
            return _RespuestaHTTP(_html_publicacion_correcta())
        raise AssertionError(f"URL inesperada: {url}")

    errores_guardados = _configurar_consulta_boe(
        monkeypatch, obtener_url, ["2026/08/09"], "09/08/2026", "09/08/2026"
    )

    runpy.run_path("plazasboe.py", run_name="__main__")

    assert publicaciones_consultadas == enlaces
    assert errores_guardados == []


@pytest.mark.parametrize("estado_fallback", [400, 500])
def test_error_http_en_indice_general_del_fallback_se_registra(
    monkeypatch, estado_fallback
):
    llamadas = []

    def obtener_url(url, timeout):
        llamadas.append(url)
        if url.endswith("?s=2B"):
            return _RespuestaHTTP("", 400)
        return _RespuestaHTTP("", estado_fallback)

    errores_guardados = _configurar_consulta_boe(
        monkeypatch, obtener_url, ["2026/08/09"], "09/08/2026", "09/08/2026"
    )

    with pytest.raises(SystemExit) as salida:
        runpy.run_path("plazasboe.py", run_name="__main__")

    assert salida.value.code == 1
    assert len(llamadas) == 2
    assert errores_guardados[0]["Tipo de error"] == "Error al acceder"
    assert errores_guardados[0]["Enlace Web"].endswith("/index.php")


def test_fallback_con_estructura_no_reconocible_registra_error(monkeypatch):
    def obtener_url(url, timeout):
        if url.endswith("?s=2B"):
            return _RespuestaHTTP("", 400)
        return _RespuestaHTTP("<html><body>Contenido inesperado</body></html>")

    errores_guardados = _configurar_consulta_boe(
        monkeypatch, obtener_url, ["2026/08/09"], "09/08/2026", "09/08/2026"
    )

    with pytest.raises(SystemExit) as salida:
        runpy.run_path("plazasboe.py", run_name="__main__")

    assert salida.value.code == 1
    assert errores_guardados[0]["Tipo de error"] == "Error de estructura"


@pytest.mark.parametrize("estado", [429, 500])
def test_429_y_5xx_del_indice_filtrado_conservan_los_reintentos(
    monkeypatch, estado
):
    llamadas = []

    def obtener_url(url, timeout):
        llamadas.append(url)
        return _RespuestaHTTP("", estado)

    errores_guardados = _configurar_consulta_boe(
        monkeypatch, obtener_url, ["2026/08/08"], "08/08/2026", "08/08/2026"
    )

    with pytest.raises(SystemExit) as salida:
        runpy.run_path("plazasboe.py", run_name="__main__")

    assert salida.value.code == 1
    assert len(llamadas) == 3
    assert errores_guardados[0]["Tipo de error"] == "Error al acceder"


def test_fallback_no_duplica_publicaciones(monkeypatch):
    enlace = "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-repetida"
    publicaciones_consultadas = []
    html_indice_general = """
        <a href="index.php?s=2B">II. B. Oposiciones y concursos</a>
        <h3>II. Autoridades y personal. - B. Oposiciones y concursos</h3>
        <a href="/diario_boe/txt.php?id=BOE-A-2026-repetida">Otros formatos</a>
        <a href="/diario_boe/txt.php?id=BOE-A-2026-repetida">HTML repetido</a>
        <h3>III. Otras disposiciones</h3>
    """

    def obtener_url(url, timeout):
        if url.endswith("?s=2B"):
            return _RespuestaHTTP("", 400)
        if url.endswith("index.php"):
            return _RespuestaHTTP(html_indice_general)
        if url == enlace:
            publicaciones_consultadas.append(url)
            return _RespuestaHTTP(_html_publicacion_correcta())
        raise AssertionError(f"URL inesperada: {url}")

    _configurar_consulta_boe(
        monkeypatch, obtener_url, ["2026/08/09"], "09/08/2026", "09/08/2026"
    )

    runpy.run_path("plazasboe.py", run_name="__main__")

    assert publicaciones_consultadas == [enlace]


def test_error_de_programacion_en_peticion_no_se_oculta(monkeypatch):
    errores_guardados = []

    def obtener_url(*args, **kwargs):
        raise KeyError("error de programación simulado")

    _configurar_fallo_indice(monkeypatch, obtener_url, errores_guardados)

    with pytest.raises(KeyError, match="error de programación simulado"):
        runpy.run_path("plazasboe.py", run_name="__main__")

    assert errores_guardados == []


def test_publicacion_sin_contenido_principal_no_se_anade_al_historico(monkeypatch):
    enlace = "https://www.boe.es/diario_boe/txt.php?id=sin-contenido"
    html_indice = '<a href="/diario_boe/txt.php?id=sin-contenido">Publicación</a>'
    html_publicacion = (
        '<div class="documento-tit">Documento sin contenido</div>'
        '<div class="metadatos">9 de agosto de 2026</div>'
    )
    codigos_guardados = []

    def obtener_url(url, timeout):
        if "index.php" in url:
            return _RespuestaHTTP(html_indice)
        if url == enlace:
            return _RespuestaHTTP(html_publicacion)
        raise AssertionError(f"URL inesperada: {url}")

    errores_guardados = _configurar_consulta_boe(
        monkeypatch, obtener_url, ["2026/08/09"], "09/08/2026", "09/08/2026"
    )

    def combinar_dataframes(
        diccionario_puestos,
        diccionario_busquedas,
        df_opo_guardadas,
        df_busquedas,
    ):
        codigos_guardados.extend(diccionario_busquedas["Código"])
        return df_opo_guardadas, df_busquedas

    monkeypatch.setattr(
        preparar_archivo_datos, "combinar_dataframes", combinar_dataframes
    )

    runpy.run_path("plazasboe.py", run_name="__main__")

    assert codigos_guardados == []
    assert errores_guardados[0]["Tipo de error"] == "Error de estructura"
    assert errores_guardados[0]["Enlace Web"] == enlace


def test_flujo_principal_informa_cuantas_publicaciones_fallan(monkeypatch):
    enlace_correcto = "https://www.boe.es/diario_boe/txt.php?id=correcto"
    enlace_fallido = "https://www.boe.es/diario_boe/txt.php?id=fallido"
    html_indice = (
        '<a href="/diario_boe/txt.php?id=correcto">Correcta</a>'
        '<a href="/diario_boe/txt.php?id=fallido">Fallida</a>'
    )
    estado_final = {}

    def obtener_url(url, timeout):
        if "index.php" in url:
            return _RespuestaHTTP(html_indice)
        if url == enlace_correcto:
            return _RespuestaHTTP(_html_publicacion_correcta())
        if url == enlace_fallido:
            return _RespuestaHTTP("", 500)
        raise AssertionError(f"URL inesperada: {url}")

    _configurar_consulta_boe(
        monkeypatch, obtener_url, ["2026/08/09"], "09/08/2026", "09/08/2026"
    )
    monkeypatch.setattr(
        impresiones,
        "imprimir_diccionario_puestos",
        lambda *args, **kwargs: estado_final.update(kwargs),
    )

    runpy.run_path("plazasboe.py", run_name="__main__")

    assert estado_final["publicaciones_analizadas"] == 1
    assert estado_final["publicaciones_fallidas"] == 1


def test_indice_rechazado_por_parser_registra_error_y_continua(monkeypatch):
    llamadas = []
    beautiful_soup_real = bs4.BeautifulSoup

    def obtener_url(url, timeout):
        llamadas.append(url)
        if "2026/08/09" in url:
            return _RespuestaHTTP("indice rechazado")
        if "2026/08/10" in url:
            return _RespuestaHTTP("<html><body>Sin publicaciones</body></html>")
        raise AssertionError(f"URL inesperada: {url}")

    def crear_soup(contenido, parser):
        if contenido == b"indice rechazado":
            raise ParserRejectedMarkup("estructura no analizable")
        return beautiful_soup_real(contenido, parser)

    errores_guardados = _configurar_consulta_boe(
        monkeypatch,
        obtener_url,
        ["2026/08/09", "2026/08/10"],
        "09/08/2026",
        "10/08/2026",
    )
    monkeypatch.setattr(bs4, "BeautifulSoup", crear_soup)

    with pytest.raises(SystemExit) as salida:
        runpy.run_path("plazasboe.py", run_name="__main__")

    assert salida.value.code == 1
    assert len(llamadas) == 2
    assert errores_guardados[0]["Tipo de error"] == "Error de estructura"
    assert "2026/08/09" in errores_guardados[0]["Enlace Web"]


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


class _RespuestaHTTP:
    def __init__(self, contenido, estado=200):
        self.content = contenido.encode()
        self.status_code = estado

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(
                f"{self.status_code} HTTP Error", response=self
            )


def _html_publicacion_correcta():
    return (
        '<div class="documento-tit">Documento correcto</div>'
        '<div class="metadatos">9 de agosto de 2026</div>'
        '<div id="textoxslt">Contenido correcto</div>'
    )


def _configurar_consulta_boe(
    monkeypatch, obtener_url, lista_fechas, fecha_inicio, fecha_fin
):
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
    errores_guardados = []

    def guardar_excel(df_combinado, df_busquedas_combinado, df_log_errores):
        errores_guardados.extend(df_log_errores.to_dict(orient="records"))

    monkeypatch.setattr(sys, "argv", ["plazasboe.py"])
    monkeypatch.setattr(
        entradas_datos,
        "solicitar_fechas_y_validar",
        lambda *args: ("", fecha_inicio, fecha_fin, lista_fechas),
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
    monkeypatch.setattr(
        preparar_archivo_datos,
        "prepara_data_frame_mostrar_resultados",
        lambda *args: oposiciones,
    )
    monkeypatch.setattr(requests, "get", obtener_url)
    monkeypatch.setattr("time.sleep", lambda *args: None)
    monkeypatch.setattr(coincidencias, "buscar_coincidencias_local", lambda *args: None)
    monkeypatch.setattr(coincidencias, "buscar_coincidencias_estado", lambda *args: None)
    monkeypatch.setattr(
        impresiones, "imprimir_diccionario_puestos", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(mapa_plazas, "generar_mapa_municipios", lambda *args: None)
    return errores_guardados
