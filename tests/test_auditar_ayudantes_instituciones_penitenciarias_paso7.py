from scripts.audit.auditar_ayudantes_instituciones_penitenciarias_paso7 import CANON, clasificar


def test_clasifica_canon_coletilla_y_exclusiones_sin_modificar_produccion():
    assert clasificar('Ayudantes de Instituciones Penitenciarias por el sistema general de acceso libre')[:2] == ('SEGURA_TEXTUAL', CANON)
    assert clasificar('Ayudantes Técnicos Sanitarios de Instituciones Penitenciarias')[0] == 'EXCLUIDA'
    assert clasificar('Ayudantes Instituciones Penitenciarias')[0] == 'DUDOSA'
