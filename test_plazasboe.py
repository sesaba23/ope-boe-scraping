import importlib
import runpy
import sys

import pandas as pd
import pytest
import requests
import bs4
from bs4 import ParserRejectedMarkup

import boe_api
import coincidencias
import entradas_datos
import impresiones
import mapa_plazas
import preparar_archivo_datos
import plazasboe
from publicaciones import debe_procesar_publicacion


@pytest.fixture(autouse=True)
def _mantener_html_en_pruebas_anteriores(monkeypatch):
    def api_no_disponible(*args, **kwargs):
        raise boe_api.ErrorAPIBOE("PRUEBA", "usar fallback HTML")

    monkeypatch.setattr(boe_api, "obtener_sumario_api", api_no_disponible)
    if "plazasboe" in sys.modules:
        monkeypatch.setattr(
            sys.modules["plazasboe"], "obtener_sumario_api", api_no_disponible
        )
    # Los fixtures históricos expresan su estado inicial como DataFrames. Este
    # adaptador conserva esa interfaz sin que producción vuelva a abrir Excel.
    monkeypatch.setattr(plazasboe.base_datos, "validar_base_principal", lambda *a, **k: {})
    monkeypatch.setattr(
        plazasboe.base_datos, "cargar_para_lectura",
        lambda *a, **k: preparar_archivo_datos.preparar_excel_y_dataframes(),
    )
    def persistir_simulado(_, lote, *args, **kwargs):
        preparar_archivo_datos.guardar_excel(
            lote["Oposiciones"], lote["Búsquedas"], lote["Log-errores"],
            lote["Publicaciones"], lote["Cobertura"],
        )
        return {"cambios": False, "backup": None, "data_version": 1}
    monkeypatch.setattr(plazasboe.base_datos, "persistir_lote_principal", persistir_simulado)


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


def test_solicita_fechas_antes_de_preparar_excel(monkeypatch):
    llamadas = []

    class DetenerFlujo(Exception):
        pass

    def solicitar_fechas(*args):
        llamadas.append("solicitar_fechas")
        return "", "01/01/2025", "01/01/2025", ["2025/01/01"]

    def preparar_excel():
        llamadas.append("preparar_excel")
        raise DetenerFlujo

    monkeypatch.setattr(plazasboe, "solicitar_fechas_y_validar", solicitar_fechas)
    monkeypatch.setattr(
        plazasboe.preparar_archivo_datos,
        "preparar_excel_y_dataframes",
        preparar_excel,
    )

    with pytest.raises(DetenerFlujo):
        plazasboe._ejecutar_aplicacion()

    assert llamadas == ["solicitar_fechas", "preparar_excel"]


def test_cancelar_fechas_no_prepara_excel(monkeypatch):
    def cancelar_fechas(*args):
        raise SystemExit(0)

    def preparar_excel():
        raise AssertionError("No debe abrirse el Excel tras cancelar las fechas")

    monkeypatch.setattr(plazasboe, "solicitar_fechas_y_validar", cancelar_fechas)
    monkeypatch.setattr(
        plazasboe.preparar_archivo_datos,
        "preparar_excel_y_dataframes",
        preparar_excel,
    )

    with pytest.raises(SystemExit):
        plazasboe._ejecutar_aplicacion()


def test_main_no_usa_bloqueo_excel(monkeypatch):
    class ContextoBloqueado:
        def __enter__(self):
            raise preparar_archivo_datos.ExcelBloqueadoError(
                "Ya hay otra ejecución trabajando con 'BOE-oposiciones.xlsx'."
            )

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        preparar_archivo_datos, "bloqueo_excel", lambda: ContextoBloqueado()
    )

    llamadas = []
    monkeypatch.setattr(plazasboe, "_ejecutar_aplicacion", lambda: llamadas.append(True))
    plazasboe.main()
    assert llamadas == [True]


def test_opcion_sqlite_espejo_es_explicita_y_no_forma_parte_del_texto(monkeypatch):
    llamadas = []

    class Bloqueo:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(sys, "argv", ["plazasboe.py", "--sqlite-espejo", "auxiliar"])
    monkeypatch.setattr(preparar_archivo_datos, "bloqueo_excel", lambda: Bloqueo())
    monkeypatch.setattr(plazasboe, "_ejecutar_aplicacion", lambda **kw: llamadas.append((kw, sys.argv[:])))
    plazasboe.main()
    assert llamadas == [({}, ["plazasboe.py", "auxiliar"])]


def test_flags_sqlite_se_combinan_y_no_forman_parte_del_texto(monkeypatch):
    llamadas = []

    class Bloqueo:
        def __enter__(self): return self
        def __exit__(self, *args): return False

    monkeypatch.setattr(sys, "argv", ["plazasboe.py", "--sqlite-espejo", "--sqlite-lectura", "auxiliar"])
    monkeypatch.setattr(preparar_archivo_datos, "bloqueo_excel", lambda: Bloqueo())
    monkeypatch.setattr(plazasboe, "_ejecutar_aplicacion", lambda **kw: llamadas.append((kw, sys.argv[:])))
    plazasboe.main()
    assert llamadas == [({}, ["plazasboe.py", "auxiliar"])]


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
    cobertura_guardada = []
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
        monkeypatch,
        obtener_url,
        ["2026/08/09"],
        "09/08/2026",
        "09/08/2026",
        cobertura_guardada=cobertura_guardada,
    )

    with pytest.raises(SystemExit) as salida:
        runpy.run_path("plazasboe.py", run_name="__main__")

    assert salida.value.code == 0
    assert llamadas == [
        "https://www.boe.es/boe/dias/2026/08/09/index.php?s=2B",
        "https://www.boe.es/boe/dias/2026/08/09/index.php",
    ]
    assert "no se ha publicado ningún proceso selectivo" in capsys.readouterr().out
    assert cobertura_guardada[-1].iloc[0]["Estado"] == "consultado"
    assert cobertura_guardada[-1].iloc[0]["Numero_publicaciones"] == 0


