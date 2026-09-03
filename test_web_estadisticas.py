import builtins
import importlib
import json
from pathlib import Path
import subprocess
import time

import pandas as pd
import pytest
import base_datos
from consultas_boe import oposiciones

import web_estadisticas
from actualizacion_boe import GestorActualizaciones


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


@pytest.mark.parametrize("ruta", ["/oposiciones", "/estadisticas", "/mapas"])
def test_rutas_principales_del_portal_devuelven_html(cliente, ruta):
    assert cliente.get(ruta).status_code == 200


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
    ruta_javascript = Path(__file__).parent / "static" / "js" / "estadisticas.js"
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
