from scripts.audit.auditar_policia_pendiente_paso4 import clasificar_policia_aislada


def _fila(**cambios):
    base = {"ambito": "LOCAL", "tipo_entidad": "MUNICIPAL", "administracion": "Ayuntamiento de Prueba", "escala": "Administración Especial", "subescala": "Servicios Especiales", "sistema": "Oposición"}
    return base | cambios


def test_clasifica_policia_nacional_solo_con_evidencia_estructural_completa():
    fila = _fila(ambito="ESTATAL", tipo_entidad="ESTATAL", administracion="Ministerio del Interior", escala="Básica")
    assert clasificar_policia_aislada(fila)[0:2] == ("SEGURA_POLICIA_NACIONAL", "Policía Nacional")
    assert clasificar_policia_aislada(_fila(ambito="ESTATAL", tipo_entidad="ESTATAL", administracion="Ministerio del Interior", escala="Ejecutiva"))[0] == "DUDOSA"


def test_clasifica_contexto_municipal_y_no_convierte_administracion_local_generica():
    assert clasificar_policia_aislada(_fila())[0:2] == ("SEGURA_POLICIA_LOCAL", "Policía Local")
    assert clasificar_policia_aislada(_fila(ambito="INDETERMINADO", tipo_entidad="INDETERMINADO", administracion="Administración Local"))[0] == "PROBABLE_POLICIA_LOCAL"
