"""Regresiones permanentes de los dos patrones auditados."""

from extraer_tablas_xml_boe import extraer_resultados_tabla
from extractor_historico_boe import extraer_campos_bloque, extraer_pares_denominacion_cantidad


def test_fila_normal_se_extrae():
    tabla = {
        "encabezados": ["Especialidad", "N.º plazas"],
        "filas": [["Auxiliar administrativo", "10"]],
    }
    assert extraer_resultados_tabla(tabla) == [{
        "Puesto": "Auxiliar administrativo",
        "Num_plazas": 10,
        "Escala": None,
        "Turno": None,
        "Sistema": None,
    }]


def test_fila_total_agregada_se_excluye():
    tabla = {
        "encabezados": ["Especialidad", "N.º plazas"],
        "filas": [["Auxiliar administrativo", "10"], ["N.º total de plazas.", "10"]],
    }
    resultados = extraer_resultados_tabla(tabla)
    assert resultados == [{
        "Puesto": "Auxiliar administrativo",
        "Num_plazas": 10,
        "Escala": None,
        "Turno": None,
        "Sistema": None,
    }]


def test_codigo_de_puesto_no_desplaza_denominacion_explicita():
    tabla = {
        "encabezados": ["N.º orden", "Puesto", "Denominación", "Vacantes"],
        "filas": [["8025", "50370641", "OFICINA DE JUSTICIA DE ADRA.", "1"]],
    }
    resultado = extraer_resultados_tabla(tabla)[0]
    assert resultado["Puesto"] == "OFICINA DE JUSTICIA DE ADRA."
    assert resultado["Num_plazas"] == 1


def test_etiquetas_de_total_en_variantes_se_excluyen():
    tabla = {
        "encabezados": ["Especialidad", "Plazas"],
        "filas": [
            ["Auxiliar", "2"],
            ["Nº total de plazas", "2"],
            ["Número total de plazas", "2"],
            ["Total de plazas", "2"],
            ["Total plazas", "2"],
        ],
    }
    resultados = extraer_resultados_tabla(tabla)
    assert [r["Puesto"] for r in resultados] == ["Auxiliar"]


def test_denominaciones_legitimas_con_total_o_numero_se_conservan():
    tabla = {
        "encabezados": ["Especialidad", "Plazas"],
        "filas": [["Técnico/a Medio de Gestión Plazas Generales", "7"], ["Técnico 1.ª", "1"]],
    }
    resultados = extraer_resultados_tabla(tabla)
    assert [r["Puesto"] for r in resultados] == [
        "Técnico/a Medio de Gestión Plazas Generales", "Técnico 1.ª"
    ]


def test_narrativa_del_total_no_se_persiste_como_puesto():
    extraido = extraer_campos_bloque("Del total de la convocatoria, 2 plazas corresponden al turno libre.")
    assert extraido["campos"]["Puesto"] is None
    assert extraer_pares_denominacion_cantidad("Del total de las plazas, 16 plazas.") == []
