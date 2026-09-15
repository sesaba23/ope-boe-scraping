from normalizacion_contextual_puestos import normalizar_puesto_efectivo
from normalizacion_puestos import normalizar_puesto


def _efectivo(texto):
    return normalizar_puesto_efectivo(texto, ambito="LOCAL", tipo_entidad="MUNICIPAL", provincia="Madrid").normalizado


def test_canoniza_especialidades_aprobadas():
    assert normalizar_puesto("Maestro de Pintura perteneciente a la Escala de Administración Especial") == "Profesor de Pintura"
    assert normalizar_puesto("Maestra/o de Formación (especialidad pintura)") == "Profesor de Pintura"
    assert normalizar_puesto("Personal Fijo-Discontinuo Docente de Danza Escuela de Música") == "Profesor de Danza"
    assert normalizar_puesto("profesorado de danza") == "Profesor de Danza"
    assert normalizar_puesto("Profesorado Escuela Municipal de Arte y Diseño de Formación y Orientación Laboral de la plantilla de") == "Profesor de Diseño"
    assert normalizar_puesto("Maestro de Taller en el Centro Ocupacional «El Molinet» (cerámica)") == "Otras especialidades artísticas explícitas"


def test_no_captura_falsos_positivos_ni_casos_contextuales():
    for texto in ("Pintor municipal", "Bailarín", "Actor", "Monitor de Danza", "Técnico de Diseño", "Maestro de Taller de Artes Plásticas y Diseño", "profesorado de monitor/a de Danza"):
        assert normalizar_puesto(texto) == texto


def test_especialidad_idempotente_y_contextual_preexistente():
    canon = _efectivo("Profesorado de danza")
    assert canon == "Profesor de Danza"
    assert _efectivo(canon) == canon
    assert normalizar_puesto("Policía") == "Policía"
    assert normalizar_puesto_efectivo("Policía", ambito="LOCAL", tipo_entidad="MUNICIPAL", administracion="Ayuntamiento de Madrid", municipio="Madrid", provincia="Madrid").normalizado == "Policía Local"
