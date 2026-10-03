"""Contrato de la caché en memoria de /api/estadisticas."""

import hashlib
from pathlib import Path
import sqlite3

import pytest

from cache_estadisticas import CacheEstadisticas, clave_estadisticas
from web_estadisticas import crear_app
import web_estadisticas
import estadisticas


DB = Path(__file__).parents[1] / "datos" / "boe.db"
TIPOS = [
    "Funcionario", "Laboral", "Otros",
]
PARAMETROS = dict(
    fecha_inicio=None, fecha_final=None, puesto=None, provincia=None,
    ambito=None, sistema=None, turno=None, tipo_personal=[], comparadores=[],
)


def clave(**cambios):
    return clave_estadisticas(78, **{**PARAMETROS, **cambios})


def test_clave_incluye_todos_los_filtros_efectivos_y_no_concatena_texto():
    base = clave()
    for campo, valor in (
        ("fecha_inicio", "2026-01-01"), ("fecha_final", "2026-09-30"),
        ("puesto", "Técnico & A=B+ñ"), ("provincia", "A Coruña"),
        ("ambito", "LOCAL"), ("sistema", "Oposición"), ("turno", "Libre"),
        ("tipo_personal", ["Funcionario"]), ("comparadores", ["Otro"]),
    ):
        assert clave(**{campo: valor}) != base
    assert clave(puesto="a&b=c") != clave(puesto="a", provincia="b=c")
    assert clave(puesto="Técnico") != clave(puesto="Tecnico")
    assert clave(puesto=" Técnico") != clave(puesto="Técnico")
    assert clave(comparadores=["A", "B"]) != clave(comparadores=["B", "A"])
    assert clave_estadisticas(79, **PARAMETROS) != base


def test_clave_multiseleccion_ignora_orden_y_duplicados():
    assert clave(tipo_personal=["Funcionario", "Laboral"]) == clave(
        tipo_personal=["Laboral", "Funcionario", "Funcionario"]
    )


def test_cache_lru_version_y_limpieza():
    cache = CacheEstadisticas(max_entradas=2)
    uno, dos, tres = (clave(puesto=valor) for valor in ("A", "B", "C"))
    assert cache.obtener(uno) is None
    cache.guardar(uno, b"uno", [])
    cache.guardar(dos, b"dos", [])
    assert cache.obtener(uno)[0] == b"uno"  # uno pasa a ser reciente
    cache.guardar(tres, b"tres", [])
    assert len(cache) == 2
    assert cache.obtener(dos) is None
    assert cache.obtener(uno)[0] == b"uno"
    nuevo = clave_estadisticas(79, **PARAMETROS)
    assert cache.obtener(nuevo) is None
    assert len(cache) == 0
    cache.guardar(nuevo, b"nuevo", [])
    cache.guardar(uno, b"viejo", [])  # MISS rezagado de la versión 78
    assert cache.obtener(nuevo)[0] == b"nuevo"
    assert len(cache) == 1
    cache.limpiar()
    assert len(cache) == cache.hits == cache.misses == 0


def test_cache_almacena_bytes_inmutables():
    cache = CacheEstadisticas()
    origen = bytearray(b'{"n":1}')
    cache.guardar(clave(), origen, ["Funcionario"])
    origen[5] = ord("9")
    assert cache.obtener(clave()) == (b'{"n":1}', ("Funcionario",))


def test_endpoint_miss_hit_identicos_y_hit_evade_trabajo_pesado(monkeypatch):
    app = crear_app(DB)
    cliente = app.test_client()
    primera = cliente.get("/api/estadisticas")
    assert primera.status_code == 200
    cache = app.extensions["cache_estadisticas"]
    assert (cache.misses, cache.hits) == (1, 0)

    def trabajo_prohibido(*args, **kwargs):
        raise AssertionError("un HIT no debe recalcular estadísticas")

    for nombre in (
        "opciones_filtros", "cargar_datos_estadisticas_sqlite", "filtrar_datos",
        "calcular_estadisticas", "calcular_comparacion_puestos", "metadata",
    ):
        monkeypatch.setattr(web_estadisticas, nombre, trabajo_prohibido)
    monkeypatch.setattr(estadisticas, "preparar_fechas", trabajo_prohibido)
    monkeypatch.setattr(estadisticas, "preparar_datos_estadisticas", trabajo_prohibido)
    segunda = cliente.get("/api/estadisticas")
    assert segunda.status_code == 200
    assert segunda.data == primera.data
    assert (cache.misses, cache.hits) == (1, 1)


def test_cambio_data_version_fuerza_miss_sin_tocar_sqlite(monkeypatch):
    app = crear_app(DB)
    cliente = app.test_client()
    version = [78]
    monkeypatch.setattr(web_estadisticas, "obtener_data_version", lambda ruta: version[0])
    primera = cliente.get("/api/estadisticas")
    cache = app.extensions["cache_estadisticas"]
    assert primera.status_code == 200 and len(cache) == 1
    version[0] = 79
    segunda = cliente.get("/api/estadisticas")
    assert segunda.status_code == 200
    assert segunda.data == primera.data
    assert (cache.misses, cache.hits) == (2, 0)
    assert len(cache) == 1


