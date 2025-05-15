import pytest
from datetime import datetime, timedelta
from entradas_datos import solicitar_fechas_y_validar


def test_solicitar_fechas_y_validar(monkeypatch):
    """
    Test para comprobar la funcionalidad de la función solicitar_fechas_y_validar
    en el archivo entrada_datos.py.
    """

    # Caso 1: Usuario introduce fechas válidas y texto de búsqueda
    inputs = iter(["01/05/2025", "07/05/2025"])
    monkeypatch.setattr(
        "builtins.input", lambda _: next(inputs, "")
    )  # Manejar StopIteration

    fecha_actual = "15/05/2025"  # Simular la fecha actual
    fechas = MockFechas()  # Simular el módulo fechas con un método generar_rango_fechas

    texto_busqueda, fecha_inicio, fecha_fin, lista_fechas = solicitar_fechas_y_validar(
        "ing téc ind", fecha_actual, fechas
    )

    assert texto_busqueda == "ing téc ind"
    assert fecha_inicio == "01/05/2025"
    assert fecha_fin == "07/05/2025"  # si no hay texto busqueda se igualan las fechas
    assert lista_fechas == [
        "01/05/2025",
        "02/05/2025",
        "03/05/2025",
        "04/05/2025",
        "05/05/2025",
        "06/05/2025",
        "07/05/2025",
    ]

    # Caso 2: Usuario no introduce texto de búsqueda y deja las fechas en blanco (usa la fecha actual por defecto)
    inputs = iter(["", ""])
    monkeypatch.setattr(
        "builtins.input", lambda _: next(inputs, "")
    )  # Manejar StopIteration

    texto_busqueda, fecha_inicio, fecha_fin, lista_fechas = solicitar_fechas_y_validar(
        "", fecha_actual, fechas
    )

    assert texto_busqueda == ""
    assert fecha_inicio == fecha_actual
    assert fecha_fin == fecha_actual
    assert lista_fechas == [fecha_actual]

    # Caso 3: Usuario introduce texto de búsqueda y una fecha inválida
    inputs = iter(["32/05/2028", "07/05/2025"])
    monkeypatch.setattr(
        "builtins.input", lambda _: next(inputs, "")
    )  # Manejar StopIteration

    with pytest.raises(
        ValueError, match="time data '32/05/2028' does not match format '%d/%m/%Y'"
    ):
        solicitar_fechas_y_validar("ing téc ind", fecha_actual, fechas, modo_test=True)


def test_fecha_no_superior_a_actual(monkeypatch):
    """
    Test para comprobar que la función solicitar_fechas_y_validar
    no permite fechas superiores a la fecha actual.
    """

    # Caso 4: Usuario introduce una fecha inicio posterior a la fecha actual
    inputs = iter(["13/05/2028", "12/05/2025"])  # Fechas posteriores a la fecha actual
    monkeypatch.setattr("builtins.input", lambda _: next(inputs, ""))

    fecha_actual = "12/05/2025"  # Simular la fecha actual
    fechas = MockFechas()  # Simular el módulo fechas con un método generar_rango_fechas

    with pytest.raises(
        ValueError,
        match="La fecha de inicio no puede ser posterior a la fecha actual.",
    ):
        solicitar_fechas_y_validar("ing téc ind", fecha_actual, fechas, modo_test=True)


class MockFechas:
    """
    Clase mock para simular el módulo fechas.
    """

    @staticmethod
    def generar_rango_fechas(fecha_inicio, fecha_fin):
        # Generar un rango de fechas entre fecha_inicio y fecha_fin
        inicio = datetime.strptime(fecha_inicio, "%d/%m/%Y")
        fin = datetime.strptime(fecha_fin, "%d/%m/%Y")
        rango = [
            (inicio + timedelta(days=i)).strftime("%d/%m/%Y")
            for i in range((fin - inicio).days + 1)
        ]
        return rango
