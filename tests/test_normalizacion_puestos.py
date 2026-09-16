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


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Tècnico/a Superior", "Técnico Superior"),
        ("Arquitecta/a de la plantilla de personal laboral fijo", "Arquitecto de la plantilla de personal laboral fijo"),
        ("Educadora/a Social", "Educador Social"),
        ("Auxiliar Administrativa/a de la plantilla de personal laboral fijo", "Auxiliar Administrativo"),
        ("Trabajadora/a Social", "Trabajador Social"),
    ],
)
def test_genero_encadenado_se_estabiliza_en_una_sola_normalizacion(entrada, esperado):
    assert normalizar_puesto(entrada) == esperado
    assert normalizar_puesto(esperado) == esperado


def test_preprocesado_compartido_clasifica_slash_y_descriptor_de_personal():
    # El espacio alrededor de la barra no puede cambiar la familia auditada.
    assert normalizar_puesto("Administrativo/ a de Personal") == "Administrativo"
    assert normalizar_puesto("Administrativo/a de Personal") == "Administrativo"
    # Un descriptor funcional no convierte esta plaza en una categoría distinta.
    assert normalizar_puesto("Auxiliar Administrativo/a /CTA (jornada parcial)") != "Auxiliar Administrativo"


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [("Oficial", "Oficial"), ("oficial", "Oficial"), ("Oficial/a", "Oficial"), ("oficial/a", "Oficial"),
     ("Auxiliar", "Auxiliar"), ("auxiliar", "Auxiliar"), ("Agente", "Agente"), ("agente", "Agente")],
)
def test_paso73_primer_bloque_literales_a_aprobados(entrada, esperado):
    assert normalizar_puesto(entrada) == esperado
    assert normalizar_puesto(esperado) == esperado


@pytest.mark.parametrize(
    "entrada",
    ["Oficial de Jardinería", "Oficial de Policía Local", "Agente Tributario", "Técnico de Medio Ambiente",
     "Auxiliar Administrativo", "Agente Primero de Policía Local", "Ingeniero Técnico Industrial"],
)
def test_paso73_preserva_especialidades_niveles_y_destinos(entrada):
    assert normalizar_puesto(entrada) == entrada


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Policía Municipal", "Policía Local"),
        ("Agente de la Policía Municipal", "Policía Local"),
        ("Oficial del Cuerpo de Policía Local", "Oficial de Policía Local"),
        ("Cabo de la Policía Local de Administración Especial", "Cabo de Policía Local"),
        ("Sargento de Policia Local", "Sargento de Policía Local"),
        ("Subinspector/a de Policía Local", "Subinspector de Policía Local"),
        ("Inspector de Policía Municipal", "Inspector de Policía Local"),
        ("Intendente Mayor de la Policía Local", "Intendente Mayor de Policía Local"),
        ("Agente Primero de Policía Local", "Agente Primero de Policía Local"),
        ("Policía Local vacante en la plantilla de personal funcionario de este Ayuntamiento", "Policía Local"),
    ],
)
def test_fase7_normaliza_categorias_seguras_de_policia_local(entrada, esperado):
    assert normalizar_puesto(entrada) == esperado
    assert normalizar_puesto(esperado) == esperado


@pytest.mark.parametrize(
    "entrada",
    [
        "Policía", "Policia", "Agente de Policía", "Guardia Urbana", "Inspector de la Guardia Urbana",
        "Auxiliar de Policía Local", "Policía Nacional", "Policía Portuaria",
        "Administrativo adscrito a Policía Local", "Técnico de Policía Local",
    ],
)
def test_fase7_no_absorbe_cuerpos_o_contextos_no_aprobados(entrada):
    assert normalizar_puesto(entrada) != "Policía Local"


def test_fase7_no_bloquea_familias_preexistentes_por_mencionar_policia():
    assert normalizar_puesto("Administrativo de Policía") == "Administrativo"
    assert normalizar_puesto("Auxiliar Administrativo (área de Policía)") == "Auxiliar Administrativo"


@pytest.mark.parametrize(
    "entrada",
    [
        "Ayudantes de Instituciones Penitenciarias por el sistema general de acceso libre",
        "AYUDANTES DE INSTITUCIONES PENITENCIARIAS POR EL SISTEMA GENERAL DE ACCESO LIBRE",
        "  Ayudantes   de Instituciones Penitenciarias por el sistema general de acceso libre  ",
    ],
)
def test_fase7b_ayudantes_penitenciarias_acceso_libre(entrada):
    canon = "Ayudantes de Instituciones Penitenciarias"
    assert normalizar_puesto(entrada) == canon
    assert normalizar_puesto(canon) == canon


