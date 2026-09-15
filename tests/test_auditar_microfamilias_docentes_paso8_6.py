from scripts.audit.auditar_microfamilias_docentes_paso8_6 import _familia, _selecciona

def test_microfamilias_conservan_especialidad_y_excluyen_generico():
    assert _familia("Profesor de Piano") == "música/instrumento"
    assert _familia("Profesor de Educación Infantil") == "educación infantil"
    assert not _selecciona({"puesto":"Profesor", "puesto_normalizado":"Profesor"})
