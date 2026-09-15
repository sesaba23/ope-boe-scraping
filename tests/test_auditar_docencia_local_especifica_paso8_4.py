from scripts.audit.auditar_docencia_local_especifica_paso8_4 import _microfamilia

def test_microfamilias_protegen_no_docentes():
    assert _microfamilia("Profesor de Piano") == "profesores municipales"
    assert _microfamilia("Monitor de escuela") == "monitores"
    assert _microfamilia("Técnico de escuela") == "técnicos"

