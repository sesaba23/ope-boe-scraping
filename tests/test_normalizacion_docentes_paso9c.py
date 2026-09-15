from normalizacion_puestos import normalizar_puesto

def test_cuerpos_docentes_explicitos():
    assert normalizar_puesto("Cuerpo de Maestros") == "Maestros"
    assert normalizar_puesto("Funcionarios docentes del cuerpo de Profesores de Enseñanza Secundaria") == "Profesores de Enseñanza Secundaria"
    assert normalizar_puesto("Catedráticos de Universidad") == "Catedráticos de Universidad"
    assert normalizar_puesto("Profesores Titulares de Universidad") == "Profesores Titulares de Universidad"

def test_no_absorbe_falsos_positivos_docentes():
    assert normalizar_puesto("Maestro de obras") == "Maestro de obras"
    assert normalizar_puesto("Profesor de Música") == "Profesor de Música"
    assert normalizar_puesto("Profesor Contratado Doctor") == "Profesor Contratado Doctor"

def test_docentes_idempotentes():
    for texto in ("Cuerpo de Maestros", "Catedráticos de Universidad", "Profesores Titulares de Universidad"):
        primero = normalizar_puesto(texto)
        assert normalizar_puesto(primero) == primero
