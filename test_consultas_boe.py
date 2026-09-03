import base_datos
import pytest

from consultas_boe import (buscar_municipios, buscar_oposiciones,
                           buscar_sugerencias_puesto, obtener_oposicion,
                           opciones_busqueda)


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