def test_400_en_filtro_recupera_2b_desde_el_indice_general(monkeypatch):
    enlaces = [
        "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-1",
        "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-2",
    ]
    publicaciones_consultadas = []
    cobertura_guardada = []
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
        monkeypatch,
        obtener_url,
        ["2026/08/09"],
        "09/08/2026",
        "09/08/2026",
        cobertura_guardada=cobertura_guardada,
    )

    runpy.run_path("plazasboe.py", run_name="__main__")

    assert publicaciones_consultadas == enlaces
    assert errores_guardados == []
    assert cobertura_guardada[-1].iloc[0]["Estado"] == "consultado"
    assert cobertura_guardada[-1].iloc[0]["Numero_publicaciones"] == 2


@pytest.mark.parametrize("estado_fallback", [400, 500])
def test_error_http_en_indice_general_del_fallback_se_registra(
    monkeypatch, estado_fallback
):
    llamadas = []
    cobertura_guardada = []

    def obtener_url(url, timeout):
        llamadas.append(url)
        if url.endswith("?s=2B"):
            return _RespuestaHTTP("", 400)
        return _RespuestaHTTP("", estado_fallback)

    errores_guardados = _configurar_consulta_boe(
        monkeypatch,
        obtener_url,
        ["2026/08/09"],
        "09/08/2026",
        "09/08/2026",
        cobertura_guardada=cobertura_guardada,
    )

    with pytest.raises(SystemExit) as salida:
        runpy.run_path("plazasboe.py", run_name="__main__")

    assert salida.value.code == 1
    assert len(llamadas) == 2
    assert errores_guardados[0]["Tipo de error"] == "Error al acceder"
    assert errores_guardados[0]["Enlace Web"].endswith("/index.php")
    assert cobertura_guardada[-1].iloc[0]["Estado"] == "error"


def test_fallback_con_estructura_no_reconocible_registra_error(monkeypatch):
    cobertura_guardada = []
    def obtener_url(url, timeout):
        if url.endswith("?s=2B"):
            return _RespuestaHTTP("", 400)
        return _RespuestaHTTP("<html><body>Contenido inesperado</body></html>")

    errores_guardados = _configurar_consulta_boe(
        monkeypatch,
        obtener_url,
        ["2026/08/09"],
        "09/08/2026",
        "09/08/2026",
        cobertura_guardada=cobertura_guardada,
    )

    with pytest.raises(SystemExit) as salida:
        runpy.run_path("plazasboe.py", run_name="__main__")

    assert salida.value.code == 1
    assert errores_guardados[0]["Tipo de error"] == "Error de estructura"
    assert cobertura_guardada[-1].iloc[0]["Estado"] == "error"


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
    cobertura_guardada = []
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
        monkeypatch,
        obtener_url,
        ["2026/08/09"],
        "09/08/2026",
        "09/08/2026",
        cobertura_guardada=cobertura_guardada,
    )

    runpy.run_path("plazasboe.py", run_name="__main__")

    assert publicaciones_consultadas == [enlace]
    assert cobertura_guardada[-1].iloc[0]["Numero_publicaciones"] == 1


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
    cobertura_guardada = []
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
        cobertura_guardada=cobertura_guardada,
    )
    monkeypatch.setattr(bs4, "BeautifulSoup", crear_soup)

    with pytest.raises(SystemExit) as salida:
        runpy.run_path("plazasboe.py", run_name="__main__")

    assert salida.value.code == 1
    assert len(llamadas) == 2
    assert errores_guardados[0]["Tipo de error"] == "Error de estructura"
    assert "2026/08/09" in errores_guardados[0]["Enlace Web"]
    assert cobertura_guardada[-1]["Estado"].tolist() == ["error", "consultado"]


@pytest.mark.parametrize(
    ("resultados", "estado", "numero"),
    [
        (
            [
                {"Num_plazas": 2, "Puesto": "Ingeniero", "Administración": "Entidad"},
                {"Num_plazas": 1, "Puesto": "Arquitecto", "Administración": "Entidad"},
            ],
            "con_coincidencias",
            2,
        ),
        (None, "sin_coincidencias", 0),
    ],
)
def test_analisis_correcto_registra_publicacion(
    monkeypatch, resultados, estado, numero
):
    enlace = "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-10463"
    html_indice = '<a href="/diario_boe/txt.php?id=BOE-A-2026-10463">Publicación</a>'
    publicaciones_guardadas = []

    def obtener_url(url, timeout):
        if "index.php" in url:
            return _RespuestaHTTP(html_indice)
        if url == enlace:
            return _RespuestaHTTP(_html_publicacion_correcta())
        raise AssertionError(f"URL inesperada: {url}")

    _configurar_consulta_boe(
        monkeypatch,
        obtener_url,
        ["2026/08/09"],
        "09/08/2026",
        "09/08/2026",
        publicaciones_guardadas,
    )
    monkeypatch.setattr(
        coincidencias, "buscar_coincidencias_local", lambda *args: resultados
    )

    runpy.run_path("plazasboe.py", run_name="__main__")

    publicacion = publicaciones_guardadas[-1].iloc[0]
    assert publicacion["Publicacion_ID"] == "BOE-A-2026-10463"
    assert publicacion["Estado_analisis"] == estado
    assert publicacion["Coincidencias"] == numero


def test_publicacion_con_fallo_no_se_registra(monkeypatch):
    enlace = "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-10463"
    html_indice = '<a href="/diario_boe/txt.php?id=BOE-A-2026-10463">Publicación</a>'
    publicaciones_guardadas = []

    def obtener_url(url, timeout):
        if "index.php" in url:
            return _RespuestaHTTP(html_indice)
        if url == enlace:
            return _RespuestaHTTP("", 500)
        raise AssertionError(f"URL inesperada: {url}")

    _configurar_consulta_boe(
        monkeypatch,
        obtener_url,
        ["2026/08/09"],
        "09/08/2026",
        "09/08/2026",
        publicaciones_guardadas,
    )

    runpy.run_path("plazasboe.py", run_name="__main__")

    assert publicaciones_guardadas[-1].empty


