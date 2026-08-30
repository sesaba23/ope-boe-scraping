import pandas as pd
import pytest

from estadisticas import (
    _convertir_fecha,
    calcular_estadisticas,
    filtrar_datos,
    normalizar_datos,
    obtener_opciones_filtros,
)


@pytest.mark.parametrize(
    ("entrada", "esperada"),
    [
        (20260702, "2026-07-02"),
        ("20260702", "2026-07-02"),
        ("2026-07-02", "2026-07-02"),
        ("2 de julio de 2026", "2026-07-02"),
    ],
)
def test_convertir_fecha_admite_formatos_inequivocos(entrada, esperada):
    assert _convertir_fecha(entrada) == pd.Timestamp(esperada)


def test_convertir_fecha_rechaza_texto_corrupto():
    assert pd.isna(_convertir_fecha("fecha corrupta"))


def _datos():
    return pd.DataFrame(
        [
            {
                "Fecha_boe": "1 de enero de 2025",
                "Num_plazas": 2,
                "Puesto": "Ingeniero Técnico Industrial",
                "Administración": "Administración A",
                "Provincia": "Madrid",
            },
            {
                "Fecha_boe": "31 de enero de 2025",
                "Num_plazas": "3",
                "Puesto": "Técnico Ingeniero de Gestión",
                "Administración": "Administración B",
                "Provincia": None,
            },
            {
                "Fecha_boe": "1 de febrero de 2025",
                "Num_plazas": "dato inválido",
                "Puesto": "Médico de Urgencias",
                "Administración": "Administración A",
                "Provincia": "Sevilla",
            },
            {
                "Fecha_boe": "fecha corrupta",
                "Num_plazas": 7,
                "Puesto": "Auxiliar administrativo",
                "Administración": "Administración C",
                "Provincia": "",
            },
        ]
    )


def test_normalizar_datos_convierte_fechas_y_plazas_sin_modificar_original():
    original = _datos()
    copia = original.copy(deep=True)

    resultado = normalizar_datos(original)

    assert resultado["Fecha_dt"].notna().tolist() == [True, True, True, False]
    assert resultado["Num_plazas_num"].tolist()[:2] == [2.0, 3.0]
    assert pd.isna(resultado.loc[2, "Num_plazas_num"])
    pd.testing.assert_frame_equal(original, copia)
    assert "Fecha_dt" not in original.columns
    assert "Num_plazas_num" not in original.columns


def test_filtrar_datos_usa_intervalo_inclusivo():
    datos = normalizar_datos(_datos())

    resultado = filtrar_datos(
        datos, fecha_inicio="2025-01-01", fecha_final="2025-01-31"
    )

    assert resultado["Puesto"].tolist() == [
        "Ingeniero Técnico Industrial",
        "Técnico Ingeniero de Gestión",
    ]


def test_filtrar_puesto_no_distingue_mayusculas_ni_tildes():
    resultado = filtrar_datos(normalizar_datos(_datos()), puesto="MEDICO")

    assert resultado["Puesto"].tolist() == ["Médico de Urgencias"]


def test_filtrar_puesto_exige_todas_las_palabras_en_cualquier_orden():
    resultado = filtrar_datos(
        normalizar_datos(_datos()), puesto="industrial ingeniero"
    )

    assert resultado["Puesto"].tolist() == ["Ingeniero Técnico Industrial"]




def test_filtrar_datos_no_modifica_dataframe_recibido():
    original = normalizar_datos(_datos())
    copia = original.copy(deep=True)

    filtrar_datos(original, fecha_inicio="2025-01-01", puesto="ingeniero")

    pd.testing.assert_frame_equal(original, copia)


def test_opciones_de_filtros_son_dinamicas_validas_y_ordenadas():
    datos = pd.DataFrame(
        {
            "Provincia": ["Sevilla", "Álava", "", None, "--", "No disponible"],
            "Sistema": ["Oposición", "Concurso", "--", "", None, "No disponible"],
            "Turno": ["Libre", "Discapacidad", None, "--", "", "No disponible"],
        }
    )

    assert obtener_opciones_filtros(datos) == {
        "provincias": ["Álava", "Sevilla"],
        "sistemas": ["Concurso", "Oposición"],
        "turnos": ["Discapacidad", "Libre"],
    }


