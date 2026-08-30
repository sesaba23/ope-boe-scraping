import builtins
import importlib
import json
from pathlib import Path
import subprocess

import pandas as pd
import pytest
import base_datos
from consultas_boe import oposiciones

import web_estadisticas


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
    with base_datos.transaccion(conexion):
        for indice, fila in datos.iterrows():
            publicacion_id = f"BOE-A-2025-{indice}"
            fecha = f"2025-0{indice + 1}-01"
            conexion.execute("INSERT INTO publicaciones VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (publicacion_id, "https://x", fecha, fila["Fecha_boe"], "", "", "test", "con_coincidencias", 1, None, None, None, None, None, None, None))
            conexion.execute("INSERT INTO oposiciones(num_plazas,puesto,administracion,escala,subescala,clase,sistema,turno,fecha_boe,fecha_boe_original,enlace,provincia,publicacion_id,version_extractor) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (fila["Num_plazas"], fila["Puesto"], fila["Administración"], "--", "--", "--", fila["Sistema"], fila["Turno"], fecha, fila["Fecha_boe"], "https://x", fila["Provincia"], publicacion_id, "test"))
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
    assert b"Estad\xc3\xadsticas de convocatorias BOE" in respuesta.data
    assert b"Aplicar filtros" in respuesta.data


def test_pagina_contiene_filtros_indicadores_y_graficos(cliente):
    respuesta = cliente.get("/")
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
    html = cliente.get("/").get_data(as_text=True)

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