def _publicacion_historica(version="legacy"):
    return pd.DataFrame(
        [
            {
                "Publicacion_ID": "BOE-A-2026-10463",
                "Enlace": "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-10463",
                "Fecha_BOE": "9 de agosto de 2026",
                "Titulo_original": "Título histórico",
                "Fecha_ultimo_analisis": pd.NA,
                "Version_extractor": version,
                "Estado_analisis": "con_coincidencias",
                "Coincidencias": 1,
            }
        ]
    )


def test_reprocesamiento_correcto_actualiza_version_y_deja_de_ser_candidato(
    monkeypatch,
):
    enlace = "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-10463"
    html_indice = '<a href="/diario_boe/txt.php?id=BOE-A-2026-10463">Publicación</a>'
    publicaciones_guardadas = []

    def obtener_url(url, timeout):
        if "index.php" in url:
            return _RespuestaHTTP(html_indice)
        if url == enlace:
            return _RespuestaHTTP(_html_publicacion_correcta())
        raise AssertionError(f"URL inesperada: {url}")

    _configurar_consulta_boe(
        monkeypatch,
        obtener_url,
        ["2026/08/09"],
        "09/08/2026",
        "09/08/2026",
        publicaciones_guardadas,
        _publicacion_historica(),
        [enlace],
    )
    monkeypatch.setattr(
        coincidencias,
        "buscar_coincidencias_local",
        lambda *args: [
            {"Num_plazas": 2, "Puesto": "Ingeniero", "Administración": "Entidad"}
        ],
    )

    runpy.run_path("plazasboe.py", run_name="__main__")

    actualizada = publicaciones_guardadas[-1]
    assert actualizada.loc[0, "Version_extractor"] == "1"
    assert actualizada.loc[0, "Coincidencias"] == 1
    assert not debe_procesar_publicacion(enlace, {enlace}, enlace, actualizada)


def test_fallo_en_reprocesamiento_conserva_publicacion_anterior(monkeypatch):
    enlace = "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-10463"
    html_indice = '<a href="/diario_boe/txt.php?id=BOE-A-2026-10463">Publicación</a>'
    publicaciones_guardadas = []
    historica = _publicacion_historica()

    def obtener_url(url, timeout):
        if "index.php" in url:
            return _RespuestaHTTP(html_indice)
        if url == enlace:
            return _RespuestaHTTP("", 500)
        raise AssertionError(f"URL inesperada: {url}")

    _configurar_consulta_boe(
        monkeypatch,
        obtener_url,
        ["2026/08/09"],
        "09/08/2026",
        "09/08/2026",
        publicaciones_guardadas,
        historica,
        [enlace],
    )

    runpy.run_path("plazasboe.py", run_name="__main__")

    pd.testing.assert_frame_equal(publicaciones_guardadas[-1], historica)


def test_reprocesamiento_sin_coincidencias_no_elimina_oposiciones(monkeypatch):
    enlace = "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-10463"
    html_indice = '<a href="/diario_boe/txt.php?id=BOE-A-2026-10463">Publicación</a>'
    publicaciones_guardadas = []
    oposiciones_guardadas = []
    oposicion_historica = pd.DataFrame(
        [
            {
                "Puesto": "Ingeniero histórico",
                "Administración": "Entidad histórica",
                "Enlace": enlace,
                "Latitud": 40.0,
                "Longitud": -3.0,
            }
        ]
    )

    def obtener_url(url, timeout):
        if "index.php" in url:
            return _RespuestaHTTP(html_indice)
        if url == enlace:
            return _RespuestaHTTP(_html_publicacion_correcta())
        raise AssertionError(f"URL inesperada: {url}")

    _configurar_consulta_boe(
        monkeypatch,
        obtener_url,
        ["2026/08/09"],
        "09/08/2026",
        "09/08/2026",
        publicaciones_guardadas,
        _publicacion_historica(),
        [enlace],
        oposicion_historica,
        oposiciones_guardadas,
    )

    runpy.run_path("plazasboe.py", run_name="__main__")

    assert len(oposiciones_guardadas[-1]) == 1
    pd.testing.assert_frame_equal(
        oposiciones_guardadas[-1][oposicion_historica.columns], oposicion_historica
    )
    assert publicaciones_guardadas[-1].loc[0, "Estado_analisis"] == "sin_coincidencias"
    assert publicaciones_guardadas[-1].loc[0, "Coincidencias"] == 0