def _datos_con_filtros():
    datos = _datos().copy()
    datos["Sistema"] = ["Oposición", "Concurso", "Oposición", "Concurso"]
    datos["Turno"] = ["Libre", "Libre", "Discapacidad", "Libre"]
    return normalizar_datos(datos)


@pytest.mark.parametrize(
    ("filtro", "valor", "puestos"),
    [
        ("provincia", "Madrid", ["Ingeniero Técnico Industrial"]),
        ("sistema", "Oposición", ["Ingeniero Técnico Industrial", "Médico de Urgencias"]),
        ("turno", "Discapacidad", ["Médico de Urgencias"]),
    ],
)
def test_filtros_exactos_por_provincia_sistema_y_turno(filtro, valor, puestos):
    resultado = filtrar_datos(_datos_con_filtros(), **{filtro: valor})

    assert resultado["Puesto"].tolist() == puestos


def test_combina_todos_los_filtros():
    resultado = filtrar_datos(
        _datos_con_filtros(),
        fecha_inicio="2025-01-01",
        fecha_final="2025-01-31",
        puesto="ingeniero industrial",
        provincia="Madrid",
        sistema="Oposición",
        turno="Libre",
    )

    assert resultado["Puesto"].tolist() == ["Ingeniero Técnico Industrial"]


def test_calcular_estadisticas_suma_plazas_y_cuenta_registros():
    resultado = calcular_estadisticas(normalizar_datos(_datos()))

    assert resultado["total_plazas"] == 12
    assert resultado["total_registros"] == 4
    assert resultado["calidad_datos"] == {
        "fecha_no_utilizable": 1,
        "numero_plazas_no_utilizable": 1,
        "puesto_no_utilizable": 0,
        "provincia_no_disponible": 2,
        "administracion_no_disponible": 0,
        "sistema_no_disponible": 4,
        "turno_no_disponible": 4,
    }


def test_calcular_top_administraciones_por_suma_de_plazas():
    filas = [
        {
            "Fecha_boe": "1 de enero de 2025",
            "Num_plazas": indice,
            "Puesto": f"Puesto {indice}",
            "Administración": f"Administración {indice}",
            "Provincia": "Madrid",
        }
        for indice in range(1, 7)
    ]
    filas.append({**filas[0], "Num_plazas": 10, "Puesto": "Puesto adicional"})

    resultado = calcular_estadisticas(normalizar_datos(pd.DataFrame(filas)))

    assert len(resultado["top_administraciones"]) == 5
    assert resultado["top_administraciones"][0] == {
        "administracion": "Administración 1",
        "plazas": 11,
    }


def test_calcular_top_puestos_limita_a_diez():
    filas = [
        {
            "Fecha_boe": "1 de enero de 2025",
            "Num_plazas": indice,
            "Puesto": f"Puesto {indice:02d}",
            "Administración": "Administración",
            "Provincia": "Madrid",
        }
        for indice in range(1, 12)
    ]
    filas.append({**filas[0], "Num_plazas": 20})

    resultado = calcular_estadisticas(normalizar_datos(pd.DataFrame(filas)))

    assert len(resultado["top_puestos"]) == 10
    assert resultado["top_puestos"][0] == {"puesto": "Puesto 01", "plazas": 21}


def test_calcular_agrupa_provincias_e_incluye_sin_provincia():
    resultado = calcular_estadisticas(normalizar_datos(_datos()))
    provincias = {
        fila["provincia"]: fila["plazas"]
        for fila in resultado["plazas_por_provincia"]
    }

    assert provincias == {"Sin provincia": 10, "Madrid": 2}


