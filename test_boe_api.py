from datetime import date, datetime

import pytest
import requests

from boe_api import ErrorAPIBOE, extraer_publicaciones_2b_api, obtener_sumario_api


class Respuesta:
    def __init__(self, datos=None, status_code=200, error_json=None, contenido=b""):
        self.datos = datos
        self.status_code = status_code
        self.error_json = error_json
        self._contenido = contenido

    @property
    def content(self):
        return self._contenido

    def json(self):
        if self.error_json:
            raise self.error_json
        return self.datos

    def raise_for_status(self):
        if self.status_code >= 400:
            respuesta = requests.Response()
            respuesta.status_code = self.status_code
            raise requests.HTTPError(response=respuesta)


def _json(secciones=None):
    return {
        "status": {"code": "200", "text": "ok"},
        "data": {"sumario": {"diario": [{"seccion": secciones or []}]}},
    }


def _seccion(items, codigo="2B", nombre="II. Autoridades y personal. - B. Oposiciones y concursos"):
    return {
        "codigo": codigo,
        "nombre": nombre,
        "departamento": [{
            "nombre": "ADMINISTRACIÓN LOCAL",
            "epigrafe": [{"item": items}],
        }],
    }


def _item(identificador="BOE-A-2025-1"):
    return {
        "identificador": identificador,
        "titulo": "Resolución de prueba",
        "url_html": f"https://www.boe.es/diario_boe/txt.php?id={identificador}",
        "url_xml": f"https://www.boe.es/diario_boe/xml.php?id={identificador}",
        "url_pdf": {"texto": f"https://www.boe.es/pdfs/{identificador}.pdf"},
    }


@pytest.mark.parametrize(
    "fecha,esperada",
    [(date(2025, 1, 2), "20250102"), (datetime(2025, 1, 2, 3), "20250102"),
     ("2025-01-02", "20250102"), ("2025/01/02", "20250102"),
     ("20250102", "20250102")],
)
def test_fecha_y_cabecera_accept(fecha, esperada):
    llamada = {}

    def obtener(url, **kwargs):
        llamada.update(url=url, **kwargs)
        return Respuesta(_json())

    resultado = obtener_sumario_api(fecha, obtener=obtener)

    assert llamada["url"].endswith(esperada)
    assert llamada["headers"] == {"Accept": "application/json"}
    assert llamada["timeout"] == 10
    assert resultado["estado"] == "OK"


def test_extrae_2b_varias_publicaciones_y_enlaces():
    resultado = extraer_publicaciones_2b_api(
        obtener_sumario_api(
            "2025-01-02",
            obtener=lambda *a, **k: Respuesta(_json([_seccion([_item(), _item("BOE-A-2025-2")])])),
        )
    )

    assert resultado["estado"] == "CON_PUBLICACIONES"
    assert [p["Publicacion_ID"] for p in resultado["publicaciones"]] == [
        "BOE-A-2025-1", "BOE-A-2025-2"
    ]
    primero = resultado["publicaciones"][0]
    assert primero["titulo"] == "Resolución de prueba"
    assert primero["departamento"] == "ADMINISTRACIÓN LOCAL"
    assert primero["url_html"].endswith("BOE-A-2025-1")
    assert primero["url_xml"].endswith("BOE-A-2025-1")
    assert primero["url_pdf"].endswith("BOE-A-2025-1.pdf")


def test_codigo_estructurado_2b_tiene_prioridad_y_texto_es_fallback():
    por_codigo = _seccion(_item(), nombre="Nombre cambiado")
    por_texto = _seccion(_item("BOE-A-2025-2"), codigo="")
    resultado = extraer_publicaciones_2b_api({"estado": "OK", "sumario": {"diario": [{"seccion": [por_codigo, por_texto]}]}})
    assert len(resultado["publicaciones"]) == 2