def test_multiseleccion_comparte_calculo_y_preserva_filtros_observables():
    app = crear_app(DB)
    cliente = app.test_client()
    primera = cliente.get("/api/estadisticas?tipo_personal=Funcionario&tipo_personal=Laboral")
    segunda = cliente.get("/api/estadisticas?tipo_personal=Laboral&tipo_personal=Funcionario")
    tercera = cliente.get("/api/estadisticas?tipo_personal=Funcionario&tipo_personal=Laboral&tipo_personal=Funcionario")
    cache = app.extensions["cache_estadisticas"]
    assert (cache.misses, cache.hits) == (1, 2)
    assert [x.get_json()["filtros"]["tipo_personal"] for x in (primera, segunda, tercera)] == [
        ["Funcionario", "Laboral"], ["Laboral", "Funcionario"],
        ["Funcionario", "Laboral", "Funcionario"],
    ]
    for respuesta in (primera, segunda, tercera):
        datos = respuesta.get_json()
        assert datos["resumen"]["total_registros"] == 74177
        assert sum(fila["registros"] for fila in datos["distribucion_tipo_personal"]) == 74177


@pytest.mark.parametrize("url", [
    "/api/estadisticas?fecha_inicio=2026-99-01",
    "/api/estadisticas?fecha_inicio=2026-09-01&fecha_final=2026-01-01",
    "/api/estadisticas?comparar=A&comparar=A",
    "/api/estadisticas?tipo_personal=Inventado",
])
def test_errores_no_se_cachean(url):
    app = crear_app(DB)
    cliente = app.test_client()
    primero = cliente.get(url)
    segundo = cliente.get(url)
    assert primero.status_code == segundo.status_code >= 400
    assert len(app.extensions["cache_estadisticas"]) == 0


def test_invariantes_productivas_en_miss_y_hit_y_sqlite_inmutable():
    antes = hashlib.sha256(DB.read_bytes()).hexdigest()
    app = crear_app(DB)
    cliente = app.test_client()
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as conexion:
        sql = conexion.execute(
            "SELECT COUNT(*), SUM(num_plazas), SUM(num_plazas IS NULL) FROM oposiciones "
            "WHERE lower(puesto) LIKE lower('%Ingeniero%') "
            "AND lower(puesto) LIKE lower('%Técnico%') "
            "AND lower(puesto) LIKE lower('%Industrial%')"
        ).fetchone()
    assert sql == (536, 803, 0)
    for _ in range(2):
        respuesta = cliente.get("/api/estadisticas?puesto=Ingeniero+T%C3%A9cnico+Industrial")
        datos = respuesta.get_json()
        assert datos["resumen"]["total_registros"] == 536
        assert datos["resumen"]["total_plazas"] == 803
        assert sum(fila["plazas"] for fila in datos["evolucion_anual"]) == 803
        assert sum(datos["evolucion_anual_puestos"]["series"][0]["values"]) == 803
    assert (app.extensions["cache_estadisticas"].misses, app.extensions["cache_estadisticas"].hits) == (1, 1)
    assert hashlib.sha256(DB.read_bytes()).hexdigest() == antes


def test_distribucion_global_siete_categorias_miss_hit():
    app = crear_app(DB)
    cliente = app.test_client()
    for _ in range(2):
        datos = cliente.get("/api/estadisticas").get_json()
        assert [x["tipo_personal"] for x in datos["distribucion_tipo_personal"]] == TIPOS
        assert sum(x["registros"] for x in datos["distribucion_tipo_personal"]) == 109429
        assert datos["resumen"]["total_registros"] == 109429


def test_filtro_funcionario_reconcilia_sql_en_miss_y_hit():
    app = crear_app(DB)
    cliente = app.test_client()
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as conexion:
        esperado = conexion.execute(
            "SELECT COUNT(*) FROM oposiciones WHERE tipo_personal = 'Funcionario'"
        ).fetchone()[0]
    for _ in range(2):
        datos = cliente.get("/api/estadisticas?tipo_personal=Funcionario").get_json()
        assert datos["resumen"]["total_registros"] == esperado
        assert [x["registros"] for x in datos["distribucion_tipo_personal"]] == [esperado, 0, 0]
    assert (app.extensions["cache_estadisticas"].misses,
            app.extensions["cache_estadisticas"].hits) == (1, 1)


def test_combinaciones_de_filtros_producen_misses_independientes():
    app = crear_app(DB)
    cliente = app.test_client()
    consultas = (
        "", "puesto=Ingeniero", "fecha_inicio=2024-01-01",
        "fecha_final=2024-12-31",
        "puesto=Ingeniero&fecha_inicio=2024-01-01&fecha_final=2024-12-31",
        "tipo_personal=Funcionario", "puesto=Ingeniero&tipo_personal=Funcionario",
        "fecha_inicio=2024-01-01&tipo_personal=Funcionario",
        "puesto=Ingeniero&fecha_inicio=2024-01-01&tipo_personal=Funcionario",
    )
    resultados = []
    for consulta in consultas:
        respuesta = cliente.get("/api/estadisticas" + ("?" + consulta if consulta else ""))
        assert respuesta.status_code == 200
        resultados.append(respuesta.get_json()["resumen"]["total_registros"])
    cache = app.extensions["cache_estadisticas"]
    assert cache.misses == len(consultas)
    assert len(cache) == cache.max_entradas  # una de las nueve fue expulsada
    assert len(set(resultados)) > 1
