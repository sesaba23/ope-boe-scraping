from scripts.audit.auditar_tecnicos_educacion_infantil_paso8_9 import _categoria, _propuesto


def test_auditoria_conserva_los_tres_niveles_tecnicos():
    assert _propuesto("técnico de educación infantil") == "Técnico de Educación Infantil"
    assert _propuesto("técnico superior de educación infantil") == "Técnico Superior de Educación Infantil"
    assert _propuesto("técnico especialista en educación infantil") == "Técnico Especialista en Educación Infantil"
    assert _propuesto("Técnico Educador Infantil") is None
    assert _categoria({"puesto": "Técnico Auxiliar de Educación Infantil"}) == "AUXILIAR"
