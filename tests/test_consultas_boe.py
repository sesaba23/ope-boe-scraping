import base_datos
import pytest

from consultas_boe import (_condiciones_busqueda, buscar_municipios, buscar_oposiciones,
                           buscar_oposiciones_sin_coordenadas, buscar_sugerencias_puesto, obtener_oposicion,
                           opciones_busqueda, resumen_mapa_oposiciones)


@pytest.fixture
def ruta_busqueda(tmp_path):
    ruta = tmp_path / "busqueda.db"
    con = base_datos.conectar(ruta)
    base_datos.crear_esquema(con)
    base_datos.crear_indices(con)
    existentes = {fila[1] for fila in con.execute("PRAGMA table_info(oposiciones)")}
    for columna in ("administracion_normalizada TEXT", "ambito TEXT", "tipo_entidad TEXT",
                    "comunidad_autonoma TEXT", "puesto_normalizado TEXT", "municipio_codigo_ine TEXT",
                    "version_resolutor TEXT"):
        if columna.split()[0] not in existentes:
            con.execute(f"ALTER TABLE oposiciones ADD COLUMN {columna}")
    for indice in range(1, 4):
        pid = f"BOE-A-2025-{indice}"
        con.execute("INSERT INTO publicaciones VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (pid, "https://boe.test", f"2025-0{indice}-01", "", "", "", "test", "ok", 1,
                     None, None, None, None, None, None, None))
    filas = [
        ("Ingeniero Técnico Industrial", "Ingeniero Técnico Industrial", "Ayuntamiento A", "LOCAL", "MUNICIPAL", "Madrid", "Madrid", "Madrid", "Oposición", "Libre", "E1", "S1", "C1", "2025-01-01", 2, "BOE-A-2025-1"),
        ("Auxiliar Administrativo", "Auxiliar Administrativo", "Consejería B", "AUTONOMICO", "AUTONOMICA", "Andalucía", "Sevilla", "Sevilla", "Concurso", "Promoción interna", "E2", "S2", "C2", "2025-02-01", 3, "BOE-A-2025-2"),
        ("Técnico O'Connor", "Técnico O'Connor", "Ministerio C", "ESTATAL", "MINISTERIO", "Comunidad de Madrid", "Madrid", "Madrid", "Oposición", "Libre", "E3", "S3", "C3", "2025-03-01", 4, "BOE-A-2025-3"),
    ]
    for puesto, normalizado, administracion, ambito, tipo, comunidad, provincia, municipio, sistema, turno, escala, subescala, clase, fecha, plazas, pid in filas:
        con.execute("""INSERT INTO oposiciones(num_plazas,puesto,puesto_normalizado,administracion,administracion_normalizada,
            ambito,tipo_entidad,comunidad_autonoma,provincia,municipio,sistema,turno,escala,subescala,clase,
            fecha_boe,fecha_boe_original,enlace,publicacion_id,version_extractor)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (plazas, puesto, normalizado, administracion, administracion, ambito, tipo, comunidad, provincia,
             municipio, sistema, turno, escala, subescala, clase, fecha, fecha, "https://boe.test", pid, "test"))
    base_datos.guardar_metadata(con, data_version=1)
    con.commit(); con.close()
    return ruta


@pytest.fixture
def ruta_mapa(ruta_busqueda):
    con = base_datos.conectar(ruta_busqueda)
    con.execute("INSERT INTO catalogos_geograficos VALUES (1, 'prueba', '1', 'test', NULL, NULL)")
    con.executemany("INSERT INTO comunidades_autonomas VALUES (?,?,?,?,?)", [
        (1, "Comunidad de Madrid", "comunidad de madrid", 0, 1),
        (2, "Andalucía", "andalucia", 0, 1),
        (3, "Ceuta", "ceuta", 1, 1),
    ])
    con.executemany("INSERT INTO provincias VALUES (?,?,?,?,?)", [
        ("28", "Madrid", "madrid", 1, 1),
        ("41", "Sevilla", "sevilla", 2, 1),
    ])
    con.executemany("INSERT INTO municipios VALUES (?,?,?,?,?,?,?,?,?,?)", [
        ("28079", "Madrid", "madrid", "28", 1, 40.4, -3.7, None, 1, 1),
        ("41091", "Sevilla", "sevilla", "41", 2, 37.3, -5.9, None, 1, 1),
        ("28001", "Villa", "villa", "28", 1, 40.1, -3.6, None, 1, 1),
        ("41001", "Villa", "villa", "41", 2, 37.1, -5.8, None, 1, 1),
        ("51001", "Ceuta", "ceuta", None, 3, 35.9, -5.3, None, 1, 1),
    ])
    con.executemany("UPDATE oposiciones SET municipio_codigo_ine = ? WHERE oposicion_id = ?", [
        ("28079", 1), ("41091", 2), ("28079", 3),
    ])

    def insertar(pid, puesto, administracion, ambito, tipo, comunidad, provincia, municipio, plazas, codigo):
        con.execute("INSERT INTO publicaciones VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (pid, "https://boe.test", "2025-04-01", "", "", "", "test", "ok", 1,
                     None, None, None, None, None, None, None))
        con.execute("""INSERT INTO oposiciones(num_plazas,puesto,puesto_normalizado,administracion,administracion_normalizada,
                       ambito,tipo_entidad,comunidad_autonoma,provincia,municipio,sistema,turno,escala,subescala,clase,
                       fecha_boe,fecha_boe_original,enlace,publicacion_id,version_extractor,municipio_codigo_ine)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (plazas, puesto, puesto, administracion, administracion, ambito, tipo, comunidad, provincia,
                     municipio, "Oposición", "Libre", "E1", "S1", "C1", "2025-04-01", "2025-04-01",
                     "https://boe.test", pid, "test", codigo))

    insertar("BOE-A-2025-4", "Ingeniero Municipal", "Ayuntamiento A", "LOCAL", "MUNICIPAL", "Comunidad de Madrid", "Madrid", "Madrid", 5, "28079")
    insertar("BOE-A-2025-5", "Técnico Villa", "Ayuntamiento Villa Madrid", "LOCAL", "MUNICIPAL", "Comunidad de Madrid", "Madrid", "Villa", 7, "28001")
    insertar("BOE-A-2025-6", "Técnico Villa", "Ayuntamiento Villa Sevilla", "LOCAL", "MUNICIPAL", "Andalucía", "Sevilla", "Villa", 11, "41001")
    insertar("BOE-A-2025-7", "Técnico Ceuta", "Ayuntamiento de Ceuta", "LOCAL", "MUNICIPAL", "Ceuta", None, "Ceuta", 13, "51001")
    insertar("BOE-A-2025-8", "Sin coordenadas", "Entidad sin resolver", "LOCAL", "MUNICIPAL", "Madrid", "Madrid", "Sin resolver", 17, None)
    con.commit()
    con.execute("PRAGMA foreign_keys = OFF")
    insertar("BOE-A-2025-9", "Código inexistente", "Entidad código inexistente", "LOCAL", "MUNICIPAL", "Madrid", "Madrid", "Inexistente", 19, "99999")
    con.commit(); con.close()
    return ruta_busqueda


