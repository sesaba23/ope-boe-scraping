from normalizacion_puestos import normalizar_puesto

def test_docencia_musical_conserva_especialidad_y_centro():
    assert normalizar_puesto("Profesor de Piano") == "Profesor de Música - Piano"
    assert normalizar_puesto("Profesor de Piano de la Escuela Municipal de Música") == "Profesor de Escuela de Música - Piano"
    assert normalizar_puesto("Profesor de Conservatorio") == "Profesor de Conservatorio"
    assert normalizar_puesto("Profesores/as de Música") == "Profesor de Música"
    assert normalizar_puesto("Profesores/as de Musica de la plantilla de personal laboral fijo") == "Profesor de Música"

def test_docencia_musical_no_absorbe_funciones_no_docentes():
    for texto in ("Músico de Banda", "Instrumentista", "Director de Banda", "Monitor de Música", "Técnico de Cultura Musical"):
        assert normalizar_puesto(texto) == texto

def test_docencia_musical_es_idempotente():
    canon = normalizar_puesto("Profesor de Piano")
    assert normalizar_puesto(canon) == canon
