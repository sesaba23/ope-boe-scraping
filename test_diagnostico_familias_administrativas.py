from diagnostico_familias_administrativas import clasificar_familia


def test_clasifica_ministerio_y_consejeria_sin_convertirlo_en_regla():
    assert clasificar_familia("Subsecretaría del Ministerio de Justicia") == ("MINISTERIO", "MEDIA")
    assert clasificar_familia("Consejería de Educación") == ("CONSEJERIA", "MEDIA")


def test_clasifica_patrones_reales_de_administracion_existente():
    assert clasificar_familia("Administración Local") == ("ADMINISTRACION_LOCAL_GENERICA", "BAJA")
    assert clasificar_familia("Comunidad Autónoma de Andalucía") == ("COMUNIDAD_AUTONOMA", "MEDIA")


def test_no_fuerza_una_familia_para_texto_desconocido():
    assert clasificar_familia("Entidad sin patrón explícito") == ("SIN_CLASIFICAR", "BAJA")
