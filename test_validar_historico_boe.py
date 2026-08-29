from datetime import datetime
import json
from pathlib import Path

import pandas as pd
import pytest
import requests

import coincidencias
import validar_historico_boe as validar


def _publicacion(numero, mes=1, departamento="ADMINISTRACIÓN LOCAL", carga=5):
    return {
        "Publicacion_ID": f"BOE-A-2004-{numero}",
        "Fecha": f"2004-{mes:02d}-15",
        "Mes": mes,
        "Numero_publicaciones_dia": carga,
        "titulo": f"Título {numero}",
        "departamento": departamento,
        "url_html": f"https://www.boe.es/diario_boe/txt.php?id=BOE-A-2004-{numero}",
    }


def _html(texto="Se convocan dos plazas", titulo="Convocatoria", fecha="15 de enero de 2004"):
    return (
        f'<div class="documento-tit">{titulo}</div>'
        f'<div class="metadatos">{fecha}</div>'
        f'<div id="textoxslt">{texto}</div>'
    )


class Respuesta:
    def __init__(self, contenido, estado=200):
        self.content = contenido.encode()
        self.status_code = estado

    def raise_for_status(self):
        if self.status_code >= 400:
            respuesta = requests.Response()
            respuesta.status_code = self.status_code
            raise requests.HTTPError(response=respuesta)


def _fila(**cambios):
    fila = {
        "Puesto": "Auxiliar", "Num_plazas": 2, "Turno": "Libre",
        "Sistema": "Oposición", "Escala": "Administración General",
        "Subescala": "Auxiliar", "Clase": "--",
        "Administración": "Ayuntamiento de Prueba",
    }
    fila.update(cambios)
    return fila


def test_seleccion_es_determinista_estratificada_y_respeta_limite():
    publicaciones = []
    for mes in range(1, 13):
        publicaciones.extend([
            _publicacion(mes * 10, mes, carga=1),
            _publicacion(mes * 10 + 1, mes, "MINISTERIO DE JUSTICIA", 30),
        ])
    publicaciones.append(_publicacion(999, 6, "UNIVERSIDADES", 12))

    primera = validar.seleccionar_muestra(publicaciones, 15)
    segunda = validar.seleccionar_muestra(list(reversed(publicaciones)), 15)

    assert [p["Publicacion_ID"] for p in primera] == [p["Publicacion_ID"] for p in segunda]
    assert len(primera) == 15
    assert {p["Mes"] for p in primera} == set(range(1, 13))
    categorias = {validar._categoria_departamento(p["departamento"]) for p in primera}
    assert categorias == {"LOCAL", "ESTADO", "OTRAS"}


def test_limite_invalido():
    with pytest.raises(ValueError):
        validar.seleccionar_muestra([], 0)


def test_documento_correctamente_extraido_usa_orden_local(monkeypatch):
    llamadas = []
    monkeypatch.setattr(coincidencias, "extraer_convocatorias_local", lambda *a: llamadas.append("local") or [_fila()])
    monkeypatch.setattr(coincidencias, "extraer_convocatorias_estatal", lambda *a: llamadas.append("estatal") or [])

    resultado = validar.analizar_publicacion(_publicacion(1), obtener=lambda *a, **k: Respuesta(_html()))

    assert resultado["clasificacion_extractor"] == "EXTRAIDA"
    assert resultado["numero_convocatorias_extraidas"] == 1
    assert llamadas == ["local"]
    assert resultado["convocatorias_extraidas"][0]["Puesto"] == "Auxiliar"


def test_varios_resultados_y_campos_problematicos(monkeypatch):
    monkeypatch.setattr(coincidencias, "extraer_convocatorias_local", lambda *a: [_fila(), _fila(Puesto="Técnico", Turno="No disponible", Clase=None)])
    resultado = validar.analizar_publicacion(_publicacion(2), obtener=lambda *a, **k: Respuesta(_html("Se convocan 2 plazas y 3 plazas de categorías distintas")))
    assert resultado["numero_convocatorias_extraidas"] == 2
    assert resultado["posible_multiconvocatoria"] is True
    assert resultado["campos_problematicos"]["Clase"] == 2
    assert resultado["campos_problematicos"]["Turno"] == 1


def test_documento_sin_resultados_no_es_error(monkeypatch):
    monkeypatch.setattr(coincidencias, "extraer_convocatorias_local", lambda *a: [])
    monkeypatch.setattr(coincidencias, "extraer_convocatorias_estatal", lambda *a: [])
    resultado = validar.analizar_publicacion(_publicacion(3), obtener=lambda *a, **k: Respuesta(_html()))
    assert resultado["clasificacion_extractor"] == "SIN_RESULTADOS"
    assert resultado["error"] is None


