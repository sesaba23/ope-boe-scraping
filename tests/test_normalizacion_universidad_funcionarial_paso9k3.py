from normalizacion_puestos import normalizar_puesto

def test_cuerpos_universitarios_funcionariales():
    assert normalizar_puesto('Catedráticas y Catedráticos de Universidad') == 'Catedráticos de Universidad'
    assert normalizar_puesto('Profesor/a Titular de Universidad') == 'Profesores Titulares de Universidad'
    assert normalizar_puesto('Cuerpos Docentes Universitarios (Catedrático/a de Universidad)') == 'Catedráticos de Universidad'

def test_no_absorbe_figuras_laborales_ni_mixtas():
    assert normalizar_puesto('Profesor Contratado Doctor') != 'Profesores Titulares de Universidad'
    assert normalizar_puesto('Profesor Contratado Doctor y dos en el cuerpo de Profesores Titulares de Universidad') != 'Profesores Titulares de Universidad'

def test_idempotencia():
    for x in ('Catedráticas y Catedráticos de Universidad', 'Profesor/a Titular de Universidad'):
        y=normalizar_puesto(x); assert normalizar_puesto(y)==y
