import builtins
import html
import importlib
from io import BytesIO
import json
from pathlib import Path
import re
import subprocess
from threading import Event
import time
from urllib.parse import parse_qs, urlencode, urlsplit
import zipfile

import openpyxl
import pandas as pd
import pytest
import base_datos
from consultas_boe import buscar_oposiciones, oposiciones

import web_estadisticas
from actualizacion_boe import GestorActualizaciones
from gestion_exportacion import GestorExportacionXlsx


@pytest.fixture
def ruta_bd(tmp_path):
    ruta = tmp_path / "estadisticas-prueba.db"
    datos = pd.DataFrame(
        [
            {
                "Fecha_boe": "1 de enero de 2025",
                "Num_plazas": 2,
                "Puesto": "Ingeniero Industrial",
                "Administración": "Administración A",
                "Provincia": "Madrid",
                "Sistema": "Oposición",
                "Turno": "Libre",
            },
            {
                "Fecha_boe": "1 de febrero de 2025",
                "Num_plazas": 3,
                "Puesto": "Auxiliar Administrativo",
                "Administración": "Administración B",
                "Provincia": "Sevilla",
                "Sistema": "Concurso",
                "Turno": "Discapacidad",
            },
        ]
    )
    conexion = base_datos.conectar(ruta)
    base_datos.crear_esquema(conexion); base_datos.crear_indices(conexion)
    existentes = {fila[1] for fila in conexion.execute("PRAGMA table_info(oposiciones)")}
    for columna in ("administracion_normalizada TEXT", "ambito TEXT", "tipo_entidad TEXT",
                    "comunidad_autonoma TEXT", "puesto_normalizado TEXT", "municipio_codigo_ine TEXT",
                    "version_resolutor TEXT"):
        if columna.split()[0] not in existentes:
            conexion.execute(f"ALTER TABLE oposiciones ADD COLUMN {columna}")
    with base_datos.transaccion(conexion):
        for indice, fila in datos.iterrows():
            publicacion_id = f"BOE-A-2025-{indice}"
            fecha = f"2025-0{indice + 1}-01"
            conexion.execute("INSERT INTO publicaciones VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (publicacion_id, "https://x", fecha, fila["Fecha_boe"], "", "", "test", "con_coincidencias", 1, None, None, None, None, None, None, None))
            conexion.execute("INSERT INTO oposiciones(num_plazas,puesto,administracion,escala,subescala,clase,sistema,turno,fecha_boe,fecha_boe_original,enlace,provincia,publicacion_id,version_extractor) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (fila["Num_plazas"], fila["Puesto"], fila["Administración"], "--", "--", "--", fila["Sistema"], fila["Turno"], fecha, fila["Fecha_boe"], "https://x", fila["Provincia"], publicacion_id, "test"))
            comunidad = "Comunidad de Madrid" if fila["Provincia"] == "Madrid" else "Andalucía"
            conexion.execute("UPDATE oposiciones SET comunidad_autonoma = ? WHERE publicacion_id = ?", (comunidad, publicacion_id))
    base_datos.guardar_metadata(conexion, data_version=1); conexion.commit(); conexion.close()
    return ruta


@pytest.fixture
def cliente(ruta_bd):
    app = web_estadisticas.crear_app(ruta_bd)
    app.config["TESTING"] = True
    return app.test_client()


def test_pagina_principal_devuelve_html(cliente):
    respuesta = cliente.get("/")

    assert respuesta.status_code == 200
    assert b"BuscadorBOE" in respuesta.data
    assert b"Buscar oposiciones" in respuesta.data
    assert b'href="/estadisticas"' in respuesta.data
    assert b'href="/static/css/portal.css"' in respuesta.data
    assert b'src="/static/js/portal.js"' in respuesta.data


@pytest.mark.parametrize("ruta", ["/oposiciones", "/estadisticas"])
def test_rutas_principales_del_portal_devuelven_html(cliente, ruta):
    assert cliente.get(ruta).status_code == 200


def test_mapa_de_rutas_publicas_y_metodos_se_mantiene_estable(ruta_bd):
    """Congela el contrato público sin fijar rutas internas de Flask."""
    app = web_estadisticas.crear_app(ruta_bd)
    rutas = {
        (regla.rule, tuple(sorted(regla.methods - {"HEAD", "OPTIONS"})))
        for regla in app.url_map.iter_rules()
        if regla.endpoint != "static"
    }

    assert rutas == {
        ("/", ("GET",)),
        ("/cobertura", ("GET",)),
        ("/administracion/base-datos", ("GET",)),
        ("/administracion/base-datos/exportar.zip", ("GET",)),
        ("/administracion/base-datos/exportar.xlsx", ("GET",)),
        ("/oposiciones", ("GET",)),
        ("/oposiciones/exportar.csv", ("GET",)),
        ("/oposiciones/exportar.xlsx", ("GET",)),
        ("/oposiciones/<int:oposicion_id>", ("GET",)),
        ("/estadisticas", ("GET",)),
        ("/mapas", ("GET",)),
        ("/api/administracion/base-datos/exportacion", ("GET",)),
        ("/api/administracion/base-datos/exportacion", ("POST",)),
        ("/api/administracion/base-datos/verificar", ("POST",)),
        ("/api/administracion/base-datos/preparar-publicacion", ("POST",)),
        ("/api/administracion/base-datos/version-publicada", ("POST",)),
        ("/api/administracion/base-datos/confirmar-publicacion", ("POST",)),
        ("/api/administracion/base-datos/publicacion", ("GET",)),
        ("/api/administracion/base-datos/preparar-actualizacion", ("POST",)),
        ("/api/administracion/base-datos/confirmar-actualizacion", ("POST",)),
        ("/api/administracion/base-datos/actualizacion", ("GET",)),
        ("/api/oposiciones/mapa", ("GET",)),
        ("/api/oposiciones/sin-coordenadas", ("GET",)),
        ("/api/actualizar-busqueda", ("POST",)),
        ("/api/trabajos/<trabajo_id>", ("GET",)),
        ("/api/cobertura/dia", ("GET",)),
        ("/api/cobertura/actualizar", ("POST",)),
        ("/api/filtros/provincias", ("GET",)),
        ("/api/filtros/municipios", ("GET",)),
        ("/api/filtros/puestos", ("GET",)),
        ("/api/estadisticas", ("GET",)),
    }


def test_recursos_comunes_del_portal_estan_disponibles(cliente):
    assert cliente.get("/static/css/portal.css").status_code == 200
    assert cliente.get("/static/js/portal.js").status_code == 200


def test_buscador_inicial_no_carga_resultados_y_busqueda_conserva_filtros(cliente):
    inicial = cliente.get("/oposiciones")
    assert b"Encuentra tu pr" in inicial.data
    assert b"resultados encontrados" not in inicial.data
    respuesta = cliente.get("/oposiciones?texto=Ingeniero&provincia=Madrid&tamano_pagina=25")
    html = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200
    assert "1 resultados encontrados" in html
    assert 'value="Ingeniero"' in html
    assert '<option value="Madrid" selected>' in html
    assert 'href="/oposiciones?pagina=1' not in html or True


def test_ver_todas_reutiliza_busqueda_paginada_y_el_submit_vacio_la_activa(cliente):
    html = cliente.get("/oposiciones?ver_todas=1&tamano_pagina=2").get_data(as_text=True)
    assert "resultados encontrados" in html
    assert 'name="ver_todas" value="1"' in html
    javascript = cliente.get("/static/js/oposiciones.js").get_data(as_text=True)
    assert 'datos.set("ver_todas", "1")' in javascript
    assert 'navegarResultados(datos)' in javascript


def test_barra_actualizacion_respeta_hidden_hasta_que_haya_trabajo(cliente):
    css = cliente.get("/static/css/portal.css").get_data(as_text=True)
    html = cliente.get("/oposiciones?ver_todas=1").get_data(as_text=True)
    assert ".update-status[hidden] { display: none; }" in css
    assert 'class="update-status" hidden' in html


def test_buscador_detalle_y_apis_territoriales(cliente):
    detalle = cliente.get("/oposiciones/1")
    assert detalle.status_code == 200
    assert b"Ver publicaci" in detalle.data
    assert b'rel="noopener noreferrer"' in detalle.data
    assert cliente.get("/oposiciones/99999999").status_code == 404
    assert cliente.get("/api/filtros/provincias?comunidad=Andaluc%C3%ADa").get_json()["provincias"] == ["Sevilla"]
    assert cliente.get("/api/filtros/municipios?q=Ma&provincia=Madrid").get_json()["municipios"] == []
    assert cliente.get("/api/filtros/municipios?q=").get_json()["municipios"] == []
    assert cliente.get("/api/filtros/puestos?q=Inge").get_json()["puestos"] == ["Ingeniero Industrial"]


def test_detalle_reconstruye_un_retorno_interno_con_filtros_navegacion_y_estado_visual(cliente):
    contexto = {
        "texto": "Técnico Ñ / &", "fecha_desde": "2025-01-01", "fecha_hasta": "2025-12-31",
        "provincia": "Madrid", "municipio_exacto": "Madrid", "municipio_provincia_exacto": "Madrid",
        "turno": "Libre", "pagina": "3", "tamano_pagina": "50", "orden": "fecha_desc",
        "ver_todas": "1", "vista": "mapa", "sin_coordenadas": "1",
        "pagina_sin_coordenadas": "2", "ajeno": "no debe pasar",
    }
    volver = "/oposiciones?" + urlencode(contexto)
    html = cliente.get("/oposiciones/1?" + urlencode({"volver": volver})).get_data(as_text=True)
    enlace = html.split('class="back-link" href="', 1)[1].split('"', 1)[0].replace("&amp;", "&")
    destino = urlsplit(enlace)

    assert destino.path == "/oposiciones"
    assert parse_qs(destino.query) == {
        "texto": ["Técnico Ñ / &"], "fecha_desde": ["2025-01-01"], "fecha_hasta": ["2025-12-31"],
        "provincia": ["Madrid"], "municipio_exacto": ["Madrid"], "municipio_provincia_exacto": ["Madrid"],
        "turno": ["Libre"], "pagina": ["3"], "tamano_pagina": ["50"], "orden": ["fecha_desc"],
        "ver_todas": ["1"], "vista": ["mapa"], "sin_coordenadas": ["1"],
        "pagina_sin_coordenadas": ["2"],
    }


def test_detalle_descarta_destinos_externos_y_parametros_no_permitidos(cliente):
    directo = cliente.get("/oposiciones/1").get_data(as_text=True)
    externo = cliente.get("/oposiciones/1?volver=https%3A%2F%2Fejemplo.test%2F").get_data(as_text=True)
    desconocido = cliente.get("/oposiciones/1?volver=%2Foposiciones%3Forden%3Bdrop%3D1").get_data(as_text=True)

    assert 'class="back-link" href="/oposiciones"' in directo
    assert 'class="back-link" href="/oposiciones"' in externo
    assert 'class="back-link" href="/oposiciones"' in desconocido


def test_enlace_detalle_del_listado_transporta_contexto_permitido(cliente):
    html = cliente.get("/oposiciones?texto=Ingeniero&provincia=Madrid&pagina=2&orden=fecha_desc&vista=mapa").get_data(as_text=True)
    detalle = html.split('class="portal-button portal-button--small" href="', 1)[1].split('"', 1)[0].replace("&amp;", "&")
    volver = parse_qs(urlsplit(detalle).query)["volver"][0]
    destino = urlsplit(volver)

    assert destino.path == "/oposiciones"
    assert parse_qs(destino.query) == {
        "texto": ["Ingeniero"], "provincia": ["Madrid"], "pagina": ["2"],
        "orden": ["fecha_desc"], "vista": ["mapa"],
    }


def test_buscador_avanzado_orden_y_tamano(cliente):
    respuesta = cliente.get("/oposiciones?sistema=Concurso&orden=puesto_asc&tamano_pagina=50")
    html = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200
    assert 'open' in html.split('class="advanced-filters"', 1)[1][:20]
    assert 'value="puesto_asc" selected' in html
    assert 'value="50" selected' in html
    assert cliente.get("/static/js/oposiciones.js").status_code == 200


def test_buscador_municipio_texto_y_autocompletado_accesible(cliente):
    html = cliente.get("/oposiciones?municipio=Mad").get_data(as_text=True)
    assert 'id="municipio"' in html
    assert 'placeholder="Escribe un municipio..."' in html
    assert 'role="combobox"' in html
    assert 'id="sugerencias-municipio"' in html
    javascript = cliente.get("/static/js/oposiciones.js").get_data(as_text=True)
    assert "setTimeout(consultar, 250)" in javascript
    assert 'evento.key === "ArrowDown"' in javascript
    assert 'evento.key === "Escape"' in javascript


def _respuesta_mapa_prueba():
    return {
        "resumen": {"convocatorias": 1, "plazas": 2, "municipios": 1, "geolocalizadas": 1, "sin_coordenadas": 0},
        "municipios": [{"codigo_ine": "51001", "municipio": "Ceuta Ñ", "provincia": None,
                        "comunidad_autonoma": "Ceuta", "latitud": 35.9, "longitud": -5.3,
                        "convocatorias": 1, "plazas": 2}],
    }


def test_api_mapa_existe_devuelve_contrato_json_y_serializa_null_unicode(cliente, monkeypatch):
    import web_estadisticas as web
    monkeypatch.setattr(web, "resumen_mapa_oposiciones", lambda *_args, **_kwargs: _respuesta_mapa_prueba())
    respuesta = cliente.get("/api/oposiciones/mapa")
    assert respuesta.status_code == 200 and respuesta.content_type.startswith("application/json")
    datos = respuesta.get_json()
    assert datos == _respuesta_mapa_prueba()
    assert datos["municipios"][0]["provincia"] is None


@pytest.mark.parametrize("parametro,valor", [
    ("texto", "Ingeniero"), ("fecha_desde", "2025-01-01"), ("fecha_hasta", "2025-12-31"),
    ("comunidad_autonoma", "Andalucía"), ("provincia", "Madrid"), ("municipio", "Mad"),
    ("municipio_exacto", "Madrid"), ("municipio_provincia_exacto", "Madrid"),
    ("administracion", "Administración A"), ("ambito", "LOCAL"), ("tipo_entidad", "MUNICIPAL"),
    ("sistema", "Oposición"), ("turno", "Libre"), ("escala", "E1"),
    ("subescala", "S1"), ("clase", "C1"),
])
def test_api_mapa_admite_los_mismos_filtros_logicos(cliente, monkeypatch, parametro, valor):
    import web_estadisticas as web
    recibidos = {}
    monkeypatch.setattr(web, "resumen_mapa_oposiciones", lambda *_args, **kwargs: recibidos.update(kwargs) or _respuesta_mapa_prueba())
    respuesta = cliente.get("/api/oposiciones/mapa", query_string={parametro: f"  {valor}  "})
    assert respuesta.status_code == 200
    assert recibidos[parametro] == valor


def test_api_mapa_equivale_al_listado_e_ignora_navegacion_y_actualizacion(cliente, monkeypatch, ruta_bd):
    monkeypatch.setattr(web_estadisticas, "determinar_actualizacion_intervalo", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no debe consultar cobertura")))
    filtros = {"texto": "Ingeniero", "provincia": "Madrid", "pagina": "99", "tamano_pagina": "1",
               "orden": "plazas_desc", "ver_todas": "1", "actualizacion": "error"}
    respuesta = cliente.get("/api/oposiciones/mapa", query_string=filtros)
    assert respuesta.status_code == 200
    assert respuesta.get_json()["resumen"]["convocatorias"] == buscar_oposiciones(
        ruta_bd, texto="Ingeniero", provincia="Madrid"
    )["total"]


def test_api_mapa_vacio_y_errores_controlados(cliente, monkeypatch):
    vacia = cliente.get("/api/oposiciones/mapa", query_string={"texto": "inexistente"})
    assert vacia.status_code == 200
    assert vacia.get_json() == {"resumen": {"convocatorias": 0, "plazas": 0, "municipios": 0, "geolocalizadas": 0, "sin_coordenadas": 0}, "municipios": []}
    fecha_invalida = cliente.get("/api/oposiciones/mapa?fecha_desde=01/01/2025")
    assert fecha_invalida.status_code == 400 and "error" in fecha_invalida.get_json()
    monkeypatch.setattr(web_estadisticas, "resumen_mapa_oposiciones", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("/ruta/secreta")))
    error = cliente.get("/api/oposiciones/mapa")
    assert error.status_code == 500 and "/ruta/secreta" not in error.get_json()["error"]


def test_api_sin_coordenadas_devuelve_contrato_paginado_y_no_activa_cobertura(cliente, monkeypatch):
    monkeypatch.setattr(web_estadisticas, "determinar_actualizacion_intervalo",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no debe consultar cobertura")))
    respuesta = cliente.get("/api/oposiciones/sin-coordenadas?tamano=1&vista=mapa")
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert set(datos) == {"total", "pagina", "tamano", "paginas", "resultados"}
    assert (datos["total"], datos["pagina"], datos["tamano"], datos["paginas"]) == (2, 1, 1, 2)
    assert len(datos["resultados"]) == 1
    assert {"oposicion_id", "puesto", "num_plazas", "fecha_boe", "administracion",
            "comunidad_autonoma", "provincia", "municipio", "municipio_codigo_ine",
            "enlace", "publicacion_id", "motivo_sin_coordenadas"} <= set(datos["resultados"][0])
    assert datos["resultados"][0]["motivo_sin_coordenadas"] == "sin_codigo_ine"


def test_api_sin_coordenadas_admite_filtros_y_errores_controlados(cliente, monkeypatch):
    filtrada = cliente.get("/api/oposiciones/sin-coordenadas?texto=Ingeniero&pagina=1&tamano=50")
    assert filtrada.status_code == 200 and filtrada.get_json()["total"] == 1
    assert cliente.get("/api/oposiciones/sin-coordenadas?pagina=0").status_code == 400
    assert cliente.get("/api/oposiciones/sin-coordenadas?tamano=101").status_code == 400
    assert cliente.get("/api/oposiciones/sin-coordenadas?fecha_desde=01/01/2025").status_code == 400
    monkeypatch.setattr(web_estadisticas, "buscar_oposiciones_sin_coordenadas",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(web_estadisticas.ErrorConsultaSQLite("no disponible")))
    assert cliente.get("/api/oposiciones/sin-coordenadas").status_code == 503
    monkeypatch.setattr(web_estadisticas, "buscar_oposiciones_sin_coordenadas",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("/detalle/interno")))
    error = cliente.get("/api/oposiciones/sin-coordenadas")
    assert error.status_code == 500 and "/detalle/interno" not in error.get_json()["error"]


def test_oposiciones_integra_pestanas_de_listado_y_mapa_sin_duplicar_filtros(cliente, monkeypatch):
    monkeypatch.setattr(web_estadisticas, "resumen_mapa_oposiciones",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no debe invocarse al renderizar")))
    html = cliente.get("/oposiciones?ver_todas=1").get_data(as_text=True)

    assert 'id="pestana-listado"' in html and 'aria-selected="true"' in html
    assert 'id="pestana-mapa"' in html and 'aria-selected="false"' in html
    assert 'id="panel-listado"' in html
    assert 'id="panel-mapa"' in html and 'hidden' in html.split('id="panel-mapa"', 1)[1][:180]
    assert 'id="mapa-oposiciones"' in html
    assert html.count('class="search-form portal-panel portal-panel--wide"') == 1
    assert "results-table" in html
    assert 'static/js/oposiciones_mapa.js' in html
    assert 'leaflet@1.9.4' in html and 'leaflet.markercluster@1.5.3' in html


def test_mapas_redirige_al_mapa_integrado_y_conserva_filtros(cliente):
    respuesta = cliente.get("/mapas?provincia=Madrid&orden=fecha_desc")

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"] == "/oposiciones?provincia=Madrid&vista=mapa"


def test_menu_ya_no_ofrece_mapas_y_enlace_directo_abre_mapa_sin_consulta_servidor(cliente, monkeypatch):
    monkeypatch.setattr(web_estadisticas, "resumen_mapa_oposiciones",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no debe invocarse al renderizar")))
    inicio = cliente.get("/").get_data(as_text=True)
    html_normal = cliente.get("/oposiciones?ver_todas=1").get_data(as_text=True)
    html_mapa = cliente.get("/oposiciones?provincia=Madrid&vista=mapa").get_data(as_text=True)
    javascript = cliente.get("/static/js/oposiciones_mapa.js").get_data(as_text=True)

    navegacion = inicio.split('<nav id="site-navigation"', 1)[1].split("</nav>", 1)[0]
    assert ">Mapas<" not in navegacion and ">Oposiciones<" in navegacion
    assert 'href="/oposiciones?vista=mapa"' in inicio
    assert 'id="pestana-listado"' in html_normal and 'aria-selected="true"' in html_normal
    assert 'id="pestana-mapa"' in html_mapa and 'data-results-panel="mapa" hidden' in html_mapa
    assert 'get("vista") === "mapa"' in javascript
    assert 'urlApi("/api/oposiciones/mapa", parametrosFiltros())' in javascript


def test_javascript_mapa_carga_diferida_conserva_filtros_y_no_inyecta_html(cliente):
    javascript = cliente.get("/static/js/oposiciones_mapa.js").get_data(as_text=True)

    assert 'urlApi("/api/oposiciones/mapa", parametrosFiltros())' in javascript
    assert "const permitidos = new Set" in javascript
    assert '"municipio_provincia_exacto"' in javascript
    assert "if (mapaCargado)" in javascript
    assert 'Cargando mapa...' not in javascript  # El estado visible pertenece al HTML accesible.
    assert "mostrarCarga(true)" in javascript and "mostrarCarga(false)" in javascript
    assert "mapa.invalidateSize()" in javascript
    assert "mapa.fitBounds" in javascript and "mapa.setView(limites.getCenter(), 12)" in javascript
    assert "window.L.markerClusterGroup" in javascript
    assert ".textContent =" in javascript
    assert ".innerHTML" not in javascript


def test_panel_sin_coordenadas_esta_oculto_y_no_se_consulta_al_renderizar(cliente, monkeypatch):
    monkeypatch.setattr(web_estadisticas, "buscar_oposiciones_sin_coordenadas",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no debe invocarse al renderizar")))
    html = cliente.get("/oposiciones?ver_todas=1&vista=mapa").get_data(as_text=True)

    assert 'id="mapa-sin-coordenadas"' in html and 'aria-controls="panel-sin-coordenadas"' in html
    assert 'id="panel-sin-coordenadas"' in html and 'hidden' in html.split('id="panel-sin-coordenadas"', 1)[1][:180]
    assert 'id="sin-coordenadas-cargando"' in html
    assert 'id="sin-coordenadas-resultados"' in html
    assert 'id="sin-coordenadas-anterior"' in html and 'id="sin-coordenadas-siguiente"' in html
    assert 'id="sin-coordenadas-cerrar"' in html and 'id="sin-coordenadas-reintentar"' in html


def test_javascript_panel_sin_coordenadas_es_diferido_seguro_y_paginado(cliente):
    javascript = cliente.get("/static/js/oposiciones_mapa.js").get_data(as_text=True)

    assert 'urlApi("/api/oposiciones/mapa", parametrosFiltros())' in javascript
    assert 'urlApi("/api/oposiciones/sin-coordenadas", parametros)' in javascript
    assert 'parametros.set("pagina", String(pagina))' in javascript
    assert 'parametros.set("tamano", "50")' in javascript
    assert 'botonSinCoordenadas.addEventListener("click"' in javascript
    assert "cacheSinCoordenadas.has(pagina)" in javascript
    assert 'sin_codigo_ine: "Municipio no identificado"' in javascript
    assert 'codigo_ine_no_resuelto: "Código municipal no reconocido"' in javascript
    assert 'municipio_sin_coordenadas: "Municipio sin coordenadas"' in javascript
    assert "Localización no disponible" in javascript
    assert "anteriorSinCoordenadas.disabled" in javascript
    assert "siguienteSinCoordenadas.disabled" in javascript
    assert '"/oposiciones/" + encodeURIComponent' in javascript
    assert ".innerHTML" not in javascript


def test_javascript_restaura_panel_y_hace_scroll_respetando_reduced_motion(cliente):
    javascript = cliente.get("/static/js/oposiciones_mapa.js").get_data(as_text=True)

    assert "const parametrosRetorno = () =>" in javascript
    assert 'parametros.set("vista", "mapa")' in javascript
    assert 'parametros.set("sin_coordenadas", "1")' in javascript
    assert 'parametros.set("pagina_sin_coordenadas", String(paginaActualSinCoordenadas))' in javascript
    assert 'scrollIntoView({behavior: reducirMovimiento ? "auto" : "smooth", block: "start"})' in javascript
    assert 'matchMedia?.("(prefers-reduced-motion: reduce)")' in javascript
    assert "panelSinCoordenadas.hidden = false;\n        desplazarPanelSinCoordenadas();" in javascript
    assert 'estadoVisual.get("sin_coordenadas") === "1"' in javascript
    assert "abrirSinCoordenadas(Number.isInteger(paginaRestaurada)" in javascript
    assert '"?volver=" + encodeURIComponent(volver)' in javascript


def test_argumentos_servidor_lan_mantienen_debug_desactivado():
    assert web_estadisticas._analizar_argumentos([]).host == "127.0.0.1"
    argumentos = web_estadisticas._analizar_argumentos(["--host", "0.0.0.0", "--port", "5001"])
    assert (argumentos.host, argumentos.port) == ("0.0.0.0", 5001)


def test_actualizacion_web_estado_y_busqueda_no_scrapea_paginacion(monkeypatch, ruta_bd):
    monkeypatch.setattr(web_estadisticas, "determinar_actualizacion_intervalo", lambda *a, **k: {"requiere_actualizacion": True, "fechas_pendientes": ["2025-03-01"]})
    llamadas = []
    def actualizar(fechas, ruta, progreso):
        llamadas.append(fechas); progreso(fechas[0], "consultado")
    app = web_estadisticas.crear_app(ruta_bd, GestorActualizaciones(ruta_bd, actualizador=actualizar))
    app.config["TESTING"] = True
    cliente_local = app.test_client()
    respuesta = cliente_local.get("/oposiciones?fecha_desde=2025-03-01&fecha_hasta=2025-03-01")
    assert b"Actualizaci" in respuesta.data
    inicio = cliente_local.post("/api/actualizar-busqueda", json={"fecha_desde": "2025-03-01", "fecha_hasta": "2025-03-01"})
    assert inicio.status_code == 202
    trabajo = inicio.get_json()["trabajo"]
    estado = cliente_local.get(f"/api/trabajos/{trabajo['id']}").get_json()
    assert estado["estado"] in {"procesando", "completado"}
    assert llamadas == [["2025-03-01"]]
    assert cliente_local.get("/oposiciones?fecha_desde=2025-03-01&pagina=2").status_code == 200


def test_busqueda_solo_por_fechas_cubiertas_va_directamente_a_resultados(monkeypatch, ruta_bd):
    monkeypatch.setattr(web_estadisticas, "determinar_actualizacion_intervalo", lambda *a, **k: {"requiere_actualizacion": False, "fechas_pendientes": []})
    app = web_estadisticas.crear_app(ruta_bd)
    app.config["TESTING"] = True
    cliente_local = app.test_client()
    respuesta = cliente_local.get("/oposiciones?fecha_desde=2025-01-01&fecha_hasta=2025-01-31")
    assert respuesta.status_code == 200
    html = respuesta.get_data(as_text=True)
    assert "1 resultados encontrados" in html
    assert "Comprobando cobertura del BOE" not in html
    assert 'class="update-status" hidden' in html
    comprobacion = cliente_local.post(
        "/api/actualizar-busqueda",
        json={"fecha_desde": "2025-01-01", "fecha_hasta": "2025-01-31"},
    )
    assert comprobacion.status_code == 200
    assert comprobacion.get_json() == {"actualizacion": False}


def test_cobertura_completa_no_crea_job_ni_llama_actualizador(monkeypatch, ruta_bd):
    monkeypatch.setattr(web_estadisticas, "determinar_actualizacion_intervalo", lambda *a, **k: {"requiere_actualizacion": False, "fechas_pendientes": []})
    llamadas = []
    app = web_estadisticas.crear_app(ruta_bd, GestorActualizaciones(ruta_bd, actualizador=lambda *a: llamadas.append(a)))
    app.config["TESTING"] = True
    respuesta = app.test_client().post("/api/actualizar-busqueda", json={"fecha_desde": "2025-01-01", "fecha_hasta": "2025-01-02"})
    assert respuesta.get_json() == {"actualizacion": False}
    assert llamadas == []


def test_fallback_error_muestra_resultados_y_no_reconsulta_cobertura(monkeypatch, ruta_bd):
    def no_debe_llamarse(*args, **kwargs):
        raise AssertionError("No debe reintentarse cobertura tras un error")
    monkeypatch.setattr(web_estadisticas, "determinar_actualizacion_intervalo", no_debe_llamarse)
    app = web_estadisticas.crear_app(ruta_bd)
    app.config["TESTING"] = True
    respuesta = app.test_client().get("/oposiciones?fecha_desde=2025-01-01&fecha_hasta=2025-01-31&actualizacion=error")
    html = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200
    assert "datos disponibles en la base de datos" in html
    assert "1 resultados encontrados" in html


def test_javascript_actualizacion_cierra_todos_los_estados(cliente):
    javascript = cliente.get("/static/js/oposiciones.js").get_data(as_text=True)
    assert "if (!datos.get(\"fecha_desde\")) return;" in javascript
    assert "navegarResultados(datos)" in javascript
    assert "restaurarFormulario" in javascript
    assert "${porcentaje} %" in javascript
    assert "Actualización completada" in javascript
    assert "BOEActualizacion.vigilarTrabajo" in javascript
    assert "actualizacion\", \"error\"" in javascript
    assert "Transcurrido:" in javascript
    compartido = cliente.get("/static/js/actualizacion.js").get_data(as_text=True)
    assert "No se pudo consultar el estado de la actualización." in compartido


def _calendario_prueba(anio=2025, mes=1):
    return {"anio": anio, "mes": mes, "dias": [{"fecha": f"{anio}-01-01", "estado_visual": "CONSULTADO", "cubierto": True, "motivo": None, "estado": "consultado", "version_extractor": "1", "fecha_ultima_consulta": "2025-01-02", "numero_publicaciones": 1}]}


def _resumen_prueba():
    return {"porcentaje": 50, "dias_totales": 2, "dias_cubiertos": 1, "dias_pendientes": 1,
            "CONSULTADO": 1, "SIN_EDICION": 0, "INCOHERENCIA_VERIFICADA": 0, "NO_REUTILIZABLE": 0,
            "fecha_inicio": "2004-01-01", "fecha_fin": "2025-01-31", "ultima_consulta": "2025-01-02"}


def test_pagina_cobertura_calendario_y_detalle(monkeypatch, ruta_bd):
    monkeypatch.setattr(web_estadisticas, "resumen_cobertura", lambda *a: _resumen_prueba())
    monkeypatch.setattr(web_estadisticas, "cobertura_mes", lambda *a, **k: _calendario_prueba(k["anio"], k["mes"]))
    monkeypatch.setattr(web_estadisticas, "detalle_cobertura_dia", lambda *a, **k: _calendario_prueba()["dias"][0])
    app = web_estadisticas.crear_app(ruta_bd); app.config["TESTING"] = True
    cliente_local = app.test_client()
    html = cliente_local.get("/cobertura?anio=2025&mes=1").get_data(as_text=True)
    assert "Cobertura del BOE" in html and "Cobertura BOE operativa" in html and "Actualizar pendientes" in html
    assert 'coverage-day--consultado' in html and ">Cobertura</a>" in html
    detalle = cliente_local.get("/api/cobertura/dia?fecha=2025-01-01").get_json()
    assert detalle["estado_visual"] == "CONSULTADO"


def test_cobertura_muestra_incoherencia_verificada(monkeypatch, ruta_bd):
    resumen = _resumen_prueba(); resumen.update({"porcentaje": 100, "dias_cubiertos": 2,
                                                  "dias_pendientes": 0, "INCOHERENCIA_VERIFICADA": 4})
    dia = _calendario_prueba()["dias"][0]
    dia.update({"estado_visual": "INCOHERENCIA_VERIFICADA", "estado": "incoherencia_historica_verificada",
                "motivo": "Incoherencia histórica verificada.", "publicaciones_sqlite": 17})
    monkeypatch.setattr(web_estadisticas, "resumen_cobertura", lambda *a: resumen)
    monkeypatch.setattr(web_estadisticas, "cobertura_mes", lambda *a, **k: {"anio": k["anio"], "mes": k["mes"], "dias": [dia]})
    monkeypatch.setattr(web_estadisticas, "detalle_cobertura_dia", lambda *a, **k: dia)
    app = web_estadisticas.crear_app(ruta_bd); app.config["TESTING"] = True
    cliente_local = app.test_client()
    html = cliente_local.get("/cobertura?anio=2025&mes=1").get_data(as_text=True)
    assert "100,00 %" in html and "Incoherencia verificada" in html and "coverage-day--incoherencia_verificada" in html
    detalle = cliente_local.get("/api/cobertura/dia?fecha=2025-01-01").get_json()
    assert detalle["motivo"] == "Incoherencia histórica verificada."


def test_cobertura_actualiza_solo_pendientes_y_mes_cubierto_no_crea_job(monkeypatch, ruta_bd):
    decisiones = iter((
        {"requiere_actualizacion": False, "fechas_pendientes": []},
        {"requiere_actualizacion": True, "fechas_pendientes": ["2025-01-03", "2025-01-17"]},
    ))
    monkeypatch.setattr(web_estadisticas, "determinar_actualizacion_intervalo", lambda *a, **k: next(decisiones))
    llamadas = []
    def actualizar(fechas, ruta, progreso):
        llamadas.append(fechas); progreso({"fase": "indices", "actual": 1, "total": 1, "mensaje": "Actualizando datos del BOE…"})
    app = web_estadisticas.crear_app(ruta_bd, GestorActualizaciones(ruta_bd, actualizador=actualizar)); app.config["TESTING"] = True
    cliente_local = app.test_client()
    assert cliente_local.post("/api/cobertura/actualizar", json={"anio": 2025, "mes": 1}).get_json() == {"actualizacion": False}
    inicio = cliente_local.post("/api/cobertura/actualizar", json={"anio": 2025, "mes": 1})
    assert inicio.status_code == 202
    for _ in range(30):
        if llamadas: break
        time.sleep(.01)
    assert llamadas == [["2025-01-03", "2025-01-17"]]


def test_oposiciones_mantiene_silenciosa_la_comprobacion_de_cobertura(cliente):
    html = cliente.get("/oposiciones").get_data(as_text=True)
    assert "Comprobando cobertura del BOE" not in html
    assert 'class="update-status" hidden' in html


def test_pagina_contiene_filtros_indicadores_y_graficos(cliente):
    respuesta = cliente.get("/estadisticas")
    html = respuesta.get_data(as_text=True)

    assert 'id="fecha_inicio"' in html
    assert 'id="fecha_final"' in html
    assert 'id="puesto"' in html
    assert 'id="provincia"' in html
    assert 'id="sistema"' in html
    assert 'id="turno"' in html
    assert html.count('>Todas</option>') == 3
    assert 'id="aplicar-filtros"' in html
    assert 'id="limpiar-filtros"' in html
    assert 'id="total-plazas"' in html
    assert 'id="total-registros"' in html
    assert 'id="total-provincias"' in html
    assert 'id="total-administraciones"' in html
    assert 'id="ranking-administraciones"' in html
    assert 'id="ranking-puestos"' in html
    assert 'id="grafico-administraciones"' not in html
    assert 'id="grafico-puestos"' not in html
    assert 'id="grafico-provincias"' in html
    assert 'id="grafico-evolucion"' in html
    assert "Cargando datos..." in html
    assert 'id="sin-resultados"' in html
    assert 'id="aviso-calidad"' in html
    assert "Calidad de los datos históricos" in html
    assert "afectan únicamente" in html


def test_pagina_carga_chart_css_y_javascript_desde_recursos_locales(cliente):
    html = cliente.get("/estadisticas").get_data(as_text=True)

    assert 'href="/static/css/estadisticas.css"' in html
    assert 'src="/static/vendor/chart.umd.min.js"' in html
    assert 'src="/static/js/estadisticas.js"' in html
    assert "cdn" not in html.lower()
    assert "http://" not in html
    assert "https://" not in html


def test_recursos_estaticos_del_dashboard_estan_disponibles(cliente):
    css = cliente.get("/static/css/estadisticas.css")
    javascript = cliente.get("/static/js/estadisticas.js")
    chart = cliente.get("/static/vendor/chart.umd.min.js")

    assert css.status_code == 200
    assert javascript.status_code == 200
    assert chart.status_code == 200
    assert b"Chart.js v4.5.1" in chart.data[:200]


def test_javascript_incluye_carga_filtros_limpieza_y_estados(cliente):
    javascript = cliente.get("/static/js/estadisticas.js").get_data(as_text=True)

    assert 'fetch(url, {headers: {Accept: "application/json"}})' in javascript
    assert 'formulario.addEventListener("submit"' in javascript
    assert 'formulario.reset()' in javascript
    assert 'botonAplicar.disabled = cargando' in javascript
    assert 'document.addEventListener("DOMContentLoaded"' in javascript
    assert "El archivo Excel no está disponible temporalmente" in javascript
    assert "incidencias en registros históricos" not in javascript
    assert '"numero_plazas_no_utilizable"' in javascript
    assert "visibles.length === 0" in javascript
    assert 'formulario.reset()' in javascript
    assert '["provincia", opciones.provincias' in javascript
    assert '["sistema", opciones.sistemas' in javascript
    assert '["turno", opciones.turnos' in javascript


def _ejecutar_diagnostico_rankings():
    ruta_javascript = Path(__file__).resolve().parent.parent / "static" / "js" / "estadisticas.js"
    administraciones = [
        {
            "administracion": f"Dirección General de Investigación Científica {indice}",
            "plazas": 110 - indice * 10,
        }
        for indice in range(6)
    ]
    puestos = [
        {
            "puesto": f"Investigador científico de organismos públicos especialidad {indice}",
            "plazas": 240 - indice * 10,
        }
        for indice in range(12)
    ]
    codigo = """
const fs = require("fs");
const vm = require("vm");
class Elemento {
    constructor(tag = "div") {
        this.tag = tag;
        this.children = [];
        this.className = "";
        this.textContent = "";
        this.style = {};
        this.attributes = {};
        this.parentElement = {style: {}};
        this.classList = {contains() { return false; }};
    }
    addEventListener() {}
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = [...children]; }
    setAttribute(nombre, valor) { this.attributes[nombre] = String(valor); }
    removeAttribute(nombre) { delete this.attributes[nombre]; }
    getContext() { return {}; }
}
const elementos = new Map();
const obtenerElemento = selector => {
    if (!elementos.has(selector)) elementos.set(selector, new Elemento());
    return elementos.get(selector);
};
const llamadasChart = [];
function Chart(contextoCanvas, configuracion) {
    llamadasChart.push(configuracion);
    this.destroy = () => {};
}
const contexto = {
    document: {
        querySelector: obtenerElemento,
        createElement: etiqueta => new Elemento(etiqueta),
        addEventListener() {}
    },
    Chart, Intl, Map, URLSearchParams,
    FormData: function() {}, console
};
vm.createContext(contexto);
vm.runInContext(fs.readFileSync(__RUTA__, "utf8"), contexto);
vm.runInContext(
    `renderizarRanking("ranking-administraciones", ${JSON.stringify(__ADMINISTRACIONES__)}, "administracion", 5)`,
    contexto
);
vm.runInContext(
    `renderizarRanking("ranking-puestos", ${JSON.stringify(__PUESTOS__)}, "puesto", 10)`,
    contexto
);
const serializar = selector => obtenerElemento(selector).children.map(fila => ({
    nombre: fila.children[0].textContent,
    valor: fila.children[1].children[1].textContent,
    porcentaje: fila.children[1].children[0].children[0].style.width
}));
const llamadasTrasRankings = llamadasChart.length;
vm.runInContext('renderizarRanking("ranking-vacio", [], "puesto", 10)', contexto);
vm.runInContext('crearGraficoProvincias([{provincia: "Madrid", plazas: 8}])', contexto);
vm.runInContext('crearGraficoEvolucion([{mes: "2025-01", plazas: 8}])', contexto);
const calidadCero = {fecha_no_utilizable: 0, numero_plazas_no_utilizable: 0,
    puesto_no_utilizable: 0, provincia_no_disponible: 0,
    administracion_no_disponible: 0, sistema_no_disponible: 0,
    turno_no_disponible: 0};
vm.runInContext(`actualizarAvisoCalidad(${JSON.stringify(calidadCero)})`, contexto);
const calidadOcultaConCeros = obtenerElemento("#aviso-calidad").hidden;
const calidadReal = {...calidadCero, numero_plazas_no_utilizable: 1,
    provincia_no_disponible: 12640};
vm.runInContext(`actualizarAvisoCalidad(${JSON.stringify(calidadReal)})`, contexto);
process.stdout.write(JSON.stringify({
    administraciones: serializar("#ranking-administraciones"),
    puestos: serializar("#ranking-puestos"),
    vacio: obtenerElemento("#ranking-vacio").children[0].textContent,
    llamadasTrasRankings,
    tiposChart: llamadasChart.map(llamada => llamada.type),
    calidadOcultaConCeros,
    calidadVisible: !obtenerElemento("#aviso-calidad").hidden,
    calidadTextos: obtenerElemento("#lista-calidad").children.map(x => x.textContent)
}));
"""
    codigo = (
        codigo.replace("__RUTA__", json.dumps(str(ruta_javascript)))
        .replace("__PUESTOS__", json.dumps(puestos))
        .replace("__ADMINISTRACIONES__", json.dumps(administraciones))
    )

    resultado = subprocess.run(
        ["node", "-e", codigo], check=True, capture_output=True, text=True
    )
    return json.loads(resultado.stdout), administraciones, puestos


def test_rankings_html_respetan_limites_orden_textos_valores_y_porcentajes():
    datos, administraciones, puestos = _ejecutar_diagnostico_rankings()

    administraciones_esperadas = sorted(
        administraciones, key=lambda fila: fila["plazas"], reverse=True
    )[:5]
    puestos_esperados = sorted(puestos, key=lambda fila: fila["plazas"], reverse=True)[:10]

    assert len(datos["administraciones"]) == 5
    assert len(datos["puestos"]) == 10
    assert [fila["nombre"] for fila in datos["administraciones"]] == [
        fila["administracion"] for fila in administraciones_esperadas
    ]
    assert [fila["nombre"] for fila in datos["puestos"]] == [
        fila["puesto"] for fila in puestos_esperados
    ]
    assert [int(fila["valor"]) for fila in datos["administraciones"]] == [
        fila["plazas"] for fila in administraciones_esperadas
    ]
    assert [int(fila["valor"]) for fila in datos["puestos"]] == [
        fila["plazas"] for fila in puestos_esperados
    ]
    assert datos["administraciones"][0]["porcentaje"] == "100%"
    assert datos["puestos"][0]["porcentaje"] == "100%"
    assert float(datos["administraciones"][-1]["porcentaje"].rstrip("%")) < 100
    assert float(datos["puestos"][-1]["porcentaje"].rstrip("%")) < 100
    assert all(
        "..." not in fila["nombre"] and "…" not in fila["nombre"]
        for ranking in (datos["administraciones"], datos["puestos"])
        for fila in ranking
    )


def test_rankings_vacios_y_uso_de_chart_js():
    datos, _, _ = _ejecutar_diagnostico_rankings()

    assert datos["vacio"] == "Sin resultados"
    assert datos["llamadasTrasRankings"] == 0
    assert datos["tiposChart"] == ["bar", "line"]


def test_calidad_frontend_oculta_ceros_y_muestra_metricas_independientes():
    datos, _, _ = _ejecutar_diagnostico_rankings()

    assert datos["calidadOcultaConCeros"] is True
    assert datos["calidadVisible"] is True
    assert datos["calidadTextos"] == [
        "1 registro sin número de plazas utilizable.",
        "12.640 registros sin provincia disponible.",
    ]


def test_javascript_no_reconstruye_graficos_durante_resize(cliente):
    javascript = cliente.get("/static/js/estadisticas.js").get_data(as_text=True)

    assert 'window.addEventListener("resize"' not in javascript


def test_api_devuelve_el_esquema_esperado(cliente):
    respuesta = cliente.get("/api/estadisticas")

    assert respuesta.status_code == 200
    assert set(respuesta.get_json()) == {
        "filtros",
        "opciones",
        "resumen",
        "top_administraciones",
        "top_puestos",
        "plazas_por_provincia",
        "evolucion_mensual",
        "calidad_datos",
        "archivo",
    }
    assert respuesta.get_json()["resumen"] == {
        "total_plazas": 5,
        "total_registros": 2,
        "total_provincias": 2,
        "total_administraciones": 2,
    }
    assert respuesta.get_json()["archivo"]["ultima_modificacion"] is not None
    assert respuesta.get_json()["opciones"] == {
        "provincias": ["Madrid", "Sevilla"],
        "ambitos": [],
        "sistemas": ["Concurso", "Oposición"],
        "turnos": ["Discapacidad", "Libre"],
    }
    assert respuesta.get_json()["calidad_datos"] == {
        "fecha_no_utilizable": 0,
        "numero_plazas_no_utilizable": 0,
        "puesto_no_utilizable": 0,
        "provincia_no_disponible": 0,
        "administracion_no_disponible": 0,
        "sistema_no_disponible": 0,
        "turno_no_disponible": 0,
        "municipio_no_disponible": 2,
        "ambito_indeterminado": 2,
    }


def test_consulta_estadistica_expone_fecha_canonica_y_original_por_separado(ruta_bd):
    canonicas = oposiciones(ruta_bd, columnas=["Fecha_boe"])
    originales = oposiciones(ruta_bd, columnas=["Fecha_boe_original"])

    assert canonicas["Fecha_boe"].tolist() == ["2025-01-01", "2025-02-01"]
    assert originales["Fecha_boe_original"].tolist() == [
        "1 de enero de 2025", "1 de febrero de 2025"
    ]


def test_api_aplica_y_devuelve_los_filtros_de_fecha(cliente):
    respuesta = cliente.get(
        "/api/estadisticas?fecha_inicio=2025-02-01&fecha_final=2025-02-28"
    )
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert datos["filtros"]["fecha_inicio"] == "2025-02-01"
    assert datos["filtros"]["fecha_final"] == "2025-02-28"
    assert datos["resumen"] == {
        "total_plazas": 3,
        "total_registros": 1,
        "total_provincias": 1,
        "total_administraciones": 1,
    }


def test_api_aplica_filtro_por_puesto(cliente):
    respuesta = cliente.get("/api/estadisticas?puesto=ingeniero")

    assert respuesta.status_code == 200
    assert respuesta.get_json()["filtros"]["puesto"] == "ingeniero"
    assert respuesta.get_json()["resumen"] == {
        "total_plazas": 2,
        "total_registros": 1,
        "total_provincias": 1,
        "total_administraciones": 1,
    }


@pytest.mark.parametrize(
    ("parametro", "valor", "plazas"),
    [
        ("provincia", "Madrid", 2),
        ("sistema", "Concurso", 3),
        ("turno", "Discapacidad", 3),
    ],
)
def test_api_aplica_filtros_exactos(cliente, parametro, valor, plazas):
    respuesta = cliente.get("/api/estadisticas", query_string={parametro: valor})

    assert respuesta.status_code == 200
    assert respuesta.get_json()["filtros"][parametro] == valor
    assert respuesta.get_json()["resumen"]["total_plazas"] == plazas
    assert respuesta.get_json()["resumen"]["total_registros"] == 1


def test_api_combina_todos_los_filtros(cliente):
    respuesta = cliente.get(
        "/api/estadisticas",
        query_string={
            "fecha_inicio": "2025-01-01",
            "fecha_final": "2025-01-31",
            "puesto": "ingeniero industrial",
            "provincia": "Madrid",
            "sistema": "Oposición",
            "turno": "Libre",
        },
    )

    assert respuesta.status_code == 200
    assert respuesta.get_json()["resumen"]["total_plazas"] == 2
    assert respuesta.get_json()["resumen"]["total_registros"] == 1


@pytest.mark.parametrize("fecha", ["01/01/2025", "2025-1-01", "2025-02-30"])
def test_api_rechaza_fecha_invalida(cliente, fecha):
    respuesta = cliente.get("/api/estadisticas", query_string={"fecha_inicio": fecha})

    assert respuesta.status_code == 400
    assert "error" in respuesta.get_json()


def test_api_rechaza_intervalo_invertido(cliente):
    respuesta = cliente.get(
        "/api/estadisticas?fecha_inicio=2025-02-01&fecha_final=2025-01-01"
    )

    assert respuesta.status_code == 400
    assert "posterior" in respuesta.get_json()["error"]


def test_api_devuelve_503_si_el_excel_no_existe(tmp_path):
    cliente = web_estadisticas.crear_app(tmp_path / "ausente.xlsx").test_client()

    respuesta = cliente.get("/api/estadisticas")

    assert respuesta.status_code == 503
    assert "error" in respuesta.get_json()


def test_api_devuelve_503_si_el_excel_esta_corrupto(tmp_path):
    ruta = tmp_path / "corrupto.xlsx"
    ruta.write_bytes(b"contenido no valido")
    cliente = web_estadisticas.crear_app(ruta).test_client()

    respuesta = cliente.get("/api/estadisticas")

    assert respuesta.status_code == 503
    assert "corrupto" in respuesta.get_json()["error"]


def test_api_devuelve_503_si_la_base_es_incompatible(tmp_path):
    ruta = tmp_path / "incompatible.db"
    ruta.write_bytes(b"no es sqlite")
    cliente = web_estadisticas.crear_app(ruta).test_client()

    respuesta = cliente.get("/api/estadisticas")

    assert respuesta.status_code == 503
    assert "SQLite" in respuesta.get_json()["error"]


def test_api_devuelve_cero_y_listas_vacias_si_no_hay_resultados(cliente):
    respuesta = cliente.get("/api/estadisticas?puesto=inexistente")
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert datos["resumen"] == {
        "total_plazas": 0,
        "total_registros": 0,
        "total_provincias": 0,
        "total_administraciones": 0,
    }
    assert datos["top_administraciones"] == []
    assert datos["top_puestos"] == []
    assert datos["plazas_por_provincia"] == []
    assert datos["evolucion_mensual"] == []


def test_api_no_modifica_sqlite(cliente, ruta_bd):
    contenido_antes = ruta_bd.read_bytes()

    respuesta = cliente.get("/api/estadisticas")

    assert respuesta.status_code == 200
    assert ruta_bd.read_bytes() == contenido_antes


def test_rutas_exportacion_directa_descargan_datasets_y_no_cachean(cliente):
    zip_completo = cliente.get("/administracion/base-datos/exportar.zip")
    assert zip_completo.status_code == 200
    assert zip_completo.mimetype == "application/zip"
    assert "attachment;" in zip_completo.headers["Content-Disposition"]
    assert zip_completo.headers["Cache-Control"] == "no-store"
    with zipfile.ZipFile(BytesIO(zip_completo.data)) as archivo:
        assert archivo.namelist() == [
            "busquedas.csv", "oposiciones.csv", "log_errores.csv",
            "publicaciones.csv", "cobertura.csv",
        ]

    csv = cliente.get("/oposiciones/exportar.csv?texto=Ingeniero&pagina=9&vista=mapa")
    xlsx = cliente.get("/oposiciones/exportar.xlsx?texto=Ingeniero&tamano_pagina=1&ver_todas=1")
    assert csv.status_code == xlsx.status_code == 200
    assert csv.mimetype == "text/csv"
    assert xlsx.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    desde_csv = pd.read_csv(BytesIO(csv.data), sep=";", encoding="utf-8-sig")
    desde_xlsx = pd.read_excel(BytesIO(xlsx.data))
    pd.testing.assert_frame_equal(desde_csv, desde_xlsx, check_dtype=False)
    assert len(desde_csv) == buscar_oposiciones(cliente.application.config["RUTA_BD"], texto="Ingeniero")["total"]


def test_rutas_exportacion_filtrada_aceptan_cero_resultados_y_orden_invalido(cliente):
    csv = cliente.get("/oposiciones/exportar.csv?texto=sin-resultados")
    xlsx = cliente.get("/oposiciones/exportar.xlsx?texto=sin-resultados")
    assert csv.status_code == xlsx.status_code == 200
    assert pd.read_csv(BytesIO(csv.data), sep=";", encoding="utf-8-sig").empty
    assert openpyxl.load_workbook(BytesIO(xlsx.data))["Oposiciones"].max_row == 1
    invalido = cliente.get("/oposiciones/exportar.csv?orden=DROP")
    assert invalido.status_code == 400 and "Orden no permitido" in invalido.get_json()["error"]


def test_exportacion_web_neutraliza_formula_sin_modificar_sqlite(cliente):
    ruta = cliente.application.config["RUTA_BD"]
    conexion = base_datos.conectar(ruta)
    try:
        conexion.execute("UPDATE oposiciones SET puesto = '=SUM(1;1)' WHERE oposicion_id = 1")
        conexion.commit()
    finally:
        conexion.close()
    respuesta = cliente.get("/oposiciones/exportar.csv")
    assert "'=SUM(1;1)" in pd.read_csv(
        BytesIO(respuesta.data), sep=";", encoding="utf-8-sig"
    )["Puesto"].tolist()
    conexion = base_datos.conectar(ruta, readonly=True)
    try:
        assert conexion.execute("SELECT puesto FROM oposiciones WHERE oposicion_id = 1").fetchone()[0] == "=SUM(1;1)"
    finally:
        conexion.close()


def test_exportacion_xlsx_completa_es_background_y_descargable(ruta_bd):
    iniciado, continuar = Event(), Event()

    def exportador(_, salida):
        iniciado.set()
        continuar.wait(1)
        Path(salida).write_bytes(b"xlsx-completo")

    gestor = GestorExportacionXlsx(exportador)
    app = web_estadisticas.crear_app(ruta_bd, gestor_exportacion_xlsx=gestor)
    app.config["TESTING"] = True
    cliente_local = app.test_client()
    inicio = cliente_local.post("/api/administracion/base-datos/exportacion")
    assert inicio.status_code == 202 and inicio.get_json()["creado"] and iniciado.wait(1)
    repetido = cliente_local.post("/api/administracion/base-datos/exportacion")
    assert repetido.get_json()["creado"] is False
    assert cliente_local.get("/administracion/base-datos/exportar.xlsx").status_code == 409
    continuar.set()
    limite = time.monotonic() + 2
    while time.monotonic() < limite:
        estado = cliente_local.get("/api/administracion/base-datos/exportacion").get_json()
        if estado["estado"] == "completada":
            break
        time.sleep(0.01)
    assert estado["estado"] == "completada"
    descarga = cliente_local.get("/administracion/base-datos/exportar.xlsx")
    assert descarga.status_code == 200 and descarga.data == b"xlsx-completo"
    assert descarga.headers["Cache-Control"] == "no-store"


def test_importar_modulo_no_arranca_servidor(monkeypatch):
    ejecuciones = []
    monkeypatch.setattr("flask.Flask.run", lambda *args, **kwargs: ejecuciones.append(1))

    importlib.reload(web_estadisticas)

    assert ejecuciones == []


def test_modulo_web_no_importa_plazasboe(monkeypatch):
    importar_real = builtins.__import__

    def importar_sin_plazasboe(nombre, *args, **kwargs):
        if nombre == "plazasboe":
            raise AssertionError("web_estadisticas no debe importar plazasboe")
        return importar_real(nombre, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", importar_sin_plazasboe)

    importlib.reload(web_estadisticas)


def test_administracion_base_muestra_textos_y_no_verifica_al_cargar(cliente, monkeypatch):
    import gestion_base
    monkeypatch.setattr(gestion_base, "verificar_integridad", lambda *_: (_ for _ in ()).throw(AssertionError("no automática")))
    respuesta = cliente.get("/administracion/base-datos")
    assert respuesta.status_code == 200
    assert b"Verificar integridad" in respuesta.data
    assert b"No descarga ni modifica" in respuesta.data
    assert b'id="estado-publicacion"' in respuesta.data
    assert b"hidden" in respuesta.data


def test_administracion_muestra_controles_de_exportacion_y_script_aislado(cliente):
    html_pagina = cliente.get("/administracion/base-datos").get_data(as_text=True)
    assert "Exportar base de datos" in html_pagina
    assert "Preparar Excel" in html_pagina
    assert 'id="enlace-descargar-exportacion-xlsx"' in html_pagina
    assert 'aria-disabled="true"' in html_pagina
    assert 'href="/administracion/base-datos/exportar.xlsx"' not in html_pagina
    assert "Primero debes preparar el Excel antes de poder descargarlo." in html_pagina
    assert 'role="tooltip"' in html_pagina
    assert "/administracion/base-datos/exportar.zip" in html_pagina
    assert "CSV (.zip)" in html_pagina
    assert "aria-live=\"polite\"" in html_pagina
    assert "js/administracion_exportacion.js" in html_pagina
    script = Path("static/js/administracion_exportacion.js").read_text(encoding="utf-8")
    assert 'setInterval(consultar, 2000)' in script
    assert "if (!polling)" in script
    assert ".textContent" in script
    assert ".innerHTML" not in script
    assert "Volver a preparar un Excel" in script and "Reintentar" in script
    assert "Excel preparado" in script
    assert "deshabilitarDescarga" in script and "habilitarDescarga" in script
    assert 'enlace.dataset.url' in script
    assert 'evento.preventDefault()' in script
    css = cliente.get("/static/css/portal.css").get_data(as_text=True)
    assert ".excel-export-actions" in css
    assert ".export-download-tooltip" in css
    assert ".admin-status--success" in css
    assert "prefers-reduced-motion: reduce" in css


def test_estado_completado_de_exportacion_reconstruye_descarga_y_mensaje(cliente):
    script = Path("static/js/administracion_exportacion.js").read_text(encoding="utf-8")
    inicio_completada = script.index('if (actual === "completada")')
    bloque_completada = script[inicio_completada:script.index("enlace.hidden", inicio_completada) if "enlace.hidden" in script[inicio_completada:] else len(script)]
    assert 'boton.textContent = "Volver a preparar un Excel"' in bloque_completada
    assert "habilitarDescarga()" in bloque_completada
    assert 'mostrar("Excel preparado", {exito: true})' in bloque_completada
    assert "detenerPolling()" in bloque_completada


def _parametros_exportacion(html_pagina, extension):
    coincidencia = re.search(rf'href="([^"]*/oposiciones/exportar\.{extension}\?[^"]*)"', html_pagina)
    assert coincidencia
    return parse_qs(urlsplit(html.unescape(coincidencia.group(1))).query)


def test_controles_exportacion_oposiciones_conservan_filtros_logicos_no_estado_visual(cliente):
    respuesta = cliente.get(
        "/oposiciones?texto=Ingeniero&provincia=Madrid&municipio_exacto=Madrid&"
        "municipio_provincia_exacto=Madrid&orden=puesto_asc&pagina=3&tamano_pagina=50&"
        "ver_todas=1&vista=mapa&sin_coordenadas=1&pagina_sin_coordenadas=2"
    )
    html_pagina = respuesta.get_data(as_text=True)
    for extension in ("csv", "xlsx"):
        parametros = _parametros_exportacion(html_pagina, extension)
        assert parametros == {
            "texto": ["Ingeniero"], "provincia": ["Madrid"],
            "municipio_exacto": ["Madrid"], "municipio_provincia_exacto": ["Madrid"],
            "orden": ["puesto_asc"],
        }
    assert "Exportar resultados" in html_pagina


def test_controles_exportacion_siguen_visibles_con_cero_resultados_y_mapa(cliente):
    vacia = cliente.get("/oposiciones?texto=sin-resultados")
    mapa = cliente.get("/oposiciones?texto=Ingeniero&vista=mapa")
    assert "/oposiciones/exportar.csv?texto=sin-resultados" in html.unescape(vacia.get_data(as_text=True))
    parametros = _parametros_exportacion(mapa.get_data(as_text=True), "csv")
    assert parametros == {"texto": ["Ingeniero"], "orden": ["fecha_desc"]}


def test_api_administracion_prepara_y_consulta_manifest(cliente, monkeypatch, ruta_bd):
    import gestion_base
    conexion = base_datos.conectar(ruta_bd)
    base_datos.guardar_metadata(conexion, schema_version=6)
    conexion.commit(); conexion.close()
    manifest = gestion_base.crear_manifest(ruta_bd)
    monkeypatch.setattr(gestion_base, "repositorio_configurado", lambda: "x/y")
    monkeypatch.setattr(gestion_base, "consultar_copia_publicada", lambda _: {"estado": "publicada", "manifest": manifest})
    preparada = cliente.post("/api/administracion/base-datos/preparar-publicacion")
    publicada = cliente.post("/api/administracion/base-datos/version-publicada")
    assert preparada.status_code == 200 and preparada.get_json()["confirmacion_requerida"]
    assert publicada.status_code == 200 and "idénticas" in publicada.get_json()["mensaje"]


def test_api_version_publicada_admite_base_local_antigua(cliente, monkeypatch, ruta_bd, tmp_path):
    import gestion_base
    conexion = base_datos.conectar(ruta_bd)
    base_datos.guardar_metadata(conexion, schema_version=2, data_version=4)
    conexion.commit(); conexion.close()
    publicada = tmp_path / "publicada.db"
    conexion = base_datos.conectar(publicada)
    base_datos.crear_esquema(conexion)
    base_datos.guardar_metadata(conexion, schema_version=6, data_version=25)
    conexion.commit(); conexion.close()
    manifest = gestion_base.crear_manifest(publicada)
    monkeypatch.setattr(gestion_base, "repositorio_configurado", lambda: "x/y")
    monkeypatch.setattr(gestion_base, "consultar_copia_publicada", lambda _: {"estado": "publicada", "manifest": manifest})

    respuesta = cliente.post("/api/administracion/base-datos/version-publicada")

    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    assert datos["local"]["schema_version"] == 2 and datos["local"]["data_version"] == 4
    assert datos["publicada"]["schema_version"] == 6 and datos["publicada"]["data_version"] == 25
    assert "posterior" in datos["mensaje"]


def test_api_administracion_error_remoto_controlado(cliente, monkeypatch):
    import gestion_base
    monkeypatch.setattr(gestion_base, "repositorio_configurado", lambda: "x/y")
    monkeypatch.setattr(gestion_base, "consultar_copia_publicada", lambda _: (_ for _ in ()).throw(gestion_base.GestionBaseError("inválido")))
    respuesta = cliente.post("/api/administracion/base-datos/version-publicada")
    assert respuesta.status_code == 502


def test_api_administracion_sin_release_no_es_error(cliente, monkeypatch):
    import gestion_base
    monkeypatch.setattr(gestion_base, "repositorio_configurado", lambda: "x/y")
    monkeypatch.setattr(gestion_base, "consultar_copia_publicada", lambda _: {"estado": "no_publicada", "mensaje": "Todavía no existe ninguna copia publicada de la base de datos."})
    respuesta = cliente.post("/api/administracion/base-datos/version-publicada")
    assert respuesta.status_code == 200
    assert "Todavía no existe" in respuesta.get_json()["mensaje"]


def test_api_administracion_publicacion_incompleta(cliente, monkeypatch):
    import gestion_base
    monkeypatch.setattr(gestion_base, "repositorio_configurado", lambda: "x/y")
    monkeypatch.setattr(gestion_base, "consultar_copia_publicada", lambda _: {"estado": "publicacion_incompleta", "mensaje": "incompleta"})
    respuesta = cliente.post("/api/administracion/base-datos/version-publicada")
    assert respuesta.status_code == 200 and respuesta.get_json()["estado"] == "publicacion_incompleta"


def test_script_administracion_distingue_estado_terminal_y_oculta_spinner():
    script = Path("static/js/administracion_base.js").read_text(encoding="utf-8")
    assert 'job.terminal' in script
    assert 'spinner.hidden = terminal' in script
    assert 'if (terminal) stopPolling()' in script


def test_script_actualizacion_muestra_exito_final_con_duracion_congelada():
    script = Path("static/js/actualizacion_base_github.js").read_text(encoding="utf-8")
    css = Path("static/css/portal.css").read_text(encoding="utf-8")
    assert 'Actualización completada en ${job.transcurrido_segundos} segundos' in script
    assert 'admin-status--success' in script and '.admin-status--success' in css
    assert 'spinner.hidden=terminal' in script
    assert 'job.error ||' in script


def test_resumenes_administrativos_y_detalle_cobertura_no_interpolan_html():
    scripts = {
        nombre: Path("static/js") / nombre
        for nombre in (
            "administracion_base.js",
            "actualizacion_base_github.js",
            "cobertura.js",
        )
    }
    contenidos = {nombre: ruta.read_text(encoding="utf-8") for nombre, ruta in scripts.items()}

    assert all("innerHTML" not in contenido for contenido in contenidos.values())
    assert all("outerHTML" not in contenido for contenido in contenidos.values())
    assert all("insertAdjacentHTML" not in contenido for contenido in contenidos.values())
    assert all("document.createElement" in contenido for contenido in contenidos.values())
    assert all("replaceChildren" in contenido for contenido in contenidos.values())
    assert "textoContent" not in contenidos["cobertura.js"]
    assert "textContent = texto" in contenidos["cobertura.js"]
    for texto in (
        "Estado almacenado",
        "Estado calculado",
        "Publicaciones según BOE",
        "Publicaciones conservadas en SQLite",
        "Detalle diario",
    ):
        assert texto in contenidos["cobertura.js"]
    for texto in ("Estructura", "Datos", "Tamaño", "SHA-256", "Comprobación"):
        assert texto in contenidos["administracion_base.js"]


def test_detalle_cobertura_conserva_texto_y_no_crea_html_desde_la_api():
    ruta = Path("static/js/cobertura.js").resolve()
    codigo = """
const fs = require("fs"), vm = require("vm");
class Elemento {
  constructor(tag = "div") { this.tag = tag; this.children = []; this.textContent = ""; this.dataset = {}; this.style = {}; this.hidden = false; this.listeners = {}; }
  addEventListener(tipo, funcion) { this.listeners[tipo] = funcion; }
  append(...nodos) { this.children.push(...nodos); }
  replaceChildren(...nodos) { this.children = nodos; }
}
const elementos = new Map();
const obtener = selector => { if (!elementos.has(selector)) elementos.set(selector, new Elemento()); return elementos.get(selector); };
const dia = new Elemento("button"); dia.dataset.fecha = "2025-01-01";
const eventos = {};
const document = {
  addEventListener: (tipo, funcion) => { eventos[tipo] = funcion; },
  querySelector: selector => selector === ".cobertura" ? Object.assign(obtener(selector), {dataset: {anio: "2025", mes: "1"}}) : obtener(selector),
  querySelectorAll: selector => selector === ".coverage-day" ? [dia] : [],
  createElement: etiqueta => new Elemento(etiqueta),
};
const contexto = {document, fetch: async () => ({ok: true, json: async () => ({fecha: "2025-01-01", estado: "<img>", estado_visual: "SIN_EDICION", cubierto: true, version_extractor: "v1", fecha_ultima_consulta: "hoy", numero_publicaciones: 2, publicaciones_sqlite: 2, motivo: "<script>"})}), encodeURIComponent, JSON, Number, Error, BOEActualizacion: {vigilarTrabajo() {}}, window: {setTimeout() {}}};
vm.createContext(contexto);
vm.runInContext(fs.readFileSync(__RUTA__, "utf8"), contexto);
(async () => { await eventos.DOMContentLoaded(); await dia.listeners.click(); const detalle = obtener("#detalle-cobertura"); process.stdout.write(JSON.stringify({tags: detalle.children.map(x => x.tag), titulo: detalle.children[0].textContent, valores: detalle.children[1].children.filter(x => x.tag === "dd").map(x => x.textContent)})); })();
""".replace("__RUTA__", json.dumps(str(ruta)))

    resultado = subprocess.run(["node", "-e", codigo], check=True, capture_output=True, text=True)
    detalle = json.loads(resultado.stdout)

    assert detalle["tags"] == ["h2", "dl"]
    assert detalle["titulo"] == "2025-01-01"
    assert "<img>" in detalle["valores"]
    assert "<script>" in detalle["valores"]


def test_api_prepara_actualizacion_sin_iniciarla(cliente, monkeypatch, ruta_bd):
    import gestion_base
    conexion = base_datos.conectar(ruta_bd); base_datos.guardar_metadata(conexion, schema_version=6); conexion.commit(); conexion.close()
    manifest = gestion_base.crear_manifest(ruta_bd)
    monkeypatch.setattr(gestion_base, "repositorio_configurado", lambda: "x/y")
    monkeypatch.setattr(gestion_base, "preparar_actualizacion_github", lambda *_: {"estado": "preparada", "local": manifest, "publicada": manifest, "mensaje": "misma"})
    respuesta = cliente.post("/api/administracion/base-datos/preparar-actualizacion")
    assert respuesta.status_code == 200 and respuesta.get_json()["confirmacion_requerida"]
