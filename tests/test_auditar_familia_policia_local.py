from scripts.audit.auditar_familia_policia_local import proponer_normalizacion_experimental


def test_propuesta_experimental_reconoce_categoria_local_y_municipal():
    assert proponer_normalizacion_experimental("Oficial de la Policía Local")[0:2] == ("SEGURA_TEXTUAL", "Oficial de Policía Local")
    assert proponer_normalizacion_experimental("Agente de Policía Municipal")[0:2] == ("SEGURA_TEXTUAL", "Policía Local")


def test_propuesta_experimental_protege_exclusiones_y_policia_aislada():
    assert proponer_normalizacion_experimental("Auxiliar de Policía Local")[0] == "EXCLUIDA"
    assert proponer_normalizacion_experimental("Administrativo adscrito a Policía Local")[0] == "EXCLUIDA"
    assert proponer_normalizacion_experimental("Policía", {("ESTATAL", "ESTATAL")})[0] == "DUDOSA"
    assert proponer_normalizacion_experimental("Policía", {("LOCAL", "MUNICIPAL")})[0] == "SEGURA_CONTEXTUAL"


def test_propuesta_experimental_no_equivale_guardia_urbana_sin_decision():
    clase, propuesto, _, _ = proponer_normalizacion_experimental("Inspector de la Guardia Urbana")
    assert (clase, propuesto) == ("DUDOSA", None)
