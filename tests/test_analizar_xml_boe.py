from datetime import datetime
import json

import pytest
import requests

import analizar_xml_boe as analizar


XML = '''<?xml version="1.0"?>
<documento fecha_actualizacion="20250813">
  <metadatos>
    <identificador>BOE-A-2004-1</identificador>
    <departamento codigo="310">Universidades</departamento>
    <titulo>Convocatoria de prueba</titulo>
    <fecha_publicacion>20040102</fecha_publicacion>
  </metadatos>
  <texto>
    <p class="parrafo">Se convocan dos plazas mediante oposición y turno libre.</p>
    <p class="parrafo">Segunda línea.</p>
  </texto>
</documento>'''.encode("utf-8")
HTML = '<div class="documento-tit">Convocatoria de prueba</div><div class="metadatos">2 de enero de 2004</div><div id="textoxslt">Se convocan dos plazas mediante oposición y turno libre. Segunda línea.</div>'.encode("utf-8")


class Respuesta:
    def __init__(self, contenido=b"", estado=200):
        self.content = contenido
        self.status_code = estado

    def raise_for_status(self):
        if self.status_code >= 400:
            respuesta = requests.Response(); respuesta.status_code = self.status_code
            raise requests.HTTPError(response=respuesta)


def _documento():
    return {
        "Publicacion_ID": "BOE-A-2004-1", "Fecha": "2004-01-02",
        "titulo": "Convocatoria", "departamento": "Universidades",
        "url_xml": "https://boe/xml", "url_html": "https://boe/html",
    }


def test_xml_valido_metadatos_texto_repetidos_y_atributos():
    resultado = analizar.analizar_xml(XML)
    assert resultado["elemento_raiz"] == "documento"
    assert resultado["metadatos"]["identificador"] == "BOE-A-2004-1"
    assert resultado["numero_bloques_texto"] == 2
    assert resultado["bloques_repetidos"]["p"] == 2
    assert resultado["atributos"]["departamento"] == ["codigo"]
    assert "Se convocan" in resultado["texto_relevante"]


def test_namespaces_se_detectan_y_no_ocultan_etiquetas():
    xml = XML.replace(b"<documento ", b'<documento xmlns="urn:boe" ')
    resultado = analizar.analizar_xml(xml)
    assert resultado["namespaces"]["(predeterminado)"] == "urn:boe"
    assert resultado["metadatos"]["identificador"] == "BOE-A-2004-1"


def test_xml_invalido_y_declaraciones_no_admitidas():
    with pytest.raises(ValueError, match="XML inválido"):
        analizar.analizar_xml(b"<documento>")
    with pytest.raises(ValueError, match="declaración"):
        analizar.analizar_xml(b'<!DOCTYPE x [<!ENTITY y "z">]><x/>')


def test_clasificacion_estructurada_semiestructurada_texto_libre_y_ausente():
    xml = b'''<documento><metadatos><identificador>BOE-A-2004-1</identificador><fecha_publicacion>20040101</fecha_publicacion></metadatos><texto><tabla><fila>3 plazas de Auxiliar</fila></tabla><p>Turno libre por oposicion</p></texto></documento>'''
    soporte = analizar.analizar_xml(xml)["soporte_campos"]
    assert soporte["Publicacion_ID"] == "ESTRUCTURADO"
    assert soporte["Num_plazas"] == "SEMIESTRUCTURADO"
    assert soporte["Turno"] == "TEXTO_LIBRE"
    assert soporte["Subescala"] == "NO_PRESENTE"


def test_comparacion_html_xml_detecta_contenido_equivalente():
    estructura = analizar.analizar_xml(XML)
    comparacion = analizar.comparar_html_xml(HTML, estructura)
    assert comparacion["contenido_esencialmente_igual"] is True
    assert comparacion["metadatos_xml"]["departamento"] == "Universidades"
    assert "identificador" in comparacion["informacion_solo_xml"]


def test_xml_no_disponible():
    resultado = analizar.analizar_publicacion(
        _documento(), obtener=lambda url, **k: Respuesta(estado=404)
    )
    assert resultado["estado"] == "XML_NO_DISPONIBLE"


def test_error_http_xml():
    resultado = analizar.analizar_publicacion(
        _documento(), obtener=lambda url, **k: Respuesta(estado=500)
    )
    assert resultado["estado"] == "ERROR_HTTP"


def test_publicacion_xml_valida_descarga_xml_y_html_una_vez():
    llamadas = []
    def obtener(url, **kwargs):
        llamadas.append(url)
        return Respuesta(XML if url.endswith("xml") else HTML)

    resultado = analizar.analizar_publicacion(_documento(), obtener=obtener)
    assert resultado["estado"] == "XML_VALIDO"
    assert llamadas == ["https://boe/xml", "https://boe/html"]
    assert resultado["xml_evitaria_regex_historico"] == "PARCIALMENTE"
    assert "texto_relevante" not in resultado["estructura_xml"]


def test_muestra_obtiene_urls_de_api_y_respeta_publicacion():
    def api(fecha):
        identificador = next(k for k, v in analizar.MUESTRA_2004.items() if v == str(fecha))
        item = {
            "identificador": identificador,
            "url_html": f"https://html?id={identificador}",
            "url_xml": f"https://xml?id={identificador}",
        }
        return {"estado": "OK", "sumario": {"diario": [{"seccion": [{
            "codigo": "2B", "departamento": {"nombre": "ORG", "item": item}
        }]}]}}

    resultado = analizar.obtener_muestra_api(
        publicacion_id="BOE-A-2004-6488", consultar_api=api
    )
    assert resultado[0]["url_xml"].startswith("https://xml")
    assert resultado[0]["Publicacion_ID"] == "BOE-A-2004-6488"


def test_resumen_cuenta_soportes_y_beneficios():
    detalle = analizar.analizar_publicacion(
        _documento(),
        obtener=lambda url, **k: Respuesta(
            XML if url.endswith("xml") else HTML
        ),
    )
    resumen = analizar.resumir([detalle])
    assert resumen["XML_VALIDO"] == 1
    assert resumen["soporte_campos"]["ESTRUCTURADO"] >= 3
    assert resumen["beneficios"]["HIBRIDO_XML_TEXTO"] == 1


def test_generacion_json_markdown_y_ausencia_de_escritura_productiva(tmp_path):
    detalle = analizar.analizar_publicacion(
        _documento(),
        obtener=lambda url, **k: Respuesta(
            XML if url.endswith("xml") else HTML
        ),
    )
    resumen = analizar.resumir([detalle])
    excel = tmp_path / "BOE-oposiciones.xlsx"; excel.write_bytes(b"intacto")
    antes = analizar.integridad_excel(excel)
    rutas = analizar.guardar_informes(
        [detalle], resumen,
        {"antes": antes, "despues": antes, "sin_cambios": True},
        tmp_path / "informes", datetime(2026, 8, 23, 10, 0, 0),
    )
    datos = json.loads(rutas[0].read_text(encoding="utf-8"))
    markdown = rutas[1].read_text(encoding="utf-8")
    assert datos["publicaciones"][0]["Publicacion_ID"] == "BOE-A-2004-1"
    assert "Recomendación arquitectónica" in markdown
    assert analizar.integridad_excel(excel) == antes
