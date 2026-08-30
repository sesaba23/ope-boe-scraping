import pytest
import json
from pathlib import Path

from normalizacion_puestos import normalizar_puesto


@pytest.mark.parametrize(("entrada", "esperado"), [(None, None), ("", None), ("   ", None)])
def test_nulos_y_vacios(entrada, esperado):
    assert normalizar_puesto(entrada) == esperado


@pytest.mark.parametrize(
    "entrada",
    [
        "Ingeniero Técnico Industrial",
        "Ingeniero/a Técnico Industrial",
        "Ingeniero/a Técnico/a Industrial",
        "Ingeniera Técnica Industrial",
        "INGENIERO/A TÉCNICO/A INDUSTRIAL",
        "ingeniero tecnico industrial",
        "Ingeniero / a Técnico / a Industrial",
        "Ingeniero-a Técnico(a) Industrial",
    ],
)
def test_variantes_ingeniero_tecnico_industrial(entrada):
    assert normalizar_puesto(entrada) == "Ingeniero Técnico Industrial"


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("  Trabajadora   Social ", "Trabajador Social"),
        ("Trabajador/a Social", "Trabajador Social"),
        ("Arquitecta Técnica", "Arquitecto Técnico"),
        ("Administrativa", "Administrativo"),
        ("Educador/a Social", "Educador Social"),
        ("Técnico/a de Administración General", "Técnico de Administración General"),
        ("Profesor(a) de Música", "Profesor de Música"),
        ("Ingenieros/as Técnicos/as Industriales", "Ingeniero Técnico Industrial"),
        ("Trabajadores/as Sociales", "Trabajadores Sociales"),
        ("INSPECTORA DE OBRAS", "Inspector DE OBRAS"),
        ("Puesto  --  especial", "Puesto -- especial"),
        ("Puesto—especial", "Puesto-especial"),
        ("Puesto ,  especial", "Puesto, especial"),
    ],
)
def test_reglas_conservadoras(entrada, esperado):
    assert normalizar_puesto(entrada) == esperado


def test_conserva_especialidad():
    assert normalizar_puesto("Ingeniero/a Técnico/a Industrial - Electricidad") == (
        "Ingeniero Técnico Industrial - Electricidad"
    )


@pytest.mark.parametrize(
    ("primero", "segundo"),
    [
        ("Ingeniero Industrial", "Ingeniero Técnico Industrial"),
        ("Técnico Industrial", "Ingeniero Técnico Industrial"),
        ("Ingeniero", "Ingeniero Industrial"),
        ("Arquitecto", "Arquitecto Técnico"),
    ],
)
def test_no_fusiona_pares_ambiguos(primero, segundo):
    assert normalizar_puesto(primero) != normalizar_puesto(segundo)


@pytest.mark.parametrize(
    "entrada",
    [
        "Ingeniero/a Técnico/a Industrial",
        "Trabajadora Social",
        "Arquitecta Técnica - Urbanismo",
        "Bombero-Conductor",
    ],
)
def test_idempotencia(entrada):
    una = normalizar_puesto(entrada)
    assert normalizar_puesto(una) == una


def test_fase2_cubre_exhaustivamente_el_fixture_versionado():
    ruta = Path(__file__).with_name("datos_pruebas") / "normalizacion_titulaciones_fase2.json"
    fixture = json.loads(ruta.read_text(encoding="utf-8"))
    for caso in fixture["casos"]:
        obtenido = normalizar_puesto(caso["texto"])
        if caso["clasificacion"] == "SEGURO":
            assert obtenido == caso["canon_esperado"], caso
            assert normalizar_puesto(obtenido) == obtenido, caso
        else:
            assert obtenido != caso["familia"], caso


@pytest.mark.parametrize(
    ("entrada", "canon_prohibido"),
    [
        ("Ingeniero Industrial", "Ingeniero Técnico Industrial"),
        ("Técnico Superior Ingeniero Industrial", "Ingeniero Técnico Industrial"),
        ("Ingeniero Técnico de Industria", "Ingeniero Técnico Industrial"),
        ("Ingeniero/a Técnico/a de Industria", "Ingeniero Técnico Industrial"),
        ("Ingeniería Técnica Industrial", "Ingeniero Técnico Industrial"),
        ("Ingenierio Técnico Industrial", "Ingeniero Técnico Industrial"),
        ("Ingeniero de Caminos, Canales y Puertos", "Ingeniero Técnico de Obras Públicas"),
        ("Ingeniero Agrónomo", "Ingeniero Técnico Agrícola"),
        ("Ingeniero de Montes", "Ingeniero Técnico Forestal"),
        ("Arquitecto", "Arquitecto Técnico"),
    ],
)
def test_fase2_protege_titulaciones_proximas(entrada, canon_prohibido):
    assert normalizar_puesto(entrada) != canon_prohibido