@pytest.fixture
def ruta_sin_coordenadas(ruta_mapa):
    con = base_datos.conectar(ruta_mapa)
    con.executemany("INSERT INTO municipios VALUES (?,?,?,?,?,?,?,?,?,?)", [
        ("28002", "Sin latitud", "sin latitud", "28", 1, None, -3.5, None, 1, 1),
        ("28003", "Sin longitud", "sin longitud", "28", 1, 40.2, None, None, 1, 1),
    ])
    for indice, codigo, puesto in ((10, "28002", "Municipio sin latitud"), (11, "28003", "Municipio sin longitud")):
        pid = f"BOE-A-2025-{indice}"
        con.execute("INSERT INTO publicaciones VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (pid, "https://boe.test", "2025-05-01", "", "", "", "test", "ok", 1,
                     None, None, None, None, None, None, None))
        con.execute("""INSERT INTO oposiciones(num_plazas,puesto,puesto_normalizado,administracion,administracion_normalizada,
                       ambito,tipo_entidad,comunidad_autonoma,provincia,municipio,sistema,turno,escala,subescala,clase,
                       fecha_boe,fecha_boe_original,enlace,publicacion_id,version_extractor,municipio_codigo_ine)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (1, puesto, puesto, "Ayuntamiento A", "Ayuntamiento A", "LOCAL", "MUNICIPAL",
                     "Comunidad de Madrid", "Madrid", puesto, "Oposición", "Libre", "E1", "S1", "C1",
                     "2025-05-01", "2025-05-01", "https://boe.test", pid, "test", codigo))
    con.commit(); con.close()
    return ruta_mapa


def test_buscar_oposiciones_sin_filtros_pagina_y_total(ruta_busqueda):
    resultado = buscar_oposiciones(ruta_busqueda, pagina=1, tamano_pagina=2)
    assert resultado["total"] == 3
    assert (resultado["pagina"], resultado["tamano_pagina"], resultado["total_paginas"]) == (1, 2, 2)
    assert [fila["oposicion_id"] for fila in resultado["filas"]] == [3, 2]
    assert buscar_oposiciones(ruta_busqueda, pagina=99, tamano_pagina=2)["pagina"] == 2


@pytest.mark.parametrize("filtros,esperado", [
    ({"texto": "ingeniero industrial"}, "Ingeniero Técnico Industrial"),
    ({"fecha_desde": "2025-02-01", "fecha_hasta": "2025-02-01"}, "Auxiliar Administrativo"),
    ({"provincia": "Sevilla", "municipio": "Sevilla", "comunidad_autonoma": "Andalucía"}, "Auxiliar Administrativo"),
    ({"administracion": "Ayuntamiento A", "ambito": "LOCAL", "tipo_entidad": "MUNICIPAL"}, "Ingeniero Técnico Industrial"),
    ({"sistema": "Concurso", "turno": "Promoción interna", "escala": "E2", "subescala": "S2", "clase": "C2"}, "Auxiliar Administrativo"),
])
def test_buscar_oposiciones_aplica_filtros(ruta_busqueda, filtros, esperado):
    resultado = buscar_oposiciones(ruta_busqueda, **filtros)
    assert resultado["total"] == 1
    assert resultado["filas"][0]["puesto"] == esperado


def test_buscar_oposiciones_limita_tamano_orden_y_parametriza_texto(ruta_busqueda):
    resultado = buscar_oposiciones(ruta_busqueda, tamano_pagina=1000, orden="puesto_asc")
    assert resultado["tamano_pagina"] == 100
    assert [fila["puesto"] for fila in resultado["filas"]] == ["Auxiliar Administrativo", "Ingeniero Técnico Industrial", "Técnico O'Connor"]
    assert buscar_oposiciones(ruta_busqueda, texto="O'Connor")["total"] == 1
    assert buscar_oposiciones(ruta_busqueda, texto="' OR 1=1 --")["total"] == 0
    with pytest.raises(ValueError, match="Orden no permitido"):
        buscar_oposiciones(ruta_busqueda, orden="fecha; DROP TABLE oposiciones")


@pytest.mark.parametrize("filtros,fragmento,parametros", [
    ({}, "", []),
    ({"texto": "ingeniero industrial"}, "LIKE lower(?) AND lower(COALESCE", ["%ingeniero%", "%industrial%"]),
    ({"fecha_desde": "2025-01-01", "fecha_hasta": "2025-12-31"}, "fecha_boe >= ? AND fecha_boe <= ?", ["2025-01-01", "2025-12-31"]),
    ({"comunidad_autonoma": "Andalucía"}, "comunidad_autonoma = ?", ["Andalucía"]),
    ({"provincia": "Sevilla"}, "provincia = ?", ["Sevilla"]),
    ({"municipio": "San Sebastián"}, "lower(municipio) LIKE lower(?) AND lower(municipio) LIKE lower(?)", ["%San%", "%Sebastián%"]),
    ({"municipio_exacto": "Madrid", "municipio_provincia_exacto": "Madrid"}, "municipio = ? AND provincia = ?", ["Madrid", "Madrid"]),
    ({"administracion": "Ayuntamiento A"}, "administracion = ?", ["Ayuntamiento A"]),
    ({"ambito": "LOCAL"}, "ambito = ?", ["LOCAL"]),
    ({"tipo_entidad": "MUNICIPAL"}, "tipo_entidad = ?", ["MUNICIPAL"]),
    ({"sistema": "Concurso"}, "sistema = ?", ["Concurso"]),
    ({"turno": "Libre"}, "turno = ?", ["Libre"]),
    ({"escala": "E1"}, "escala = ?", ["E1"]),
    ({"subescala": "S1"}, "subescala = ?", ["S1"]),
    ({"clase": "C1"}, "clase = ?", ["C1"]),
])
def test_condiciones_busqueda_centraliza_todos_los_filtros(filtros, fragmento, parametros):
    where, resultado_parametros = _condiciones_busqueda(**filtros)
    assert fragmento in where
    assert resultado_parametros == parametros


def test_condiciones_busqueda_combina_y_parametriza_caracteres_especiales():
    valor = "' OR 1=1 --"
    where, parametros = _condiciones_busqueda(
        texto=valor, municipio="Madrid", municipio_exacto="Madrid",
        municipio_provincia_exacto="Madrid", provincia="Madrid", ambito="LOCAL",
    )
    assert "ORDER BY" not in where and "LIMIT" not in where and "OFFSET" not in where
    assert valor not in where
    assert parametros == ["LOCAL", "Madrid", "Madrid", "Madrid", "%'%", "%OR%", "%1=1%", "%--%"]
    assert "lower(municipio) LIKE" not in where


def test_resumen_mapa_agrega_por_ine_y_usa_maestros(ruta_mapa):
    resumen = resumen_mapa_oposiciones(ruta_mapa)
    assert resumen["resumen"] == {
        "convocatorias": 9, "plazas": 81, "municipios": 5,
        "geolocalizadas": 7, "sin_coordenadas": 2,
    }
    assert [(fila["codigo_ine"], fila["convocatorias"], fila["plazas"]) for fila in resumen["municipios"]] == [
        ("28079", 3, 11), ("51001", 1, 13), ("41091", 1, 3), ("28001", 1, 7), ("41001", 1, 11),
    ]
    ceuta = next(fila for fila in resumen["municipios"] if fila["codigo_ine"] == "51001")
    assert ceuta["provincia"] is None and ceuta["comunidad_autonoma"] == "Ceuta"
    villas = [fila for fila in resumen["municipios"] if fila["municipio"] == "Villa"]
    assert {(fila["codigo_ine"], fila["provincia"]) for fila in villas} == {("28001", "Madrid"), ("41001", "Sevilla")}
    con = base_datos.conectar(ruta_mapa)
    con.execute("UPDATE oposiciones SET latitud = 0, longitud = 0 WHERE municipio_codigo_ine = '28079'")
    con.commit(); con.close()
    madrid = next(fila for fila in resumen_mapa_oposiciones(ruta_mapa)["municipios"] if fila["codigo_ine"] == "28079")
    assert (madrid["latitud"], madrid["longitud"]) == (40.4, -3.7)


@pytest.mark.parametrize("filtros", [
    {}, {"texto": "ingeniero"}, {"fecha_desde": "2025-02-01", "fecha_hasta": "2025-04-01"},
    {"comunidad_autonoma": "Andalucía"}, {"provincia": "Madrid"}, {"municipio": "Vill"},
    {"municipio_exacto": "Villa", "municipio_provincia_exacto": "Sevilla"},
    {"administracion": "Ayuntamiento A", "ambito": "LOCAL", "tipo_entidad": "MUNICIPAL"},
    {"sistema": "Oposición", "turno": "Libre", "escala": "E1", "subescala": "S1", "clase": "C1"},
    {"texto": "técnico", "provincia": "Sevilla", "ambito": "LOCAL", "tipo_entidad": "MUNICIPAL"},
])
def test_resumen_mapa_comparte_exactamente_el_universo_del_listado(ruta_mapa, filtros):
    assert resumen_mapa_oposiciones(ruta_mapa, **filtros)["resumen"]["convocatorias"] == buscar_oposiciones(ruta_mapa, **filtros)["total"]


def test_resumen_mapa_sin_resultados(ruta_mapa):
    assert resumen_mapa_oposiciones(ruta_mapa, texto="no existe") == {
        "resumen": {"convocatorias": 0, "plazas": 0, "municipios": 0, "geolocalizadas": 0, "sin_coordenadas": 0},
        "municipios": [],
    }


@pytest.mark.parametrize("filtros", [
    {}, {"provincia": "Madrid"}, {"texto": "sin"}, {"ambito": "LOCAL", "tipo_entidad": "MUNICIPAL"},
])
def test_sin_coordenadas_tiene_el_mismo_total_que_el_resumen(ruta_sin_coordenadas, filtros):
    detalle = buscar_oposiciones_sin_coordenadas(ruta_sin_coordenadas, **filtros)
    resumen = resumen_mapa_oposiciones(ruta_sin_coordenadas, **filtros)
    assert detalle["total"] == resumen["resumen"]["sin_coordenadas"]


def test_buscar_sin_coordenadas_pagina_motivos_y_orden_determinista(ruta_sin_coordenadas):
    primera = buscar_oposiciones_sin_coordenadas(ruta_sin_coordenadas, pagina=1, tamano=2)
    segunda = buscar_oposiciones_sin_coordenadas(ruta_sin_coordenadas, pagina=2, tamano=2)

    assert (primera["total"], primera["pagina"], primera["tamano"], primera["paginas"]) == (4, 1, 2, 2)
    assert [fila["oposicion_id"] for fila in primera["resultados"]] == [11, 10]
    assert [fila["oposicion_id"] for fila in segunda["resultados"]] == [9, 8]
    assert [fila["motivo_sin_coordenadas"] for fila in primera["resultados"]] == [
        "municipio_sin_coordenadas", "municipio_sin_coordenadas",
    ]
    assert [fila["motivo_sin_coordenadas"] for fila in segunda["resultados"]] == [
        "codigo_ine_no_resuelto", "sin_codigo_ine",
    ]
    assert primera["resultados"][1]["provincia"] == "Madrid"
    assert primera["resultados"][1]["enlace"] == "https://boe.test"


def test_buscar_sin_coordenadas_excluye_geolocalizadas_ceuta_y_valida_paginacion(ruta_sin_coordenadas):
    assert buscar_oposiciones_sin_coordenadas(ruta_sin_coordenadas, texto="Técnico Ceuta")["total"] == 0
    assert buscar_oposiciones_sin_coordenadas(ruta_sin_coordenadas, provincia="Sevilla")["total"] == 0
    assert buscar_oposiciones_sin_coordenadas(ruta_sin_coordenadas, texto="Código inexistente")["total"] == 1
    assert buscar_oposiciones_sin_coordenadas(ruta_sin_coordenadas, texto="inexistente total")["resultados"] == []
    with pytest.raises(ValueError):
        buscar_oposiciones_sin_coordenadas(ruta_sin_coordenadas, pagina=0)
    with pytest.raises(ValueError):
        buscar_oposiciones_sin_coordenadas(ruta_sin_coordenadas, tamano=101)


def test_opciones_busqueda_y_dependencias_territoriales(ruta_busqueda):
    opciones = opciones_busqueda(ruta_busqueda)
    assert opciones["comunidades"] == ["Andalucía", "Comunidad de Madrid", "Madrid"]
    assert opciones["administraciones"] == []
    assert opciones_busqueda(ruta_busqueda, comunidad_autonoma="Andalucía")["provincias"] == ["Sevilla"]
    assert opciones_busqueda(ruta_busqueda, provincia="Madrid")["municipios"] == ["Madrid"]


def test_obtener_oposicion_existente_e_inexistente(ruta_busqueda):
    detalle = obtener_oposicion(ruta_busqueda, 1)
    assert detalle["puesto"] == "Ingeniero Técnico Industrial"
    assert detalle["comunidad_autonoma"] == "Madrid"
    assert obtener_oposicion(ruta_busqueda, 9999) is None


def test_opciones_ciudad_autonoma_sin_provincia(ruta_busqueda):
    con = base_datos.conectar(ruta_busqueda)
    con.execute("UPDATE oposiciones SET comunidad_autonoma = 'Ceuta', provincia = NULL, municipio = 'Ceuta' WHERE oposicion_id = 3")
    con.commit(); con.close()
    opciones = opciones_busqueda(ruta_busqueda, comunidad_autonoma="Ceuta")
    assert opciones["provincias"] == []
    assert opciones["municipios"] == ["Ceuta"]
    assert buscar_oposiciones(ruta_busqueda, comunidad_autonoma="Ceuta")["total"] == 1


def test_municipio_parcial_exacto_y_sugerencias_acotadas(ruta_busqueda):
    assert buscar_oposiciones(ruta_busqueda, municipio="Mad")["total"] == 2
    assert buscar_oposiciones(ruta_busqueda, municipio="Mad", provincia="Madrid")["total"] == 2
    assert buscar_oposiciones(ruta_busqueda, municipio="Sev", comunidad_autonoma="Andalucía")["total"] == 1
    assert buscar_oposiciones(ruta_busqueda, municipio_exacto="Madrid")["total"] == 2
    assert buscar_oposiciones(ruta_busqueda, municipio="inexistente")["total"] == 0
    assert buscar_municipios(ruta_busqueda, "m") == []
    assert buscar_municipios(ruta_busqueda, "Mad", limite=100)[0]["municipio"] == "Madrid"
    assert buscar_municipios(ruta_busqueda, "' OR 1=1 --") == []


@pytest.mark.parametrize("ciudad", ["Ceuta", "Melilla"])
def test_municipio_ciudad_autonoma_sin_provincia(ruta_busqueda, ciudad):
    con = base_datos.conectar(ruta_busqueda)
    con.execute("UPDATE oposiciones SET comunidad_autonoma = ?, provincia = NULL, municipio = ? WHERE oposicion_id = 3", (ciudad, ciudad))
    con.commit(); con.close()
    sugerencias = buscar_municipios(ruta_busqueda, ciudad[:3])
    assert sugerencias == [{"municipio": ciudad, "provincia": None, "comunidad_autonoma": ciudad}]
    assert buscar_oposiciones(ruta_busqueda, municipio=ciudad[:3])["total"] == 1


def test_municipio_con_acentos_se_mantiene_en_busqueda_parcial(ruta_busqueda):
    con = base_datos.conectar(ruta_busqueda)
    con.execute("UPDATE oposiciones SET municipio = 'Alcalá de Henares' WHERE oposicion_id = 2")
    con.commit(); con.close()
    assert buscar_municipios(ruta_busqueda, "alcal")[0]["municipio"] == "Alcalá de Henares"


def test_sugerencias_puesto_parciales_y_limite(ruta_busqueda):
    assert buscar_sugerencias_puesto(ruta_busqueda, "inge") == ["Ingeniero Técnico Industrial"]
    assert buscar_sugerencias_puesto(ruta_busqueda, "ingeniero industrial") == ["Ingeniero Técnico Industrial"]
    assert buscar_sugerencias_puesto(ruta_busqueda, "x") == []
    assert buscar_sugerencias_puesto(ruta_busqueda, "' OR 1=1 --") == []