@pytest.mark.parametrize(
    ("texto_busqueda", "puestos_esperados"),
    [
        ("ingeniero", ["Ingeniero Industrial"]),
        ("abogado", []),
        ("", ["Ingeniero Industrial", "Arquitecto Técnico", "Administrativo"]),
    ],
)
def test_publicaciones_cuenta_extraccion_completa_y_oposiciones_recibe_filtrado(
    monkeypatch, texto_busqueda, puestos_esperados
):
    enlace = "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-10463"
    html_indice = '<a href="/diario_boe/txt.php?id=BOE-A-2026-10463">Publicación</a>'
    publicaciones_guardadas = []
    puestos_guardados = []
    trazabilidad_guardada = []
    resultados_mostrados = {}
    resultados_mapa = []
    filtrado_real = preparar_archivo_datos.prepara_data_frame_mostrar_resultados
    extraidas = [
        {"Num_plazas": 2, "Puesto": "Ingeniero Industrial", "Administración": "Entidad", "Fecha_boe": "9 de agosto de 2026"},
        {"Num_plazas": 1, "Puesto": "Arquitecto Técnico", "Administración": "Entidad", "Fecha_boe": "9 de agosto de 2026"},
        {"Num_plazas": 3, "Puesto": "Administrativo", "Administración": "Entidad", "Fecha_boe": "9 de agosto de 2026"},
    ]

    def obtener_url(url, timeout):
        if "index.php" in url:
            return _RespuestaHTTP(html_indice)
        if url == enlace:
            return _RespuestaHTTP(_html_publicacion_correcta())
        raise AssertionError(f"URL inesperada: {url}")

    _configurar_consulta_boe(
        monkeypatch,
        obtener_url,
        ["2026/08/09"],
        "09/08/2026",
        "09/08/2026",
        publicaciones_guardadas,
    )
    monkeypatch.setattr(
        entradas_datos,
        "solicitar_fechas_y_validar",
        lambda *args: (
            texto_busqueda,
            "09/08/2026",
            "09/08/2026",
            ["2026/08/09"],
        ),
    )
    monkeypatch.setattr(
        coincidencias, "buscar_coincidencias_local", lambda *args: extraidas
    )

    def combinar(diccionario_puestos, *args):
        puestos_guardados.extend(diccionario_puestos.get("Puesto", []))
        trazabilidad_guardada.extend(
            zip(
                diccionario_puestos.get("Publicacion_ID", []),
                diccionario_puestos.get("Version_extractor", []),
                diccionario_puestos.get("Fecha_analisis", []),
            )
        )
        return pd.DataFrame(diccionario_puestos), pd.DataFrame({"Código": []})

    monkeypatch.setattr(preparar_archivo_datos, "combinar_dataframes", combinar)
    monkeypatch.setattr(
        preparar_archivo_datos,
        "prepara_data_frame_mostrar_resultados",
        filtrado_real,
    )
    monkeypatch.setattr(
        impresiones,
        "imprimir_diccionario_puestos",
        lambda diccionario, **kwargs: resultados_mostrados.update(diccionario),
    )
    monkeypatch.setattr(
        mapa_plazas,
        "generar_mapa_municipios",
        lambda dataframe: resultados_mapa.append(dataframe.copy(deep=True)),
    )

    runpy.run_path("plazasboe.py", run_name="__main__")

    publicacion = publicaciones_guardadas[-1].iloc[0]
    assert publicacion["Estado_analisis"] == "con_coincidencias"
    assert publicacion["Coincidencias"] == 3
    assert puestos_guardados == [
        "Ingeniero Industrial",
        "Arquitecto Técnico",
        "Administrativo",
    ]
    assert {fila[0] for fila in trazabilidad_guardada} == {"BOE-A-2026-10463"}
    assert {fila[1] for fila in trazabilidad_guardada} == {"1"}
    assert len({fila[2] for fila in trazabilidad_guardada}) == 1
    assert resultados_mostrados.get("Puesto", []) == puestos_esperados
    if puestos_esperados:
        assert resultados_mapa[-1]["Puesto"].tolist() == puestos_esperados
    else:
        assert resultados_mapa == []


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

    def guardar_excel(
        df_combinado,
        df_busquedas_combinado,
        df_log_errores,
        df_publicaciones=None,
        df_cobertura=None,
    ):
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


