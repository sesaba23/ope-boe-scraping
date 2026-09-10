import pytest

from normalizacion_seleccion import normalizar_sistema, normalizar_turno

@pytest.mark.parametrize("original,canon", [
    ("Turno libre","Turno Libre"),("Turno libre.","Turno Libre"),("turno libre","Turno Libre"),("Libre","Turno Libre"),
    ("Promoción interna","Promoción Interna"),("Promocion interna","Promoción Interna"),("De Promoción Interna","Promoción Interna"),
    ("Movilidad","Movilidad"),("De Movilidad","Movilidad"),("De Promoción Externa","Promoción Externa"),
    ("Reservado A Personas Con Discapacidad","Reservado a Personas con Discapacidad"),("turno general","Turno General"),
    ("Restringido","Restringido"),("No disponible","--"),("--","--"),
])
def test_normalizar_turno(original,canon):
    assert normalizar_turno(original)==canon
    assert normalizar_turno(canon)==canon

@pytest.mark.parametrize("original,canon", [
    ("Concurso-oposición","Concurso-Oposición"),("Concurso oposición","Concurso-Oposición"),("Concurso-Oposición","Concurso-Oposición"),("Concurso-oposicion","Concurso-Oposición"),
    ("Concurso","Concurso"),("Oposición","Oposición"),("Oposicion","Oposición"),("Concurso de méritos","Concurso de Méritos"),
    ("Concurso de meritos","Concurso de Méritos"),("General De Acceso Libre","General de Acceso Libre"),
    ("General De Acceso Libre Y Promoción Interna","General de Acceso Libre y Promoción Interna"),("--","--"),
])
def test_normalizar_sistema(original,canon):
    assert normalizar_sistema(original)==canon
    assert normalizar_sistema(canon)==canon

@pytest.mark.parametrize("valor", [None,"", "Libre extraordinario", "Concurso de plazas", "General de acceso libre"])
def test_valores_no_aprobados_se_preservan(valor):
    assert normalizar_turno(valor)==valor
    assert normalizar_sistema(valor)==valor