def test_error_documental():
    resultado = validar.analizar_publicacion(_publicacion(4), obtener=lambda *a, **k: Respuesta("", 500))
    assert resultado["clasificacion_extractor"] == "ERROR"
    assert resultado["error"]["tipo"] == "HTTPError"


@pytest.mark.parametrize(
    "texto,esperada",
    [
        ("Se convocan cinco plazas por turno libre.", "PROBABLE_CONVOCATORIA"),
        ("Se publica la relación definitiva de aprobados del tribunal.", "PROBABLE_NO_CONVOCATORIA"),
        ("Se anuncia información complementaria del proceso.", "REVISAR"),
    ],
)
def test_clasificacion_diagnostica(texto, esperada):
    assert validar.diagnosticar_texto(texto)[0] == esperada


def test_posible_multiconvocatoria():
    assert validar.detectar_multiconvocatoria("2 plazas de auxiliar y 3 plazas de técnico")
    assert not validar.detectar_multiconvocatoria("Una plaza de auxiliar")


def test_resumen_calcula_totales_desgloses_y_multiconvocatorias():
    detalles = [
        {**_detalle_base("EXTRAIDA", "PROBABLE_CONVOCATORIA", 2), "campos_problematicos": {"Clase": 1}},
        {**_detalle_base("SIN_RESULTADOS", "PROBABLE_CONVOCATORIA", 0), "posible_multiconvocatoria": True},
    ]
    resumen = validar.resumir_resultados(detalles, [], [0.1, 0.2], "estrategia")
    assert resumen["EXTRAIDA"] == 1
    assert resumen["SIN_RESULTADOS_diagnostico"]["PROBABLE_CONVOCATORIA"] == 1
    assert resumen["total_convocatorias_extraidas"] == 2
    assert resumen["posibles_multiconvocatoria_una_fila"] == 1
    assert resumen["campos_problematicos"] == {"Clase": 1}


def test_json_y_markdown_contienen_detalle_sin_html(tmp_path):
    detalle = _detalle_base("SIN_RESULTADOS", "PROBABLE_CONVOCATORIA", 0)
    resumen = validar.resumir_resultados([detalle], [], [0.1], "muestra estratificada")
    integridad = {"antes": {"sha256": "a"}, "despues": {"sha256": "a"}, "sin_cambios": True}
    rutas = validar.guardar_informes([detalle], resumen, integridad, tmp_path, datetime(2026, 8, 23, 10, 0, 0))
    datos = json.loads(rutas[0].read_text(encoding="utf-8"))
    markdown = rutas[1].read_text(encoding="utf-8")
    assert datos["publicaciones"][0]["Publicacion_ID"] == "BOE-A-2004-1"
    assert "html_completo" not in datos["publicaciones"][0]
    assert "SIN_RESULTADOS + PROBABLE_CONVOCATORIA" in markdown
    assert "muestra estratificada" in markdown


def test_integridad_solo_lee_y_dataframe_productivo_no_cambia(tmp_path):
    excel = tmp_path / "BOE-oposiciones.xlsx"
    excel.write_bytes(b"contenido")
    original = pd.DataFrame({"dato": [1]})
    copia = original.copy(deep=True)
    antes = validar.integridad_excel(excel)
    validar.seleccionar_muestra([_publicacion(1)], 1)
    despues = validar.integridad_excel(excel)
    assert antes == despues
    pd.testing.assert_frame_equal(original, copia)


def test_descubrimiento_usa_api_y_no_html():
    llamadas = []

    def api(fecha):
        llamadas.append(fecha)
        return {"estado": "SIN_EDICION", "sumario": None}

    publicaciones, errores, tiempos = validar.descubrir_publicaciones(
        2004, "2004-01-01", "2004-01-02", consultar_api=api
    )
    assert publicaciones == []
    assert errores == []
    assert len(llamadas) == len(tiempos) == 2


def _detalle_base(clasificacion, diagnostico, numero):
    return {
        "Publicacion_ID": "BOE-A-2004-1", "Fecha": "2004-01-15",
        "titulo": "Título", "departamento": "ADMINISTRACIÓN LOCAL",
        "url_html": "https://www.boe.es/?id=BOE-A-2004-1",
        "clasificacion_extractor": clasificacion,
        "clasificacion_diagnostica": diagnostico,
        "indicios_encontrados": ["se convocan"],
        "numero_convocatorias_extraidas": numero,
        "convocatorias_extraidas": [], "campos_problematicos": {},
        "posible_multiconvocatoria": False, "error": None,
        "tiempo_documental": 0.2,
    }