@pytest.mark.parametrize(
    "entrada",
    [
        "Ayudantes Instituciones Penitenciarias",
        "Ayudantes Técnicos Sanitarios de Instituciones Penitenciarias",
        "Enfermeros de Instituciones Penitenciarias",
    ],
)
def test_fase7b_no_absorbe_ayudantes_penitenciarias_no_aprobados(entrada):
    assert normalizar_puesto(entrada) == entrada


def test_fase2_cubre_exhaustivamente_el_fixture_versionado():
    ruta = Path(__file__).resolve().parent.parent / "datos_pruebas" / "normalizacion_titulaciones_fase2.json"
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


@pytest.mark.parametrize(
    "entrada",
    [
        "Maestro/a de Educación Infantil",
        "Maestra de Educación Infantil",
        "Maestro en Educación Infantil",
        "Maestra/o Educación Infantil",
    ],
)
def test_fase8_educacion_infantil_canoniza_variantes_completas(entrada):
    assert normalizar_puesto(entrada) == "Maestro de Educación Infantil"
    assert normalizar_puesto(normalizar_puesto(entrada)) == "Maestro de Educación Infantil"


@pytest.mark.parametrize(
    "entrada",
    [
        "Maestro/maestra en educación infantil",
        "Maestro-a de Educación Infantil",
        "Maestro o Maestra de Educación Infantil",
    ],
)
def test_paso21_a1_canoniza_solo_las_tres_variantes_auditadas(entrada):
    assert normalizar_puesto(entrada) == "Maestro de Educación Infantil"
    assert normalizar_puesto(normalizar_puesto(entrada)) == "Maestro de Educación Infantil"


@pytest.mark.parametrize(
    "entrada",
    [
        "Maestro/a de Educación Infantil de la plantilla de personal laboral fijo",
        "Maestro/a Educación Infantil de la plantilla de personal laboral fijo",
        "Maestro/a de Escuela Infantil",
        "Maestro/a de la plantilla de personal laboral fijo",
        "Maestro/a (Educación Infantil)",
    ],
)
def test_paso21_a1_no_absorbe_contexto_centro_ni_contrato(entrada):
    assert normalizar_puesto(entrada) != "Maestro de Educación Infantil"


@pytest.mark.parametrize(
    "entrada",
    [
        "Maestro de Obras",
        "Maestro de Escuela Infantil",
        "Maestra de Educación Infantil de la plantilla de personal laboral fijo",
        "Educador Infantil",
        "Profesor de Educación Infantil",
    ],
)
def test_fase8_educacion_infantil_no_absorbe_profesiones_ni_descriptores(entrada):
    assert normalizar_puesto(entrada) != "Maestro de Educación Infantil"


@pytest.mark.parametrize(
    "entrada",
    [
        "Educador/a de Educación Infantil",
        "Educador/a de Infantil",
        "Educador/a (Infantil)",
        "Educadora infantil",
        "Educador-a Infantil",
    ],
)
def test_fase8_educador_infantil_canoniza_solo_variantes_completas(entrada):
    assert normalizar_puesto(entrada) == "Educador Infantil"
    assert normalizar_puesto(normalizar_puesto(entrada)) == "Educador Infantil"


@pytest.mark.parametrize(
    "entrada",
    [
        "Educador de Escuela Infantil",
        "Educador Infantil de la plantilla de personal laboral fijo",
        "Técnico Educador Infantil",
        "Auxiliar Educador Infantil",
        "Monitor de Guardería (Educador Infantil)",
        "Director/Educador de la Escuela Infantil Municipal",
        "Maestro-Educador Infantil",
    ],
)
def test_fase8_educador_infantil_no_elimina_profesion_o_contexto(entrada):
    assert normalizar_puesto(entrada) != "Educador Infantil"


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("técnico/a de educación infantil", "Técnico de Educación Infantil"),
        ("técnico/a superior de educación infantil", "Técnico Superior de Educación Infantil"),
        ("técnico/a especialista en educación infantil", "Técnico Especialista en Educación Infantil"),
    ],
)
def test_fase8_tecnicos_infantil_conservan_categoria(entrada, esperado):
    assert normalizar_puesto(entrada) == esperado
    assert normalizar_puesto(esperado) == esperado


@pytest.mark.parametrize(
    "entrada",
    [
        "Técnico en Educación Infantil",
        "Técnico Especialista de Educación Infantil",
        "Técnico Educador Infantil",
        "Técnico Auxiliar de Educación Infantil",
        "Técnico de Escuela Infantil",
        "Educador Infantil",
        "Maestro de Educación Infantil",
    ],
)
def test_fase8_tecnicos_infantil_no_fusionan_niveles_o_profesiones(entrada):
    assert normalizar_puesto(entrada) != "Técnico de Educación Infantil" or entrada == "Técnico de Educación Infantil"