def test_busqueda_nueva_reutiliza_publicacion_y_filtra_oposiciones_locales(
    monkeypatch, capsys
):
    enlace = "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-10463"
    html_indice = '<a href="/diario_boe/txt.php?id=BOE-A-2026-10463">Publicación</a>'
    fecha_analisis = "2026-08-20 10:11:12"
    fecha_ultimo_analisis = "2026-08-20 10:11:12"
    publicaciones_iniciales = pd.DataFrame(
        [
            {
                "Publicacion_ID": "BOE-A-2026-10463",
                "Enlace": enlace,
                "Fecha_BOE": "9 de agosto de 2026",
                "Titulo_original": "Convocatoria múltiple",
                "Fecha_ultimo_analisis": fecha_ultimo_analisis,
                "Version_extractor": "1",
                "Estado_analisis": "con_coincidencias",
                "Coincidencias": 2,
            }
        ]
    )
    oposiciones_iniciales = pd.DataFrame(
        [
            {
                "Num_plazas": 2,
                "Puesto": "Ingeniero Industrial",
                "Administración": "Ayuntamiento de Madrid",
                "Escala": "--",
                "Subescala": "--",
                "Clase": "--",
                "Sistema": "Oposición",
                "Turno": "Libre",
                "Fecha_boe": "9 de agosto de 2026",
                "Publicación": "Convocatoria múltiple",
                "Enlace": enlace,
                "Municipio": "Madrid",
                "Provincia": "Madrid",
                "Latitud": 40.4168,
                "Longitud": -3.7038,
                "Habitantes": 3000000,
                "Publicacion_ID": "BOE-A-2026-10463",
                "Version_extractor": "1",
                "Fecha_analisis": fecha_analisis,
            },
            {
                "Num_plazas": 1,
                "Puesto": "Arquitecto Técnico",
                "Administración": "Ayuntamiento de Madrid",
                "Escala": "--",
                "Subescala": "--",
                "Clase": "--",
                "Sistema": "Oposición",
                "Turno": "Libre",
                "Fecha_boe": "9 de agosto de 2026",
                "Publicación": "Convocatoria múltiple",
                "Enlace": enlace,
                "Municipio": "Madrid",
                "Provincia": "Madrid",
                "Latitud": 40.4168,
                "Longitud": -3.7038,
                "Habitantes": 3000000,
                "Publicacion_ID": "BOE-A-2026-10463",
                "Version_extractor": "1",
                "Fecha_analisis": fecha_analisis,
            },
        ]
    )
    publicaciones_guardadas = []
    oposiciones_guardadas = []
    busquedas_guardadas = []
    resultados_mostrados = {}
    mapas = []
    solicitudes = []
    codigo_anterior = f"{enlace}_ingeniero"
    codigo_nuevo = f"{enlace}_arquitecto"
    combinar_real = preparar_archivo_datos.combinar_dataframes
    filtrar_real = preparar_archivo_datos.prepara_data_frame_mostrar_resultados

    def obtener_url(url, timeout):
        solicitudes.append(url)
        if "index.php" in url:
            return _RespuestaHTTP(html_indice)
        raise AssertionError("Una publicación reutilizable no debe descargarse")

    _configurar_consulta_boe(
        monkeypatch,
        obtener_url,
        ["2026/08/09"],
        "09/08/2026",
        "09/08/2026",
        publicaciones_guardadas,
        publicaciones_iniciales,
        [codigo_anterior],
        oposiciones_iniciales,
        oposiciones_guardadas,
        busquedas_guardadas,
    )
    monkeypatch.setattr(
        entradas_datos,
        "solicitar_fechas_y_validar",
        lambda *args: (
            "arquitecto",
            "09/08/2026",
            "09/08/2026",
            ["2026/08/09"],
        ),
    )
    monkeypatch.setattr(
        preparar_archivo_datos, "combinar_dataframes", combinar_real
    )
    monkeypatch.setattr(
        preparar_archivo_datos,
        "prepara_data_frame_mostrar_resultados",
        filtrar_real,
    )
    monkeypatch.setattr(
        impresiones,
        "imprimir_diccionario_puestos",
        lambda diccionario, **kwargs: resultados_mostrados.update(diccionario),
    )
    monkeypatch.setattr(
        mapa_plazas,
        "generar_mapa_municipios",
        lambda dataframe: mapas.append(dataframe.copy(deep=True)),
    )
    monkeypatch.setattr(
        boe_api,
        "obtener_sumario_api",
        lambda fecha: _sumario_api([_item_api("BOE-A-2026-10463")]),
    )

    runpy.run_path("plazasboe.py", run_name="__main__")

    assert solicitudes == []
    assert resultados_mostrados["Puesto"] == ["Arquitecto Técnico"]
    assert mapas[-1]["Puesto"].tolist() == ["Arquitecto Técnico"]
    assert set(busquedas_guardadas[-1]["Código"]) == {
        codigo_anterior,
        codigo_nuevo,
    }
    pd.testing.assert_frame_equal(
        oposiciones_guardadas[-1].reset_index(drop=True),
        oposiciones_iniciales.reset_index(drop=True),
    )
    pd.testing.assert_frame_equal(
        publicaciones_guardadas[-1], publicaciones_iniciales
    )
    salida = capsys.readouterr().out
    assert "Publicaciones descargadas: 0" in salida
    assert "Publicaciones reutilizadas localmente: 1" in salida


def test_cobertura_indice_200_cuenta_enlaces_unicos_y_no_cambia_por_error_documental(
    monkeypatch
):
    enlace = "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-10463"
    html_indice = (
        '<a href="/diario_boe/txt.php?id=BOE-A-2026-10463">Primero</a>'
        '<a href="/diario_boe/txt.php?id=BOE-A-2026-10463">Duplicado</a>'
    )
    cobertura_guardada = []

    def obtener_url(url, timeout):
        if "index.php" in url:
            return _RespuestaHTTP(html_indice)
        if url == enlace:
            return _RespuestaHTTP("", 500)
        raise AssertionError(f"URL inesperada: {url}")

    _configurar_consulta_boe(
        monkeypatch,
        obtener_url,
        ["2026/08/09"],
        "09/08/2026",
        "09/08/2026",
        cobertura_guardada=cobertura_guardada,
    )

    runpy.run_path("plazasboe.py", run_name="__main__")

    fila = cobertura_guardada[-1].iloc[0]
    assert fila["Estado"] == "consultado"
    assert fila["Numero_publicaciones"] == 1


@pytest.mark.parametrize(
    ("respuesta", "estado_esperado"),
    [(_RespuestaHTTP("<html>Sin publicaciones</html>"), "consultado"),
     (_RespuestaHTTP("", 404), "sin_edicion")],
)
def test_cobertura_dia_sin_publicaciones(monkeypatch, respuesta, estado_esperado):
    cobertura_guardada = []
    _configurar_consulta_boe(
        monkeypatch,
        lambda *args, **kwargs: respuesta,
        ["2026/08/09"],
        "09/08/2026",
        "09/08/2026",
        cobertura_guardada=cobertura_guardada,
    )

    with pytest.raises(SystemExit) as salida:
        runpy.run_path("plazasboe.py", run_name="__main__")

    assert salida.value.code == 0
    fila = cobertura_guardada[-1].iloc[0]
    assert fila["Estado"] == estado_esperado
    assert fila["Numero_publicaciones"] == 0


@pytest.mark.parametrize("estado_http", [429, 500])
def test_cobertura_registra_error_http_del_indice(monkeypatch, estado_http):
    cobertura_guardada = []
    llamadas = []

    def obtener_url(url, timeout):
        llamadas.append(url)
        return _RespuestaHTTP("", estado_http)

    _configurar_consulta_boe(
        monkeypatch,
        obtener_url,
        ["2026/08/09"],
        "09/08/2026",
        "09/08/2026",
        cobertura_guardada=cobertura_guardada,
    )

    with pytest.raises(SystemExit):
        runpy.run_path("plazasboe.py", run_name="__main__")

    assert len(llamadas) == 3
    fila = cobertura_guardada[-1].iloc[0]
    assert fila["Estado"] == "error"
    assert pd.isna(fila["Numero_publicaciones"])


