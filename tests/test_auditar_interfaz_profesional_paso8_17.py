from scripts.audit.auditar_interfaz_profesional_paso8_17 import auditar


def test_auditoria_interfaz_profesional_registra_elementos_y_placeholders():
    resultado = auditar()
    assert resultado["footer"] is True
    assert resultado["navegacion"] is True
    assert resultado["desarrollador"] is True
    assert "[NOMBRE DE LA EMPRESA]" in resultado["placeholders"]
    assert resultado["sqlite_inmutable"] is True