def test_paso21_a2_canoniza_solo_el_cuerpo_explicito_auditado():
    assert normalizar_puesto("funcionarios docentes para el Cuerpo de Maestros") == "Maestros"
    assert normalizar_puesto("Maestros") == "Maestros"


@pytest.mark.parametrize(
    "entrada",
    [
        "funcionarios docentes para el Cuerpo de Maestros de Educación Infantil",
        "funcionarios docentes para el Cuerpo de Maestros de la plantilla de personal laboral fijo",
        "Maestro de Taller",
        "Maestro de Música",
        "Maestro/a de Escuela Infantil",
        "funcionarios docentes en los cuerpos de maestros 250",
    ],
)
def test_paso21_a2_no_absorbe_especialidad_contexto_cifras_o_funcion(entrada):
    assert normalizar_puesto(entrada) != "Maestros"
def test_fotocomposicion_no_se_confunde_con_composicion_musical():
    assert normalizar_puesto("Maestro/a de Fotocomposición") == "Maestro/a de Fotocomposición"
    assert normalizar_puesto("Composición gráfica") == "Composición gráfica"
    assert normalizar_puesto("Maestro/a de Composición") == "Profesor de Música - Composición"


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Bombero", "Bombero"), ("bombero", "Bombero"),
        ("Bombero/a", "Bombero"),
        ("Bombero Conductor", "Bombero-Conductor"),
        ("Bombero-Conductor", "Bombero-Conductor"),
        ("Bombero/a Conductor/a", "Bombero-Conductor"),
        ("Bombero/a-Conductor/a", "Bombero-Conductor"),
    ],
)
def test_paso41_bomberos_canoniza_solo_variantes_completas(entrada, esperado):
    assert normalizar_puesto(entrada) == esperado


@pytest.mark.parametrize(
    "entrada",
    ["Bombero Forestal", "Cabo Bombero", "Bombero Especialista", "Bombero-Mecánico-Conductor", "Bombero-Conductor Especialista"],
)
def test_paso41_bomberos_preserva_rangos_especialidades_y_compuestos(entrada):
    assert normalizar_puesto(entrada) == entrada


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Bibliotecario", "Bibliotecario"), ("Bibliotecario/a", "Bibliotecario"),
        ("Bibliotecaria", "Bibliotecario"), ("Bibliotecaria/o", "Bibliotecario"),
        ("Auxiliar de Biblioteca", "Auxiliar de Biblioteca"),
        ("Auxiliar Biblioteca", "Auxiliar de Biblioteca"),
    ],
)
def test_paso44_bibliotecas_canoniza_literales_completos(entrada, esperado):
    assert normalizar_puesto(entrada) == esperado


@pytest.mark.parametrize(
    "entrada",
    ["Archivero/a", "Ayudante de Biblioteca", "Técnico de Biblioteca", "Auxiliar de Archivo", "Bibliotecario-Archivero", "Director de Biblioteca", "Ayudantes de Archivos, Bibliotecas y Museos"],
)
def test_paso44_bibliotecas_preserva_fronteras(entrada):
    assert normalizar_puesto(entrada) == entrada


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Técnico/a Informático/a", "Técnico Informático"),
        ("Técnico/a Auxiliar de Informática", "Técnico Auxiliar de Informática"),
        ("Técnico/a Medio/a de Informática", "Técnico Medio de Informática"),
        ("Técnico/a Superior de Informática", "Técnico Superior de Informática"),
        ("Técnico/a Superior Informático/a", "Técnico Superior Informático"),
    ],
)
def test_paso47_tecnicos_informaticos_canoniza_solo_conjuntos_cerrados(entrada, esperado):
    assert normalizar_puesto(entrada) == esperado
    assert normalizar_puesto(esperado) == esperado


@pytest.mark.parametrize(
    "entrada",
    [
        "Técnico de Informática", "Técnico en Informática", "Técnico de Sistemas Informáticos",
        "Administrador de Sistemas", "Técnico de Redes", "Técnico de Soporte Informático",
        "Técnico Programador", "Analista-Programador", "Operador Informático",
        "Técnico Auxiliar de Informática de la escala de Administración Especial",
        "Técnico Informático y Apoyo Administrativo", "Técnico Superior en Informática",
    ],
)
def test_paso47_tecnicos_informaticos_preserva_nivel_y_fronteras(entrada):
    assert normalizar_puesto(entrada) == entrada


@pytest.mark.parametrize("entrada", ["Enfermero", "Enfermera", "Enfermero/a", "Enfermera/o", "Enfermero-a"])
def test_paso50_enfermeria_canoniza_solo_genero_completo(entrada):
    assert normalizar_puesto(entrada) == "Enfermero"
    assert normalizar_puesto("Enfermero") == "Enfermero"


