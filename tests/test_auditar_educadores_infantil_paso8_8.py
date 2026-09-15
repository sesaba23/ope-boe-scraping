from scripts.audit.auditar_educadores_infantil_paso8_8 import _categoria, _coincide_b, _propuesto


def test_auditoria_reconoce_educador_infantil_sin_confundir_tecnico():
    assert _categoria({"puesto": "Educador/a de Educación Infantil"}) == "EDUCADOR_INFANTIL_EXPLICITO"
    assert _categoria({"puesto": "Técnico/a Educador/a Infantil"}) == "TECNICO"
    assert _propuesto("Educador/a de Educación Infantil") == "Educador Infantil"
    assert _propuesto("Técnico/a Educador/a Infantil") is None


def test_reconstruccion_b_cubre_guarderia_y_escuela_infantil():
    assert _coincide_b({"puesto": "Educador/a de Guardería", "puesto_normalizado": ""})
    assert _coincide_b({"puesto": "Educador de la Escuela Infantil", "puesto_normalizado": ""})
