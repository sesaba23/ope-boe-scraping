from scripts.audit.auditar_personal_escuela_infantil_paso8_10 import _clasifica, _profesion_centro, ejecutar


def test_no_fusiona_escuela_con_educacion():
    assert _clasifica("Técnico de Escuela Infantil") == "TECNICO_ESCUELA_INFANTIL"
    assert _clasifica("Técnico de Educación Infantil") == "TECNICO_EDUCACION_INFANTIL"


def test_distingue_centro_y_profesion():
    assert _profesion_centro("Técnico de Escuela Infantil") == "ESCUELA_INFANTIL_PARTE_PROFESION"
    assert _profesion_centro("plaza para Escuela Infantil Municipal") == "ESCUELA_INFANTIL_SOLO_CENTRO"


def test_auditoria_a_b_es_consistente():
    r = ejecutar(salida="/tmp/fase8_paso10_test.json")
    assert r["reconciliacion"]["iguales"]
    assert r["reconciliacion"]["diferencia_simetrica"] == []
    assert r["conjunto_seguro"]["reglas"] == []
