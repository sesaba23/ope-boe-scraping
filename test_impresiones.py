import impresiones


def _resultado():
    return {
        "Fecha_boe": ["1 de enero de 2025"],
        "Puesto": ["Ingeniero"],
        "Num_plazas": [1],
        "Administración": ["Ayuntamiento de Ejemplo"],
        "Escala": ["--"],
        "Subescala": ["--"],
        "Clase": ["--"],
        "Sistema": ["Oposición"],
        "Turno": ["Libre"],
        "Publicación": ["BOE-A-2025-1"],
        "Enlace": ["https://www.boe.es/ejemplo"],
    }


def test_informa_exito_completo(capsys, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *args: None)

    impresiones.imprimir_diccionario_puestos(
        _resultado(), "01/01/2025", "01/01/2025", publicaciones_analizadas=1
    )

    salida = capsys.readouterr().out
    assert "Los resultados se han guardado correctamente" in salida
    assert "Resultados incompletos" not in salida


def test_informa_resultados_parciales_y_numero_de_fallos(capsys, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *args: None)

    impresiones.imprimir_diccionario_puestos(
        _resultado(),
        "01/01/2025",
        "01/01/2025",
        publicaciones_analizadas=1,
        publicaciones_fallidas=2,
    )

    salida = capsys.readouterr().out
    assert "Resultados incompletos" in salida
    assert "2 publicación/es" in salida
    assert "Los resultados se han guardado correctamente" not in salida


def test_informa_fallo_de_todas_las_publicaciones(capsys):
    impresiones.imprimir_diccionario_puestos(
        {},
        "01/01/2025",
        "01/01/2025",
        publicaciones_analizadas=0,
        publicaciones_fallidas=2,
    )

    salida = capsys.readouterr().out
    assert "No se pudo analizar ninguna publicación" in salida
    assert "Publicaciones fallidas: 2" in salida
    assert "No se encontraron convocatorias" not in salida
    assert "Los resultados se han guardado correctamente" not in salida


def test_informa_ausencia_real_de_convocatorias(capsys):
    impresiones.imprimir_diccionario_puestos(
        {},
        "01/01/2025",
        "01/01/2025",
        publicaciones_analizadas=1,
        publicaciones_fallidas=0,
    )

    salida = capsys.readouterr().out
    assert "No se encontraron convocatorias" in salida
    assert "Resultados incompletos" not in salida
    assert "No se pudo analizar ninguna publicación" not in salida