@pytest.mark.parametrize(
    "error_red", [requests.exceptions.Timeout(), requests.exceptions.ConnectionError()]
)
def test_cobertura_registra_timeout_y_error_de_conexion(monkeypatch, error_red):
    cobertura_guardada = []

    def obtener_url(*args, **kwargs):
        raise error_red

    _configurar_consulta_boe(
        monkeypatch,
        obtener_url,
        ["2026/08/09"],
        "09/08/2026",
        "09/08/2026",
        cobertura_guardada=cobertura_guardada,
    )

    with pytest.raises(SystemExit):
        runpy.run_path("plazasboe.py", run_name="__main__")

    assert cobertura_guardada[-1].iloc[0]["Estado"] == "error"


def test_cobertura_existente_no_evital_peticion_y_fallo_no_la_destruye(monkeypatch):
    cobertura_guardada = []
    llamadas = []
    cobertura_inicial = pd.DataFrame(
        [
            {
                "Fecha": "2026-08-09",
                "Estado": "consultado",
                "Version_extractor": "1",
                "Fecha_ultima_consulta": "2026-08-20 10:00:00",
                "Numero_publicaciones": 4,
            }
        ]
    )

    def obtener_url(url, timeout):
        llamadas.append(url)
        return _RespuestaHTTP("", 500)

    _configurar_consulta_boe(
        monkeypatch,
        obtener_url,
        ["2026/08/09"],
        "09/08/2026",
        "09/08/2026",
        cobertura_guardada=cobertura_guardada,
        cobertura_inicial=cobertura_inicial,
    )

    with pytest.raises(SystemExit):
        runpy.run_path("plazasboe.py", run_name="__main__")

    assert len(llamadas) == 3
    fila = cobertura_guardada[-1].iloc[0]
    assert fila["Estado"] == "consultado"
    assert fila["Version_extractor"] == "1"
    assert fila["Numero_publicaciones"] == 4
    assert fila["Fecha_ultima_consulta"] != "2026-08-20 10:00:00"


def test_integracion_cache_10_11_12_reutiliza_y_filtra_datos_locales(
    monkeypatch, capsys
):
    cobertura_inicial = pd.DataFrame(
        [
            {
                "Fecha": "2026-08-10",
                "Estado": "consultado",
                "Version_extractor": "1",
                "Fecha_ultima_consulta": "2026-08-20 10:00:00",
                "Numero_publicaciones": 2,
            },
            {
                "Fecha": "2026-08-11",
                "Estado": "sin_edicion",
                "Version_extractor": "1",
                "Fecha_ultima_consulta": "2026-08-20 10:00:00",
                "Numero_publicaciones": 0,
            },
        ]
    )
    publicaciones = pd.DataFrame(
        [
            {
                "Publicacion_ID": "BOE-A-2026-1000",
                "Fecha_BOE": "10 de agosto de 2026",
                "Version_extractor": "1",
                "Estado_analisis": "con_coincidencias",
                "Coincidencias": 1,
            },
            {
                "Publicacion_ID": "BOE-A-2026-1001",
                "Fecha_BOE": pd.Timestamp("2026-08-10"),
                "Version_extractor": "1",
                "Estado_analisis": "sin_coincidencias",
                "Coincidencias": 0,
            },
        ]
    )
    enlace = "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-1000"
    oposiciones = pd.DataFrame(
        [
            {
                "Num_plazas": 1,
                "Puesto": "Arquitecto Técnico",
                "Administración": "Ayuntamiento de Madrid",
                "Fecha_boe": "10 de agosto de 2026",
                "Enlace": enlace,
                "Publicacion_ID": "BOE-A-2026-1000",
                "Latitud": 40.4,
                "Longitud": -3.7,
                "Habitantes": 3000000,
            },
            {
                "Num_plazas": 1,
                "Puesto": "Arquitecto fuera del intervalo",
                "Administración": "Ayuntamiento de Madrid",
                "Fecha_boe": "9 de agosto de 2026",
                "Enlace": "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-999",
                "Publicacion_ID": "BOE-A-2026-999",
                "Latitud": 40.4,
                "Longitud": -3.7,
                "Habitantes": 3000000,
            },
        ]
    )
    cobertura_guardada = []
    busquedas_guardadas = []
    resultados = {}
    mapas = []
    solicitudes = []
    combinar_real = preparar_archivo_datos.combinar_dataframes
    filtrar_real = preparar_archivo_datos.prepara_data_frame_mostrar_resultados

    def obtener_url(url, timeout):
        solicitudes.append(url)
        assert "2026/08/12" in url, "Los índices 10 y 11 deben reutilizarse"
        return _RespuestaHTTP("<html>Sin publicaciones</html>")

    _configurar_consulta_boe(
        monkeypatch,
        obtener_url,
        ["2026/08/10", "2026/08/11", "2026/08/12"],
        "10/08/2026",
        "12/08/2026",
        publicaciones_iniciales=publicaciones,
        oposiciones_iniciales=oposiciones,
        busquedas_guardadas=busquedas_guardadas,
        cobertura_guardada=cobertura_guardada,
        cobertura_inicial=cobertura_inicial,
    )
    monkeypatch.setattr(
        entradas_datos,
        "solicitar_fechas_y_validar",
        lambda *args: (
            "arquitecto",
            "10/08/2026",
            "12/08/2026",
            ["2026/08/10", "2026/08/11", "2026/08/12"],
        ),
    )
    monkeypatch.setattr(
        preparar_archivo_datos, "combinar_dataframes", combinar_real
    )
    monkeypatch.setattr(
        preparar_archivo_datos,
        "prepara_data_frame_mostrar_resultados",
        filtrar_real,
    )
    monkeypatch.setattr(
        impresiones,
        "imprimir_diccionario_puestos",
        lambda diccionario, **kwargs: resultados.update(diccionario),
    )
    monkeypatch.setattr(
        mapa_plazas,
        "generar_mapa_municipios",
        lambda dataframe: mapas.append(dataframe.copy(deep=True)),
    )

    runpy.run_path("plazasboe.py", run_name="__main__")

    assert solicitudes == [
        "https://www.boe.es/boe/dias/2026/08/12/index.php?s=2B"
    ]
    assert resultados["Puesto"] == ["Arquitecto Técnico"]
    assert mapas[-1]["Puesto"].tolist() == ["Arquitecto Técnico"]
    assert busquedas_guardadas[-1].empty
    cobertura_final = cobertura_guardada[-1].set_index("Fecha")
    assert cobertura_final.loc["2026-08-10", "Fecha_ultima_consulta"] == "2026-08-20 10:00:00"
    assert cobertura_final.loc["2026-08-11", "Fecha_ultima_consulta"] == "2026-08-20 10:00:00"
    assert cobertura_final.loc["2026-08-12", "Estado"] == "consultado"
    salida = capsys.readouterr().out
    assert "Índices reutilizados localmente: 2" in salida
    assert "Índices consultados por HTTP: 1" in salida


