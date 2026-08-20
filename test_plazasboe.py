import runpy
import sys

import pandas as pd
import requests

import coincidencias
import entradas_datos
import impresiones
import mapa_plazas
import preparar_archivo_datos


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

    runpy.run_path("plazasboe.py", run_name="__main__")

    assert enlaces_analizados == [enlace_correcto]
