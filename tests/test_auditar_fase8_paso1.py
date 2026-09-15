from scripts.audit.auditar_fase8_paso1 import clasificar


def test_clasificacion_es_excluyente_y_protege_no_docentes():
    assert clasificar("Profesor de Música", "Profesor de Música", "LOCAL") == "DOCENCIA_MUSICAL_RESIDUAL"
    assert clasificar("Monitor de escuela", "Monitor de escuela", "LOCAL") == "MONITOR"
    assert clasificar("Técnico de formación", "Técnico de formación", "LOCAL") == "TECNICO"
    assert clasificar("Auxiliar de escuela", "Auxiliar de escuela", "LOCAL") == "AUXILIAR"


def test_ya_normalizada_tiene_precedencia():
    assert clasificar("Profesor/a", "Profesor", "LOCAL") == "YA_NORMALIZADA"