def test_ejecucion_completamente_local_muestra_y_envia_resultados_al_mapa(
    monkeypatch, capsys
):
    publicacion_id = "BOE-A-2026-1000"
    enlace = f"https://www.boe.es/diario_boe/txt.php?id={publicacion_id}"
    cobertura = pd.DataFrame(
        [
            {
                "Fecha": "2026-08-10",
                "Estado": "consultado",
                "Version_extractor": "1",
                "Fecha_ultima_consulta": "2026-08-20 10:00:00",
                "Numero_publicaciones": 1,
            }
        ]
    )
    publicaciones = pd.DataFrame(
        [
            {
                "Publicacion_ID": publicacion_id,
                "Fecha_BOE": "10 de agosto de 2026",
                "Version_extractor": "1",
                "Estado_analisis": "con_coincidencias",
                "Coincidencias": 1,
            }
        ]
    )
    oposiciones = pd.DataFrame(
        [
            {
                "Num_plazas": 1,
                "Puesto": "Arquitecto Técnico",
                "Administración": "Ayuntamiento de Madrid",
                "Fecha_boe": "10 de agosto de 2026",
                "Enlace": enlace,
                "Publicacion_ID": publicacion_id,
                "Latitud": 40.4,
                "Longitud": -3.7,
                "Habitantes": 3000000,
            }
        ]
    )
    resultados = {}
    mapas = []
    filtrar_real = preparar_archivo_datos.prepara_data_frame_mostrar_resultados

    _configurar_consulta_boe(
        monkeypatch,
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Una ejecución local no debe consultar el índice")
        ),
        ["2026/08/10"],
        "10/08/2026",
        "10/08/2026",
        publicaciones_iniciales=publicaciones,
        oposiciones_iniciales=oposiciones,
        cobertura_inicial=cobertura,
    )
    monkeypatch.setattr(
        entradas_datos,
        "solicitar_fechas_y_validar",
        lambda *args: (
            "arquitecto",
            "10/08/2026",
            "10/08/2026",
            ["2026/08/10"],
        ),
    )
    monkeypatch.setattr(
        preparar_archivo_datos,
        "prepara_data_frame_mostrar_resultados",
        filtrar_real,
    )
    monkeypatch.setattr(
        impresiones,
        "imprimir_diccionario_puestos",
        lambda diccionario, **kwargs: resultados.update(diccionario),
    )
    monkeypatch.setattr(
        mapa_plazas,
        "generar_mapa_municipios",
        lambda dataframe: mapas.append(dataframe.copy(deep=True)),
    )
    monkeypatch.setattr(
        boe_api,
        "obtener_sumario_api",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("La cobertura reutilizable debe preceder a la API")
        ),
    )

    runpy.run_path("plazasboe.py", run_name="__main__")

    assert resultados["Puesto"] == ["Arquitecto Técnico"]
    assert mapas[-1]["Puesto"].tolist() == ["Arquitecto Técnico"]
    salida = capsys.readouterr().out
    assert "Índices reutilizados localmente: 1" in salida
    assert "Índices consultados por HTTP: 0" in salida