def test_provincias_con_cero_plazas_tras_filtrar_no_aparecen():
    filtrados = filtrar_datos(normalizar_datos(_datos()), puesto="médico")

    resultado = calcular_estadisticas(filtrados)

    assert resultado["total_registros"] == 1
    assert resultado["plazas_por_provincia"] == []


def test_cuenta_provincias_y_administraciones_con_plazas():
    resultado = calcular_estadisticas(normalizar_datos(_datos()))

    assert resultado["total_provincias"] == 1
    assert resultado["total_administraciones"] == 3


def test_contadores_ignoran_vacios_sin_provincia_y_grupos_sin_plazas():
    datos = pd.DataFrame(
        [
            {"Fecha_boe": "1 de enero de 2025", "Num_plazas": 1, "Puesto": "A", "Administración": "Entidad A", "Provincia": "Madrid"},
            {"Fecha_boe": "1 de enero de 2025", "Num_plazas": 2, "Puesto": "B", "Administración": "Entidad A", "Provincia": "Madrid"},
            {"Fecha_boe": "1 de enero de 2025", "Num_plazas": 3, "Puesto": "C", "Administración": "Entidad B", "Provincia": "Sin provincia"},
            {"Fecha_boe": "1 de enero de 2025", "Num_plazas": 4, "Puesto": "D", "Administración": None, "Provincia": None},
            {"Fecha_boe": "1 de enero de 2025", "Num_plazas": 0, "Puesto": "E", "Administración": "", "Provincia": "Sevilla"},
        ]
    )

    resultado = calcular_estadisticas(normalizar_datos(datos))

    assert resultado["total_provincias"] == 1
    assert resultado["total_administraciones"] == 2


def test_evolucion_mensual_esta_ordenada_y_suma_plazas():
    resultado = calcular_estadisticas(normalizar_datos(_datos()))

    assert resultado["evolucion_mensual"] == [
        {"mes": "2025-01", "plazas": 5},
        {"mes": "2025-02", "plazas": 0},
    ]


def test_calcular_estadisticas_admite_dataframe_vacio():
    vacio = pd.DataFrame(
        columns=["Fecha_boe", "Num_plazas", "Puesto", "Administración", "Provincia"]
    )

    resultado = calcular_estadisticas(vacio)

    assert resultado == {
        "total_plazas": 0,
        "total_registros": 0,
        "total_provincias": 0,
        "total_administraciones": 0,
        "top_administraciones": [],
        "top_puestos": [],
        "plazas_por_provincia": [],
        "evolucion_mensual": [],
        "calidad_datos": {
            "fecha_no_utilizable": 0,
            "numero_plazas_no_utilizable": 0,
            "puesto_no_utilizable": 0,
            "provincia_no_disponible": 0,
            "administracion_no_disponible": 0,
            "sistema_no_disponible": 0,
            "turno_no_disponible": 0,
        },
    }


def test_calidad_distingue_carencias_sin_invalidar_otras_estadisticas():
    datos = pd.DataFrame([
        {"Fecha_boe": "2026-07-02", "Num_plazas": 2, "Puesto": "A",
         "Administración": "--", "Provincia": None, "Sistema": "--", "Turno": "--"},
        {"Fecha_boe": "20260703", "Num_plazas": "mal", "Puesto": " ",
         "Administración": " ", "Provincia": "Madrid", "Sistema": "Libre", "Turno": ""},
    ])
    resultado = calcular_estadisticas(datos)

    assert resultado["total_registros"] == 2
    assert resultado["total_plazas"] == 2
    assert resultado["top_administraciones"] == []
    assert resultado["calidad_datos"] == {
        "fecha_no_utilizable": 0,
        "numero_plazas_no_utilizable": 1,
        "puesto_no_utilizable": 1,
        "provincia_no_disponible": 1,
        "administracion_no_disponible": 2,
        "sistema_no_disponible": 1,
        "turno_no_disponible": 2,
    }


def test_calcular_estadisticas_no_modifica_dataframe_original():
    original = normalizar_datos(_datos())
    copia = original.copy(deep=True)

    calcular_estadisticas(original)

    pd.testing.assert_frame_equal(original, copia)