@pytest.mark.parametrize(
    "entrada",
    [
        "DUE", "ATS", "Diplomado Universitario en Enfermería", "Matrona",
        "Enfermero/a del Trabajo", "Enfermería de Salud Mental", "Auxiliar de Enfermería",
        "Supervisor de Enfermería", "Enfermero/a-DUE", "Enfermeros",
    ],
)
def test_paso50_enfermeria_preserva_historia_especialidades_y_mandos(entrada):
    assert normalizar_puesto(entrada) == entrada


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Operario/a de Limpieza", "Operario de Limpieza"),
        ("Peón/a de Limpieza", "Peón de Limpieza"),
        ("Encargado/a de Limpieza", "Encargado de Limpieza"),
        ("Empleado/a de Limpieza", "Empleado de Limpieza"),
    ],
)
def test_paso53_limpieza_canoniza_solo_variantes_completas(entrada, esperado):
    assert normalizar_puesto(entrada) == esperado
    assert normalizar_puesto(esperado) == esperado


@pytest.mark.parametrize(
    "entrada",
    [
        "Limpiador", "Operario de Limpieza Viaria", "Peón de Limpieza Viaria",
        "Auxiliar de Limpieza", "Personal de Limpieza", "Operario de Servicios Múltiples",
        "Limpiador-Conserje", "Limpieza y Cocina", "Encargado de Limpieza Viaria",
    ],
)
def test_paso53_limpieza_preserva_categorias_ambitos_y_compuestos(entrada):
    assert normalizar_puesto(entrada) == entrada

@pytest.mark.parametrize("entrada", ["Conductor", "Conductor/a", "Conductora", "Conductor-a"])
def test_paso56_conductores_canoniza_solo_genero_completo(entrada):
    assert normalizar_puesto(entrada) == "Conductor"

@pytest.mark.parametrize("entrada", ["Bombero-Conductor", "Conductor de Ambulancia", "Conductor-Mecánico", "Oficial Conductor", "Conductor de Maquinaria", "Operario Conductor", "Conductores"])
def test_paso56_conductores_preserva_fronteras(entrada):
    assert normalizar_puesto(entrada) == entrada


@pytest.mark.parametrize(
    "entrada", ["Psicólogo", "Psicóloga", "Psicólogo/a", "Psicóloga/o", "Psicólogo-a", "Psicologo/a", "Psicológo/a"]
)
def test_paso62_psicologia_canoniza_solo_genero_completo(entrada):
    assert normalizar_puesto(entrada) == "Psicólogo"
    assert normalizar_puesto("Psicólogo") == "Psicólogo"


@pytest.mark.parametrize(
    "entrada",
    [
        "Psicólogo Clínico", "Psicólogo General Sanitario", "Psicólogo Sanitario",
        "Psicólogo Educativo", "Psicólogo Escolar", "Psicólogo Forense", "Técnico Psicólogo",
        "Facultativo Psicólogo", "Psicopedagogo", "Jefe de Psicología", "Escala de Psicólogos",
        "Psicólogo-Orientador", "Psicólogos",
    ],
)
def test_paso62_psicologia_preserva_especialidades_y_fronteras(entrada):
    assert normalizar_puesto(entrada) == entrada


@pytest.mark.parametrize("entrada", ["Trabajador Social", "Trabajadora Social", "Trabajador/a Social", "Trabajadora/or Social", "Trabajador-a Social"])
def test_paso65_trabajo_social_canoniza_solo_genero_completo(entrada):
    assert normalizar_puesto(entrada) == "Trabajador Social"


@pytest.mark.parametrize("entrada", ["Asistente Social", "Técnico de Trabajo Social", "Jefe de Trabajo Social", "Escala de Trabajo Social", "Trabajador Social-Educador"])
def test_paso65_trabajo_social_preserva_fronteras(entrada):
    assert normalizar_puesto(entrada) == entrada


@pytest.mark.parametrize("entrada", ["Cocinero", "Cocinera", "Cocinero/a", "Cocinera/o", "cocinero/a"])
def test_paso68_cocina_canoniza_solo_genero_completo(entrada):
    assert normalizar_puesto(entrada) == "Cocinero"


@pytest.mark.parametrize("entrada", ["Ayudante de Cocina", "Auxiliar de Cocina", "Pinche de Cocina", "Jefe de Cocina", "Cocinero-Repostero", "Cocinero-Limpiador", "Cocineros"])
def test_paso68_cocina_preserva_fronteras(entrada):
    assert normalizar_puesto(entrada) == entrada