def _configurar_consulta_boe(
    monkeypatch,
    obtener_url,
    lista_fechas,
    fecha_inicio,
    fecha_fin,
    publicaciones_guardadas=None,
    publicaciones_iniciales=None,
    codigos_iniciales=None,
    oposiciones_iniciales=None,
    oposiciones_guardadas=None,
    busquedas_guardadas=None,
    cobertura_guardada=None,
    cobertura_inicial=None,
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
    oposiciones = (
        oposiciones_iniciales
        if oposiciones_iniciales is not None
        else pd.DataFrame(columns=columnas)
    )
    busquedas = pd.DataFrame({"Código": codigos_iniciales or []})
    publicaciones = (
        publicaciones_iniciales
        if publicaciones_iniciales is not None
        else pd.DataFrame()
    )
    cobertura = cobertura_inicial if cobertura_inicial is not None else pd.DataFrame()
    log_errores = pd.DataFrame(columns=["Fecha", "Tipo de error", "Enlace Web"])
    errores_guardados = []

    def guardar_excel(
        df_combinado,
        df_busquedas_combinado,
        df_log_errores,
        df_publicaciones=None,
        df_cobertura=None,
    ):
        errores_guardados.extend(df_log_errores.to_dict(orient="records"))
        if publicaciones_guardadas is not None:
            publicaciones_guardadas.append(df_publicaciones.copy(deep=True))
        if oposiciones_guardadas is not None:
            oposiciones_guardadas.append(df_combinado.copy(deep=True))
        if busquedas_guardadas is not None:
            busquedas_guardadas.append(df_busquedas_combinado.copy(deep=True))
        if cobertura_guardada is not None:
            cobertura_guardada.append(df_cobertura.copy(deep=True))

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
            "Publicaciones": publicaciones,
            "Cobertura": cobertura,
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


def _sumario_api(items=None, secciones=True):
    seccion = []
    if secciones:
        seccion = [{
            "codigo": "2B",
            "nombre": "II. Autoridades y personal. - B. Oposiciones y concursos",
            "departamento": [{
                "nombre": "ADMINISTRACIÓN LOCAL",
                "epigrafe": [{"item": items or []}],
            }],
        }]
    return {"estado": "OK", "sumario": {"diario": [{"seccion": seccion}]}}


def _item_api(publicacion_id="BOE-A-2026-1"):
    return {
        "identificador": publicacion_id,
        "titulo": "Resolución de prueba",
        "url_html": f"https://www.boe.es/diario_boe/txt.php?id={publicacion_id}",
    }


def test_api_con_publicaciones_no_consulta_html_y_normaliza_enlaces():
    import plazasboe

    llamadas_html = []
    resultado = plazasboe._descubrir_indice_api_con_fallback(
        "2026/08/20",
        "https://www.boe.es/boe/dias/2026/08/20/index.php?s=2B",
        consultar_api=lambda fecha: _sumario_api([_item_api()]),
        consultar_html=lambda url: llamadas_html.append(url),
    )

    assert resultado["fuente"] == "api"
    assert resultado["estado"] == "consultado"
    assert resultado["enlaces"] == [
        "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-1"
    ]
    assert llamadas_html == []


@pytest.mark.parametrize(
    "respuesta,estado",
    [
        (_sumario_api(secciones=False), "consultado"),
        ({"estado": "SIN_EDICION", "sumario": None}, "sin_edicion"),
    ],
)
def test_api_sin_publicaciones_fiable_no_consulta_html(respuesta, estado):
    import plazasboe

    resultado = plazasboe._descubrir_indice_api_con_fallback(
        "2026/08/09",
        "indice",
        consultar_api=lambda fecha: respuesta,
        consultar_html=lambda url: pytest.fail("No debe consultar HTML"),
    )
    assert resultado["estado"] == estado
    assert resultado["enlaces"] == []
    assert resultado["fuente"] == "api"


def test_error_api_activa_fallback_html_sin_conservar_error_recuperado():
    import plazasboe

    esperado = {
        "estado": "consultado",
        "enlaces": ["https://www.boe.es/?id=BOE-A-2026-2"],
        "errores": [],
        "mensaje": None,
        "fuente": "html",
    }
    resultado = plazasboe._descubrir_indice_api_con_fallback(
        "2026/08/20",
        "indice",
        consultar_api=lambda fecha: (_ for _ in ()).throw(
            boe_api.ErrorAPIBOE("HTTP_500", "fallo")
        ),
        consultar_html=lambda url: esperado,
    )
    assert resultado == esperado


def test_error_api_y_html_conserva_error_final_existente():
    import plazasboe

    esperado = {
        "estado": "error",
        "enlaces": [],
        "errores": [{"Error al acceder": "indice"}],
        "mensaje": "fallo HTML",
        "fuente": "html",
    }
    resultado = plazasboe._descubrir_indice_api_con_fallback(
        "2026/08/20",
        "indice",
        consultar_api=lambda fecha: (_ for _ in ()).throw(
            boe_api.ErrorAPIBOE("TIMEOUT", "fallo")
        ),
        consultar_html=lambda url: esperado,
    )
    assert resultado == esperado


def test_api_deduplica_por_publicacion_id_sin_doble_procesamiento():
    import plazasboe

    resultado = plazasboe._descubrir_indice_api_con_fallback(
        "2026/08/20",
        "indice",
        consultar_api=lambda fecha: _sumario_api([_item_api(), _item_api()]),
        consultar_html=lambda url: pytest.fail("No debe consultar HTML"),
    )
    assert len(resultado["enlaces"]) == 1


def test_api_y_html_producen_la_misma_representacion_normalizada():
    import plazasboe

    class Respuesta:
        content = b'<a href="/diario_boe/txt.php?id=BOE-A-2026-1">Documento</a>'
        status_code = 200
        def raise_for_status(self):
            return None

    api = plazasboe._descubrir_indice_api_con_fallback(
        "2026/08/20", "indice",
        consultar_api=lambda fecha: _sumario_api([_item_api()]),
    )
    html = plazasboe._descubrir_indice_html(
        "indice", obtener=lambda *a, **k: Respuesta()
    )
    assert api["estado"] == html["estado"]
    assert api["enlaces"] == html["enlaces"]


def test_publicacion_api_se_descarga_y_registra_cobertura_correcta(
    monkeypatch, capsys
):
    publicacion_id = "BOE-A-2026-20000"
    enlace = f"https://www.boe.es/diario_boe/txt.php?id={publicacion_id}"
    solicitudes = []
    coberturas = []

    def obtener_documento(url, timeout):
        solicitudes.append(url)
        assert url == enlace
        return _RespuestaHTTP(
            '<div class="documento-tit">Documento API</div>'
            '<div class="metadatos">20 de agosto de 2026</div>'
            '<div id="textoxslt">Contenido</div>'
        )

    _configurar_consulta_boe(
        monkeypatch,
        obtener_documento,
        ["2026/08/20"],
        "20/08/2026",
        "20/08/2026",
        cobertura_guardada=coberturas,
    )
    monkeypatch.setattr(
        boe_api,
        "obtener_sumario_api",
        lambda fecha: _sumario_api([_item_api(publicacion_id)]),
    )

    runpy.run_path("plazasboe.py", run_name="__main__")

    assert solicitudes == [enlace]
    cobertura = coberturas[-1].iloc[-1]
    assert cobertura["Estado"] == "consultado"
    assert cobertura["Numero_publicaciones"] == 1
    salida = capsys.readouterr().out
    assert "Índices resueltos por API: 1" in salida
    assert "Índices resueltos por fallback HTML: 0" in salida


def test_seleccionar_extractor_centraliza_el_rango_historico():
    import plazasboe
    assert plazasboe.seleccionar_extractor("2004-01-02") == "historico"
    assert plazasboe.seleccionar_extractor("2005-01-02") == "actual"
