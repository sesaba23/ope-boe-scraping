from normalizacion_puestos import normalizar_puesto

def test_secundaria_explicita_singular_y_codigo_590():
    assert normalizar_puesto('Profesor de Enseñanza Secundaria') == 'Profesores de Enseñanza Secundaria'
    assert normalizar_puesto('Profesores de Enseñanza Secundaria (código 590) situadas en las Ciudades de Ceuta y Melilla') == 'Profesores de Enseñanza Secundaria'

def test_secundaria_no_absorbe_denominaciones_locales():
    assert normalizar_puesto('Profesor/a de Secundaria (Inglés Técnico)') != 'Profesores de Enseñanza Secundaria'
