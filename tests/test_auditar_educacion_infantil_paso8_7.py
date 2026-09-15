from scripts.audit.auditar_educacion_infantil_paso8_7 import (
    MAESTRO_CANON,
    _categoria,
    _coincide_metodo_b,
)

def test_auditoria_distingue_profesiones_infantiles():
    assert _categoria("Maestro/a de Educación Infantil", "Maestro/a de Educación Infantil") == "MAESTRO_EDUCACION_INFANTIL"
    assert _categoria("Educador Infantil", "Educador Infantil") == "EDUCADOR_INFANTIL"
    assert _categoria("Técnico de Educación Infantil", "Técnico de Educación Infantil") == "TECNICO_EDUCACION_INFANTIL"
    assert MAESTRO_CANON.fullmatch("maestro/a de educacion infantil")


def test_reconstruccion_b_cubre_escuela_municipal_y_errata_acento():
    assert _coincide_metodo_b({
        "puesto": "Director/a de la Escuela Municipal Infantil",
        "puesto_normalizado": "",
    })
    assert _coincide_metodo_b({
        "puesto": "Técnico/a Especialista en Educación Ínfantil",
        "puesto_normalizado": "",
    })