def test_2b_ausente_no_es_error():
    resultado = extraer_publicaciones_2b_api({"estado": "OK", "sumario": {"diario": [{"seccion": [{"codigo": "1", "nombre": "I"}]}]}})
    assert resultado == {"estado": "SIN_SECCION_2B", "publicaciones": []}


def test_dia_sin_edicion_confirmado_por_json_404():
    respuesta = Respuesta({"status": {"code": "404", "text": "No encontrado"}}, 404)
    sumario = obtener_sumario_api("2025-01-05", obtener=lambda *a, **k: respuesta)
    assert extraer_publicaciones_2b_api(sumario)["estado"] == "SIN_EDICION"


def test_dia_sin_edicion_confirmado_por_xml_oficial_404():
    contenido = b"<response><status><code>404</code><text>La informacion solicitada no existe</text></status><data/></response>"
    respuesta = Respuesta(status_code=404, error_json=ValueError(), contenido=contenido)
    assert obtener_sumario_api("2025-01-05", obtener=lambda *a, **k: respuesta)["estado"] == "SIN_EDICION"


def test_seccion_puede_ser_objeto_en_lugar_de_lista():
    resultado = extraer_publicaciones_2b_api({
        "estado": "OK",
        "sumario": {"diario": [{"seccion": _seccion(_item())}]},
    })
    assert resultado["publicaciones"][0]["Publicacion_ID"] == "BOE-A-2025-1"


def test_deduplica_por_id_y_por_url_si_falta_id():
    sin_id = _item("invalido")
    resultado = extraer_publicaciones_2b_api({"estado": "OK", "sumario": {"diario": [{"seccion": [_seccion([_item(), _item(), sin_id, dict(sin_id)])]}]}})
    assert len(resultado["publicaciones"]) == 2
    assert "Publicacion_ID" not in resultado["publicaciones"][1]


@pytest.mark.parametrize("codigo,tipo", [(400, "HTTP_400"), (429, "HTTP_429"), (500, "HTTP_5XX")])
def test_estados_http_son_errores(codigo, tipo):
    with pytest.raises(ErrorAPIBOE) as capturado:
        obtener_sumario_api("2025-01-02", obtener=lambda *a, **k: Respuesta({}, codigo))
    assert capturado.value.tipo == tipo


def test_404_no_confirmado_es_error():
    with pytest.raises(ErrorAPIBOE) as capturado:
        obtener_sumario_api("2025-01-02", obtener=lambda *a, **k: Respuesta({}, 404))
    assert capturado.value.tipo == "HTTP_404"


@pytest.mark.parametrize(
    "error,tipo",
    [(requests.Timeout("t"), "TIMEOUT"), (requests.ConnectionError("c"), "CONEXION")],
)
def test_errores_de_red(error, tipo):
    def obtener(*args, **kwargs):
        raise error
    with pytest.raises(ErrorAPIBOE) as capturado:
        obtener_sumario_api("2025-01-02", obtener=obtener)
    assert capturado.value.tipo == tipo


def test_json_invalido():
    with pytest.raises(ErrorAPIBOE, match="JSON válido") as capturado:
        obtener_sumario_api("2025-01-02", obtener=lambda *a, **k: Respuesta(error_json=ValueError()))
    assert capturado.value.tipo == "JSON_INVALIDO"


@pytest.mark.parametrize(
    "datos",
    [[], {}, {"status": {"code": "200"}}, {"status": {"code": "200"}, "data": {"sumario": {}}}],
)
def test_estructura_inesperada(datos):
    with pytest.raises(ErrorAPIBOE) as capturado:
        obtener_sumario_api("2025-01-02", obtener=lambda *a, **k: Respuesta(datos))
    assert capturado.value.tipo == "ESTRUCTURA"


def test_status_interno_no_exitoso():
    with pytest.raises(ErrorAPIBOE) as capturado:
        obtener_sumario_api("2025-01-02", obtener=lambda *a, **k: Respuesta({"status": {"code": "500", "text": "error"}}))
    assert capturado.value.tipo == "STATUS_500"
