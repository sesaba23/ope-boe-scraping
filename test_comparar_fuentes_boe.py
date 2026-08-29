from comparar_fuentes_boe import comparar_fecha, obtener_publicaciones_html
from boe_api import ErrorAPIBOE


def _api(ids):
    return {"estado": "OK", "sumario": {"diario": [{"seccion": [{
        "codigo": "2B", "nombre": "II. Autoridades y personal. - B. Oposiciones y concursos",
        "departamento": [{"nombre": "ORG", "epigrafe": [{"item": [
            {"identificador": i, "titulo": i, "url_html": f"https://x/?id={i}"} for i in ids
        ]}]}],
    }]}]}}


def _html(ids):
    return {"estado": "CON_PUBLICACIONES", "publicaciones": [
        {"Publicacion_ID": i, "titulo": i, "url_html": f"https://x/?id={i}"} for i in ids
    ]}


def test_comparacion_identica():
    resultado = comparar_fecha("2025-01-02", lambda f: _api(["BOE-A-2025-1"]), lambda f: _html(["BOE-A-2025-1"]))
    assert resultado["clasificacion"] == "COINCIDEN"
    assert resultado["numero_api"] == resultado["numero_html"] == 1
    assert resultado["ids_comunes"] == ["BOE-A-2025-1"]


def test_publicacion_solo_api():
    resultado = comparar_fecha("2025-01-02", lambda f: _api(["BOE-A-2025-1", "BOE-A-2025-2"]), lambda f: _html(["BOE-A-2025-1"]))
    assert resultado["clasificacion"] == "SOLO_API"
    assert resultado["solo_api"][0]["Publicacion_ID"] == "BOE-A-2025-2"


def test_publicacion_solo_html():
    resultado = comparar_fecha("2025-01-02", lambda f: _api(["BOE-A-2025-1"]), lambda f: _html(["BOE-A-2025-1", "BOE-A-2025-2"]))
    assert resultado["clasificacion"] == "SOLO_HTML"
    assert resultado["solo_html"][0]["Publicacion_ID"] == "BOE-A-2025-2"


def test_error_api_queda_diferenciado():
    def api(_fecha):
        raise ErrorAPIBOE("HTTP_500", "fallo API")
    resultado = comparar_fecha("2025-01-02", api, lambda f: _html([]))
    assert resultado["clasificacion"] == "ERROR_API"
    assert resultado["error_api"] == "fallo API"


def test_error_html_queda_diferenciado():
    def html(_fecha):
        raise RuntimeError("fallo HTML")
    resultado = comparar_fecha("2025-01-02", lambda f: _api([]), html)
    assert resultado["clasificacion"] == "ERROR_HTML"
    assert resultado["error_html"] == "fallo HTML"


def test_html_deduplica_y_extrae_id_sin_consultar_documentos():
    class Respuesta:
        status_code = 200
        content = b'<a href="/diario_boe/txt.php?id=BOE-A-2025-1">Uno</a><a href="/diario_boe/txt.php?id=BOE-A-2025-1">Uno repetido</a>'
        def raise_for_status(self): pass
    llamadas = []
    resultado = obtener_publicaciones_html("2025-01-02", obtener=lambda url, **k: llamadas.append(url) or Respuesta())
    assert len(llamadas) == 1
    assert [p["Publicacion_ID"] for p in resultado["publicaciones"]] == ["BOE-A-2025-1"]
