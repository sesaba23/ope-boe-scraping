"""Normalización conservadora y auditable de denominaciones de puestos."""

import re
import unicodedata
from dataclasses import dataclass


# Grafías conocidas: se usan para recuperar acentos y capitalización, no para
# decidir equivalencias semánticas.
GRAFIAS = {
    "administracion": "Administración",
    "administrativo": "Administrativo",
    "administrativos": "Administrativos",
    "arquitecto": "Arquitecto",
    "arquitectos": "Arquitectos",
    "educador": "Educador",
    "educadores": "Educadores",
    "facultativo": "Facultativo",
    "facultativos": "Facultativos",
    "industrial": "Industrial",
    "industriales": "Industriales",
    "ingeniero": "Ingeniero",
    "ingenieros": "Ingenieros",
    "inspector": "Inspector",
    "inspectores": "Inspectores",
    "profesor": "Profesor",
    "profesores": "Profesores",
    "social": "Social",
    "tecnico": "Técnico",
    "tecnicos": "Técnicos",
    "trabajador": "Trabajador",
    "trabajadores": "Trabajadores",
}

REGLAS_GENERO = (
    (r"administrativ(?:os/as|as/os|os\(as\)|as|os)", "Administrativos"),
    (r"arquitect(?:os/as|as/os|os\(as\)|as|os)", "Arquitectos"),
    (r"facultativ(?:os/as|as/os|os\(as\)|as|os)", "Facultativos"),
    (r"ingenier(?:os/as|as/os|os\(as\)|as|os)", "Ingenieros"),
    (r"t[eé]cnic(?:os/as|as/os|os\(as\)|as|os)", "Técnicos"),
    (r"educador(?:es/as|as|es)", "Educadores"),
    (r"inspector(?:es/as|as|es)", "Inspectores"),
    (r"profesor(?:es/as|as|es)", "Profesores"),
    (r"trabajador(?:es/as|as|es)", "Trabajadores"),
    (r"administrativ(?:o/a|a/o|o-a|o\(a\)|a|o)", "Administrativo"),
    (r"arquitect(?:o/a|a/o|o-a|o\(a\)|a|o)", "Arquitecto"),
    (r"facultativ(?:o/a|a/o|o-a|o\(a\)|a|o)", "Facultativo"),
    (r"ingenier(?:o/a|a/o|o-a|o\(a\)|a|o)", "Ingeniero"),
    (r"t[eé]cnic(?:o/a|a/o|o-a|o\(a\)|a|o)", "Técnico"),
    (r"educador(?:/a|\(a\)|a)?", "Educador"),
    (r"inspector(?:/a|\(a\)|a)?", "Inspector"),
    (r"profesor(?:/a|\(a\)|a)?", "Profesor"),
    (r"trabajador(?:/a|\(a\)|a)?", "Trabajador"),
)

# Equivalencias semánticas explícitas. Las claves se calculan después de las
# transformaciones ortotipográficas y de género seguras.
CANONES = {
    "ayudantes de instituciones penitenciarias por el sistema general de acceso libre": "Ayudantes de Instituciones Penitenciarias",
    "administrativo": "Administrativo",
    "arquitecto": "Arquitecto",
    "arquitecto tecnico": "Arquitecto Técnico",
    "auxiliar administrativo": "Auxiliar Administrativo",
    "educador social": "Educador Social",
    "ingeniero tecnico industrial": "Ingeniero Técnico Industrial",
    "tecnico de administracion general": "Técnico de Administración General",
    "trabajador social": "Trabajador Social",
}
REGLAS_TECNICOS_INFORMATICOS = {
    "Técnico Informático": {"tecnico informatico", "tecnico/a informatico", "tecnico/a informatico/a"},
    "Técnico Auxiliar de Informática": {"tecnico auxiliar de informatica", "tecnico/a auxiliar de informatica"},
    "Técnico Medio de Informática": {"tecnico medio de informatica", "tecnico/a medio de informatica", "tecnico/a medio/a de informatica"},
    "Técnico Superior de Informática": {"tecnico superior de informatica", "tecnico/a superior de informatica"},
    "Técnico Superior Informático": {"tecnico superior informatico", "tecnico/a superior informatico", "tecnico/a superior informatico/a"},
}
REGLAS_ENFERMERIA = {
    "Enfermero": {"enfermero", "enfermera", "enfermero/a", "enfermera/o", "enfermero-a"},
}
REGLAS_LIMPIEZA = {
    "Operario de Limpieza": {"operario de limpieza", "operario/a de limpieza"},
    "Peón de Limpieza": {"peon de limpieza", "peon/a de limpieza"},
    "Encargado de Limpieza": {"encargado de limpieza", "encargado/a de limpieza"},
    "Empleado de Limpieza": {"empleado de limpieza", "empleado/a de limpieza"},
}
REGLAS_CONDUCTORES = {"Conductor": {"conductor", "conductora", "conductor/a", "conductora/o", "conductor-a"}}
REGLAS_PSICOLOGIA = {
    # Sólo la denominación individual completa. Especialidades, condición
    # sanitaria, categoría, cuerpo, mando y puestos compuestos quedan fuera.
    "Psicólogo": {"psicologo", "psicologa", "psicologo/a", "psicologa/o", "psicologo-a"},
}
REGLAS_TRABAJO_SOCIAL = {
    "Trabajador Social": {"trabajador social", "trabajadora social", "trabajador/a social", "trabajadora/or social", "trabajador-a social"},
}
REGLAS_COCINA = {"Cocinero": {"cocinero", "cocinera", "cocinero/a", "cocinera/o", "cocinero-a"}}
# PASO 73: primer bloque semántico de PASO 72.  Se limita a las formas
# completas aprobadas; no usa prefijos, por lo que no absorbe oficiales,
# auxiliares o agentes con especialidad, destino, mando o función añadida.
REGLAS_PRIMER_BLOQUE = {
    "Oficial": {"oficial", "oficial/a"},
    "Auxiliar": {"auxiliar"},
    "Agente": {"agente"},
}
TILDES_ORTOGRAFICAS_SEGURAS = {
    "tecnico": "técnico", "tecnica": "técnica", "tecnicos": "técnicos", "tecnicas": "técnicas",
    "medico": "médico", "medica": "médica", "psicologo": "psicólogo", "psicologa": "psicóloga",
    "informatico": "informático", "informatica": "informática", "administracion": "administración",
    "gestion": "gestión", "direccion": "dirección", "educacion": "educación", "formacion": "formación",
    "investigacion": "investigación", "intervencion": "intervención", "atencion": "atención", "prevencion": "prevención",
    "proteccion": "protección", "comunicacion": "comunicación", "programacion": "programación", "inspeccion": "inspección",
    "produccion": "producción", "conservacion": "conservación", "instalacion": "instalación", "explotacion": "explotación",
    "construccion": "construcción", "electrico": "eléctrico", "electronico": "electrónico", "mecanico": "mecánico", "clinico": "clínico",
}

# Familias profesionales aprobadas en Fase 4.  Estas reglas se mantienen
# separadas de los cánones ortotipográficos: eliminan sólo variación de una
# misma categoría y nunca rangos, especialidades o descriptores dudosos.
FAMILIAS_PUESTO_CANONICAS = {
    "policia_local": "Policía Local",
    "auxiliar_administrativo": "Auxiliar Administrativo",
    "administrativo": "Administrativo",
}
MARCADORES_POLICIA_LOCAL = re.compile(r"\bpolicia(?:s)? (?:local(?:es)?|municipal(?:es)?)\b")
MARCADORES_GUARDIA_URBANA = re.compile(r"\bguardia urbana\b")
EXCLUSIONES_POLICIA_LOCAL = re.compile(
    r"\b(?:auxiliar\w*|administrativ\w*|tecnic\w*|coordinador\w*|"
    r"recepcionista\w*|vigilante\w*|seguridad|nacional\w*|autonomic\w*|"
    r"portuari\w*|cauces|otros cuerpos|plantilla de policia)\b"
)
# De más específica a más general.  Cada categoría se reconoce antes de que
# el puesto pueda caer en la categoría base Policía Local.
CATEGORIAS_POLICIA_LOCAL = (
    ("Superintendente", r"\bsuperintendente\b"),
    ("Intendente Mayor", r"\bintendente(?:/ta)? (?:mayor|major)\b"),
    ("Intendente", r"\bintendente(?:/ta)?\b"),
    ("Inspector", r"\binspector(?:/a)?\b"),
    ("Subinspector", r"\bsubinspector(?:/a)?\b"),
    ("Suboficial", r"\bsuboficial(?:/a)?\b"),
    ("Sargento", r"\bsargento\b"),
    ("Cabo", r"\bcabo\b"),
    ("Caporal", r"\bcaporal(?:/a)?\b"),
    ("Oficial", r"\boficial(?:/a)?\b"),
    ("Jefe", r"\bjefe\b"),
    ("Agente Primero", r"\bagente primero\b"),
    ("Agente", r"\bagente(?:s)?\b"),
)
EXCLUSION_AUXILIAR_ADMINISTRATIVO = re.compile(r"\b(?:servicios administrativos|administracion especial|tecnico auxiliar)\b")
EXCLUSION_ADMINISTRATIVO = re.compile(r"\b(?:auxiliar|tecnico|servicios administrativos|personal administrativo)\b")


@dataclass(frozen=True)
class ReglaTitulacion:
    canon: str
    nucleo: str
    prefijos: tuple[str, ...] = ()
    sufijos: tuple[str, ...] = ()
    exclusiones: tuple[str, ...] = ()
    prioridad: int = 100
    confianza: str = "ALTA"


PREFIJOS_ADMINISTRATIVOS = (
    r"personal ", r"tmae ", r"tecnico medio ", r"tecnico de grado medio ",
    r"tecnico medio de administracion especial ",
    r"tecnico medio administracion especial ",
    r"consolidacion de trabajo temporal de ",
)

SUFIJOS_ADMINISTRATIVOS = (
    r" de (?:la )?plantilla(?: de personal)? (?:laboral fijo|funcionario)",
    r" de (?:la )?(?:escala|subescala)(?: tecnica| tecnico| tecnica media| tecnico media)?(?: de la)?(?: de)? administracion especial",
    r" perteneciente(?:s|/s)? a la escala(?: de la)?(?: de)? administracion especial",
    r" encuadradas en la escala de administracion especial",
    r" de esta universidad", r" en la concejalia de presidencia",
    r" para el ayuntamiento de san martin de la vega",
    r" del ayuntamiento de madrid", r" del ayuntamiento de getafe",
    r" de la plantilla del ayuntamiento de torrejon de ardoz",
    r" como personal funcionario de carrera", r" a tiempo parcial",
    r" a tiempo parcial \(dos horas semanales\) de la plantilla de personal labor",
    r" a tiempo parcial de la plantilla de personal laboral fijo",
    r" a jornada completa \(subgrupo a2\)",
    r" de la plantilla de personal laboral fijo grupo a2",
    r" \((?:personal funcionario|concurso oposicion libre|oep 2008|oep extraordinaria 2020)\)",
    r"-subgrupo a2", r" del ayuntamiento de getafe",
)

EXCLUSIONES_TITULACIONES = (
    r"\b(?:o|y|y/o|equivalente|grado en)\b", r"ingenierio",
    r"electric|mecanic|quimic|prevencion|ruidos|instalacion|equipamiento|alumbrado|rama",
)

TITULACIONES_CANONICAS = tuple(sorted((
    ReglaTitulacion("Ingeniero Técnico de Obras Públicas", r"ingenier(?:o|os) tecnic(?:o|os) de obras publicas", PREFIJOS_ADMINISTRATIVOS, SUFIJOS_ADMINISTRATIVOS, EXCLUSIONES_TITULACIONES, 10),
    ReglaTitulacion("Ingeniero Técnico de Telecomunicación", r"ingenier(?:o|os) tecnic(?:o|os) (?:de )?telecomunicaciones?", PREFIJOS_ADMINISTRATIVOS, SUFIJOS_ADMINISTRATIVOS, EXCLUSIONES_TITULACIONES, 20),
    ReglaTitulacion("Ingeniero Técnico en Informática", r"ingenier(?:o|os) tecnic(?:o|os) (?:en |de )?informatica", PREFIJOS_ADMINISTRATIVOS, SUFIJOS_ADMINISTRATIVOS, EXCLUSIONES_TITULACIONES, 30),
    ReglaTitulacion("Ingeniero Técnico Industrial", r"ingenier(?:o|os) tecnic(?:o|os)? industrial(?:es)?", PREFIJOS_ADMINISTRATIVOS, SUFIJOS_ADMINISTRATIVOS, EXCLUSIONES_TITULACIONES + (r" de industria",), 40),
    ReglaTitulacion("Ingeniero Técnico Agrícola", r"ingenier(?:o|os) tecnic(?:o|os)? agricol(?:a|as)", PREFIJOS_ADMINISTRATIVOS, SUFIJOS_ADMINISTRATIVOS, EXCLUSIONES_TITULACIONES, 50),
    ReglaTitulacion("Ingeniero Técnico Forestal", r"ingenier(?:o|os) tecnic(?:o|os)? forestal(?:es)?", PREFIJOS_ADMINISTRATIVOS, SUFIJOS_ADMINISTRATIVOS, EXCLUSIONES_TITULACIONES, 60),
    ReglaTitulacion("Ingeniero Técnico Aeronáutico", r"ingenier(?:o|os) tecnic(?:o|os)? aeronautic(?:o|os)", PREFIJOS_ADMINISTRATIVOS, SUFIJOS_ADMINISTRATIVOS, EXCLUSIONES_TITULACIONES, 70),
    ReglaTitulacion("Ingeniero Técnico Topógrafo", r"ingenier(?:o|os) tecnic(?:o|os)? topograf(?:o|os)", PREFIJOS_ADMINISTRATIVOS, SUFIJOS_ADMINISTRATIVOS, EXCLUSIONES_TITULACIONES, 80),
), key=lambda regla: regla.prioridad))


def _clave(texto):
    descompuesto = unicodedata.normalize("NFKD", texto.casefold())
    sin_acentos = "".join(
        caracter for caracter in descompuesto if not unicodedata.combining(caracter)
    )
    return re.sub(r"\s+", " ", sin_acentos).strip()


def _preparar_texto(texto):
    """Aplica la limpieza ortotipográfica común previa a cualquier decisión."""
    if texto is None:
        return None
    resultado = unicodedata.normalize("NFKC", str(texto))
    resultado = resultado.translate(str.maketrans({"\u2013": "-", "\u2014": "-", "\u2212": "-"}))
    resultado = re.sub(r"\s+", " ", resultado).strip()
    if not resultado:
        return None
    resultado = re.sub(r"\s*/\s*", "/", resultado)
    resultado = re.sub(r"\s*([,;:])\s*", r"\1 ", resultado)
    return re.sub(r"\s+", " ", resultado).strip()


def _normalizar_genero(texto):
    """Normaliza género hasta un punto fijo en una única invocación.

    Algunas reglas producen una forma que satisface otra regla anterior de la
    lista (por ejemplo, ``Técnica/a`` → ``Técnico/a`` → ``Técnico``). Repetir
    el conjunto hasta estabilizarlo evita que una segunda llamada pública al
    normalizador siga modificando el resultado.
    """
    resultado = texto
    while True:
        anterior = resultado
        for patron, reemplazo in REGLAS_GENERO:
            resultado = re.sub(rf"(?i)\b(?:{patron})(?!\w)", reemplazo, resultado)
        if resultado == anterior:
            return resultado


def _recuperar_grafia(texto):
    partes = re.split(r"(\W+)", texto, flags=re.UNICODE)
    for indice in range(0, len(partes), 2):
        grafia = GRAFIAS.get(_clave(partes[indice]))
        if grafia:
            partes[indice] = grafia
    return "".join(partes)


def _normalizar_titulacion(texto):
    clave = _clave(texto)
    # Dos formulaciones completas de género aprobadas que deliberadamente no
    # se convierten mediante reglas morfológicas globales.
    clave = clave.replace("ingeniera/ingeniero tecnica/tecnico", "ingeniero tecnico")
    clave = clave.replace("ingeniero o ingeniera tecnica", "ingeniero tecnico")
    clave = clave.replace("administracion especial-ingeniero", "administracion especial ingeniero")
    for regla in TITULACIONES_CANONICAS:
        if any(re.search(patron, clave) for patron in regla.exclusiones):
            continue
        prefijos = "|".join(regla.prefijos)
        sufijos = "|".join(regla.sufijos)
        patron = rf"^(?:(?:{prefijos}))?(?:{regla.nucleo})(?:(?:{sufijos}))?$"
        if re.fullmatch(patron, clave):
            return regla.canon
    return None


def clasificar_policia_local(texto):
    """Clasifica de forma textual y conservadora puestos de Policía Local.

    Es la única fuente de decisión para producción y para el dry-run de Fase
    7. No usa datos geográficos ni contexto externo: ``Policía`` aislado y
    Guardia Urbana se dejan deliberadamente fuera de automatización.
    """
    texto = _preparar_texto(texto)
    clave = _clave(texto or "")
    if not ("polic" in clave or MARCADORES_GUARDIA_URBANA.search(clave)):
        return None, None, None, None
    if EXCLUSIONES_POLICIA_LOCAL.search(clave):
        return "EXCLUIDA", None, None, "menciona policía como destino o cuerpo distinto"
    if MARCADORES_GUARDIA_URBANA.search(clave):
        return "DUDOSA", None, "Guardia Urbana", "Guardia Urbana queda fuera de esta fase"
    if not MARCADORES_POLICIA_LOCAL.search(clave):
        return "DUDOSA", None, None, "mención policial sin cuerpo local o municipal inequívoco"
    for categoria, patron in CATEGORIAS_POLICIA_LOCAL:
        if re.search(patron, clave):
            # Agente es la denominación base aprobada; el resto mantiene su
            # categoría para impedir absorciones de rango.
            canon = "Policía Local" if categoria == "Agente" else f"{categoria} de Policía Local"
            return "SEGURA", canon, categoria, "cuerpo local o municipal y categoría inequívoca"
    return "SEGURA", "Policía Local", "Policía Local", "cuerpo local o municipal inequívoco"


def clasificar_familia_puesto(texto):
    """Clasifica las familias Fase 4 sin decidir equivalencias dudosas.

    Devuelve ``(familia, clasificación, canon, motivo)``.  El motor sólo usa
    los casos ``alta_confianza``; el resto se expone para auditoría y tests.
    """
    texto = _preparar_texto(texto)
    clave = _clave(texto or "")
    clase_policia, canon_policia, _, motivo_policia = clasificar_policia_local(texto)
    # Una exclusión sin marcador local/municipal (por ejemplo, "Administrativo
    # de Policía") no debe impedir que las familias ya aprobadas de
    # Administrativo sigan actuando. Sí conservamos la exclusión cuando el
    # propio texto menciona Policía Local/Municipal.
    if clase_policia and (
        clase_policia != "EXCLUIDA" or MARCADORES_POLICIA_LOCAL.search(clave)
    ):
        clasificacion = {"SEGURA": "alta_confianza", "DUDOSA": "dudosa", "EXCLUIDA": "excluida"}[clase_policia]
        return "policia_local", clasificacion, canon_policia, motivo_policia
    # Precedencia obligatoria: nunca dejar que Auxiliar caiga en Administrativo.
    if re.search(r"\bauxiliar(?:es)? administrativ", clave):
        if EXCLUSION_AUXILIAR_ADMINISTRATIVO.search(clave):
            return "auxiliar_administrativo", "excluida", None, "categoría auxiliar profesional distinta"
        patron = r"^(?:plaza(?:s)? de |personal )?auxiliar(?:es)? administrativ(?:o|a|os|as|o/a|a/o|os/as|as/os)(?:\b(?!/)|\s+de )"
        if re.match(patron, clave):
            return "auxiliar_administrativo", "alta_confianza", FAMILIAS_PUESTO_CANONICAS["auxiliar_administrativo"], "auxiliar administrativo con género/plural o descriptor permitido"
        return "auxiliar_administrativo", "dudosa", None, "orden o contexto no validado"
    if re.search(r"\badministrativ", clave):
        if EXCLUSION_ADMINISTRATIVO.search(clave):
            return "administrativo", "excluida", None, "no es la categoría de Administrativo"
        patron = r"^(?:plaza(?:s)? de )?administrativ(?:o|a|os|as|o/a|a/o|os/as|as/os)(?:\b(?!/)|\s+de )"
        if re.match(patron, clave):
            return "administrativo", "alta_confianza", FAMILIAS_PUESTO_CANONICAS["administrativo"], "administrativo con género/plural o descriptor permitido"
        return "administrativo", "dudosa", None, "texto administrativo sin categoría inequívoca"
    return None, None, None, None


def _normalizar_docencia_musical(texto):
    """Devuelve el canon musical aprobado o ``None``.

    Mantiene deliberadamente las especialidades y distingue Conservatorio y
    Escuela de Música. Se replica el conjunto conservador auditado en 9H-4.
    """
    valor = texto.casefold()
    if not re.search(r"profesor|maestro", valor):
        return None
    if re.search(r"\bmonitor|\bauxiliar|t[eé]cnico|m[uú]sico|instrumentista|director(?![-/ ]profesor)", valor):
        return None
    musical = r"m[uú]sica|musical|conservatorio|escuela.*m[uú]sica|banda|piano|guitarra|viol[ií]n|viola|violonchelo|contrabajo|flauta|clarinete|oboe|fagot|saxof[oó]n|trompeta|tromb[oó]n|trompa|tuba|percusi[oó]n|bater[ií]a|acorde[oó]n|arpa|[oó]rgano|canto|solfeo|lenguaje musical|\bcomposici[oó]n\b|direcci[oó]n de (?:orquesta|banda)|armon[ií]a"
    if not re.search(musical, valor):
        return None
    especialidades = r"piano|guitarra|viol[ií]n|viola|violonchelo|contrabajo|flauta|clarinete|oboe|fagot|saxof[oó]n|trompeta|tromb[oó]n|trompa|tuba|percusi[oó]n|bater[ií]a|acorde[oó]n|arpa|[oó]rgano|canto|solfeo|lenguaje musical|\bcomposici[oó]n\b|armon[ií]a|m[uú]sica y movimiento|m[uú]sica moderna"
    encontrada = re.findall(especialidades, valor, re.I)
    centro = "Conservatorio" if "conservatorio" in valor else (
        "Escuela de Música" if re.search(r"escuela(?: municipal)? de m[uú]sica", valor) else None
    )
    if centro and encontrada:
        return f"Profesor de {centro} - {encontrada[0].title()}"
    if encontrada:
        return f"Profesor de Música - {encontrada[0].title()}"
    if centro:
        return f"Profesor de {centro}"
    if re.fullmatch(r"profesor(?:/a|a)?(?:es)?(?: de)? m[uú]sica(?: de la plantilla de personal laboral fijo(?:-discontinuo)?)?", valor):
        return "Profesor de Música"
    return None


def _normalizar_docencia_artistica_no_musical(texto):
    """Aplica únicamente el conjunto cerrado aprobado en 9J-2.

    Las expresiones son intencionadamente completas (no se usa similitud ni
    coincidencia por ID), de modo que una nueva variante no entra en
    producción sin pasar primero por una auditoría.
    """
    valor = texto.casefold()
    if not re.search(r"danza|pintura|diseño|cerámica", valor):
        return None
    if re.search(r"\bmonitor|\bt[eé]cnico|\bauxiliar|\boficial|\bayudante|\banimador|\bdirector", valor):
        return None
    if re.fullmatch(r"personal fijo-discontinuo docente de danza escuela de música", valor):
        return "Profesor de Danza"
    if re.fullmatch(r"profesorado de danza", valor):
        return "Profesor de Danza"
    if re.fullmatch(r"maestro de pintura perteneciente a la escala de administración especial", valor):
        return "Profesor de Pintura"
    if re.fullmatch(r"maestra/o de formación \(especialidad pintura\)", valor):
        return "Profesor de Pintura"
    if re.fullmatch(r"profesorado escuela municipal de arte y diseño de formación y orientación laboral de la plantilla de", valor):
        return "Profesor de Diseño"
    if re.fullmatch(r"maestro de taller en el centro ocupacional «el molinet» \(cerámica\)", valor):
        return "Otras especialidades artísticas explícitas"
    return None


def _normalizar_universidad_funcionarial(texto):
    """Reduce únicamente denominaciones inequívocas de cuerpos universitarios.

    Se excluyen expresamente frases que mezclan cuerpos, categorías laborales o
    información de una plaza concreta; esas denominaciones deben conservarse.
    """
    clave = _clave(texto)
    if re.search(r"contratad|ayudante|asociad|laboral|investigador|visitante|sustitut", clave):
        return None
    if re.search(r"profesor(?:es|as)? titulares?.*catedr|catedr.*profesor(?:es|as)? titulares?", clave):
        return None
    patrones = (
        (r"(?:catedratic(?:o|a|os|as)|catedr[aá]tico/a|catedr[aá]ticas y catedr[aá]ticos|profesorado catedratic(?:o|a)|catedra(?:s)?)[ ]+de universidad(?:[ .]|$)", "Catedráticos de Universidad"),
        (r"(?:profesor(?:es|as)? titulares?|profesorado titular|profesor o profesora titular|profesor/a titular|profesoras y profesores titulares)[ ]+de universidad(?:[ .]|$)", "Profesores Titulares de Universidad"),
    )
    for patron, canon in patrones:
        if re.fullmatch(patron, clave):
            return canon
    # Encabezados de convocatoria que explicitan el cuerpo entre paréntesis.
    if re.fullmatch(r"cuerpos docentes universitarios \(catedratic(?:o|a|o/a) de universidad\)(?: mediante promocion interna)?", clave):
        return "Catedráticos de Universidad"
    if re.fullmatch(r"cuerpos docentes universitarios \(profesor(?:es|as)? titulares? de universidad\)", clave):
        return "Profesores Titulares de Universidad"
    return None


def _normalizar_cuerpo_maestros(texto):
    clave = _clave(texto)
    if re.search(r'industrial|obras?|taller|mantenimiento|electric|limpieza|jardinero|arsenal|capataz|laboral|infantil|musica|danza|arte', clave):
        return None
    if re.fullmatch(r'(?:funcionarios docentes (?:en|del|correspondientes al) )?(?:los )?cuerpos? de maestros(?: \(\d+\))?', clave):
        return 'Maestros'
    if re.fullmatch(r'maestros?(?: \(codigo 597\))?', clave):
        return 'Maestros'
    return None


def _normalizar_maestro_educacion_infantil(texto):
    """Canoniza sólo variantes completas de Maestro de Educación Infantil."""
    clave = _clave(texto)
    patron = r"maestr(?:o/a|a/o|a|o)(?:-a)? (?:(?:de|en) )?educacion infantil"
    if re.fullmatch(patron, clave) or re.fullmatch(r"maestr(?:o/a|a/o|a|o) educacion infantil", clave):
        return "Maestro de Educación Infantil"
    if clave in {
        "maestro/maestra en educacion infantil",
        "maestro-a de educacion infantil",
        "maestro o maestra de educacion infantil",
    }:
        return "Maestro de Educación Infantil"
    return None


def _normalizar_maestro_educacion_fisica(texto):
    """Canoniza únicamente las dos variantes validadas de Educación Física."""
    clave = _clave(texto)
    if clave in {"maestro de educacion fisica", "maestro/a de educacion fisica"}:
        return "Maestro de Educación Física"
    return None


def _normalizar_bomberos(texto):
    """Canoniza sólo literales completos auditados de Bomberos.

    Conserva la distinción profesional Bombero/Bombero-Conductor y no toca
    mandos, especialidades ni puestos compuestos.
    """
    clave = _clave(texto)
    if clave in {"bombero", "bombero/a"}:
        return "Bombero"
    if clave in {
        "bombero conductor", "bombero-conductor",
        "bombero/a conductor/a", "bombero/a-conductor/a",
    }:
        return "Bombero-Conductor"
    return None


def _normalizar_bibliotecas_archivos(texto):
    """Canoniza sólo variantes completas validadas de Biblioteca.

    No alcanza Archivo, Museos, escalas, auxiliares técnicos, ayudantes ni
    puestos con mando o funciones combinadas.
    """
    clave = _clave(texto)
    if clave in {"bibliotecario", "bibliotecario/a", "bibliotecaria", "bibliotecaria/o"}:
        return "Bibliotecario"
    if clave in {"auxiliar de biblioteca", "auxiliar biblioteca"}:
        return "Auxiliar de Biblioteca"
    return None


def _normalizar_tecnicos_informaticos(texto):
    """Canoniza únicamente cinco conjuntos informáticos auditados y cerrados.

    Cada literal mantiene su nivel y su formulación (``de`` frente a ``en``),
    evitando convertir sistemas, redes, programación, cuerpos o escalas en un
    técnico genérico.
    """
    clave = _clave(texto)
    return next((canon for canon, variantes in REGLAS_TECNICOS_INFORMATICOS.items() if clave in variantes), None)


def _normalizar_enfermeria(texto):
    """Canoniza sólo variantes completas de género de Enfermero.

    DUE, ATS, auxiliares, especialidades, mandos y expresiones compuestas se
    excluyen deliberadamente: su equivalencia requiere evidencia contextual.
    """
    clave = _clave(texto)
    return next((canon for canon, variantes in REGLAS_ENFERMERIA.items() if clave in variantes), None)


def _normalizar_limpieza(texto):
    """Aplica sólo conjuntos completos que conservan categoría y mando."""
    clave = _clave(texto)
    return next((canon for canon, variantes in REGLAS_LIMPIEZA.items() if clave in variantes), None)

def _normalizar_conductores(texto):
    """Sólo conductor/a aislado; vehículos, rangos y compuestos se preservan."""
    clave = _clave(texto)
    return next((canon for canon, variantes in REGLAS_CONDUCTORES.items() if clave in variantes), None)


def _normalizar_psicologia(texto):
    """Canoniza sólo variantes completas de género del puesto Psicólogo.

    No usa prefijos ni subcadenas: Psicología Clínica, sanitario, educativa,
    técnica, facultativa, escalas, mandos y composiciones se preservan.
    """
    clave = _clave(texto)
    return next((canon for canon, variantes in REGLAS_PSICOLOGIA.items() if clave in variantes), None)


def _normalizar_trabajo_social(texto):
    """Sólo formas completas del puesto individual; no asistentes ni técnicos."""
    clave = _clave(texto)
    return next((canon for canon, variantes in REGLAS_TRABAJO_SOCIAL.items() if clave in variantes), None)


def _normalizar_cocina(texto):
    """Sólo cocinero/a aislado; categorías, ámbitos, mandos y compuestos no entran."""
    clave = _clave(texto)
    return next((canon for canon, variantes in REGLAS_COCINA.items() if clave in variantes), None)


def _normalizar_primer_bloque(texto):
    """Canoniza sólo los literales aislados A aprobados en PASO 72.

    Los conjuntos A_NUEVO de PASO 72-C son variantes ortográficas/género ya
    resueltas por reglas previas; aquí no se generalizan sus prefijos para no
    perder especialidades, niveles, mandos ni destinos.
    """
    clave = _clave(texto)
    return next((canon for canon, variantes in REGLAS_PRIMER_BLOQUE.items() if clave in variantes), None)


def _normalizar_ortografia_puesto(texto):
    """Corrige sólo tokens OA auditables y la primera letra alfabética."""
    def tilde(coincidencia):
        palabra = coincidencia.group(0)
        correccion = TILDES_ORTOGRAFICAS_SEGURAS.get(palabra.lower())
        return correccion.capitalize() if correccion and palabra[0].isupper() else (correccion or palabra)
    resultado = re.sub(r"\b[\wáéíóúüñÁÉÍÓÚÜÑ]+\b", tilde, texto)
    for indice, caracter in enumerate(resultado):
        if caracter.isalpha():
            return resultado[:indice] + caracter.upper() + resultado[indice + 1:]
    return resultado


def _normalizar_educador_infantil(texto):
    """Canoniza sólo fórmulas completas de Educador Infantil.

    No absorbe referencias a centro, relación laboral ni categorías como
    técnico, auxiliar, monitor, maestro o dirección.
    """
    clave = _clave(texto)
    patron = r"educador(?:/a|-a|a)?(?: de)?(?: educacion)? infantil"
    if re.fullmatch(patron, clave) or re.fullmatch(
        r"educador(?:/a|-a|a)? \(infantil\)", clave
    ):
        return "Educador Infantil"
    return None


def _normalizar_tecnico_educacion_infantil(texto):
    """Canoniza categorías técnicas completas sin fusionar sus niveles."""
    clave = _clave(texto)
    reglas = (
        (r"tecnico(?:/a|-a|a)? de educacion infantil", "Técnico de Educación Infantil"),
        (r"tecnico(?:/a|-a|a)? superior de educacion infantil", "Técnico Superior de Educación Infantil"),
        (r"tecnico(?:/a|-a|a)? especialista en educacion infantil", "Técnico Especialista en Educación Infantil"),
    )
    for patron, canon in reglas:
        if re.fullmatch(patron, clave):
            return canon
    return None


def _normalizar_secundaria_explicita(texto):
    """Solo variantes completas del cuerpo, sin especialidad ni mezcla."""
    clave = _clave(texto)
    if re.fullmatch(r"profesor de ensenanza secundaria", clave):
        return "Profesores de Enseñanza Secundaria"
    if re.fullmatch(r"profesores de ensenanza secundaria \(codigo 590\) situadas en las ciudades de ceuta y melilla", clave):
        return "Profesores de Enseñanza Secundaria"
    return None


def _normalizar_puesto_una_vez(texto):
    """Aplica una pasada del pipeline sobre una representación preparada."""
    texto = _preparar_texto(texto)
    if texto is None:
        return None
    clave_original = _clave(texto)
    # Docencia musical aprobada en Fase 7, paso 9H-4. La regla exige una
    # función docente explícita y conserva centro e instrumento/especialidad.
    # Músicos, instrumentistas, directores y personal de apoyo quedan fuera.
    musical = _normalizar_docencia_musical(texto)
    if musical:
        return musical
    artistica = _normalizar_docencia_artistica_no_musical(texto)
    if artistica:
        return artistica
    universitaria = _normalizar_universidad_funcionarial(texto)
    if universitaria:
        return universitaria
    maestros = _normalizar_cuerpo_maestros(texto)
    if maestros:
        return maestros
    maestro_infantil = _normalizar_maestro_educacion_infantil(texto)
    if maestro_infantil:
        return maestro_infantil
    maestro_fisica = _normalizar_maestro_educacion_fisica(texto)
    if maestro_fisica:
        return maestro_fisica
    bomberos = _normalizar_bomberos(texto)
    if bomberos:
        return bomberos
    bibliotecas = _normalizar_bibliotecas_archivos(texto)
    if bibliotecas:
        return bibliotecas
    tecnicos_informaticos = _normalizar_tecnicos_informaticos(texto)
    if tecnicos_informaticos:
        return tecnicos_informaticos
    enfermeria = _normalizar_enfermeria(texto)
    if enfermeria:
        return enfermeria
    limpieza = _normalizar_limpieza(texto)
    if limpieza:
        return limpieza
    conductores = _normalizar_conductores(texto)
    if conductores:
        return conductores
    psicologia = _normalizar_psicologia(texto)
    if psicologia:
        return psicologia
    trabajo_social = _normalizar_trabajo_social(texto)
    if trabajo_social:
        return trabajo_social
    cocina = _normalizar_cocina(texto)
    if cocina:
        return cocina
    primer_bloque = _normalizar_primer_bloque(texto)
    if primer_bloque:
        return primer_bloque
    educador_infantil = _normalizar_educador_infantil(texto)
    if educador_infantil:
        return educador_infantil
    tecnico_infantil = _normalizar_tecnico_educacion_infantil(texto)
    if tecnico_infantil:
        return tecnico_infantil
    secundaria = _normalizar_secundaria_explicita(texto)
    if secundaria:
        return secundaria
    # Cuerpos docentes inequívocos.  Se limitan a formulaciones explícitas;
    # no se infiere docencia por ámbito o por la palabra «profesor» aislada.
    reglas_docentes = (
        (r"^(?:funcionarios docentes del )?(?:cuerpo de )?maestros$", "Maestros"),
        (r"^funcionarios docentes para el cuerpo de maestros$", "Maestros"),
        (r"^(?:funcionarios docentes del )?(?:cuerpo de )?profesores? de ensenanza secundaria$", "Profesores de Enseñanza Secundaria"),
        (r"^(?:funcionarios docentes del )?(?:cuerpo de )?profesores? tecnicos? de formacion profesional$", "Profesores Técnicos de Formación Profesional"),
        (r"^(?:funcionarios docentes del )?(?:cuerpo de )?profesores? de escuelas oficiales de idiomas$", "Profesores de Escuelas Oficiales de Idiomas"),
        (r"^catedraticos? de universidad$", "Catedráticos de Universidad"),
        (r"^profesores? titulares? de universidad$", "Profesores Titulares de Universidad"),
    )
    for patron, canon in reglas_docentes:
        if re.fullmatch(patron, clave_original, re.I):
            return canon
    _, clasificacion_familia, canon_familia, _ = clasificar_familia_puesto(texto)
    if clasificacion_familia == "alta_confianza":
        return canon_familia
    variante_no_aprobada = (
        "ingeniera/o tecnica/o industrial " in clave_original
        or "ingeniera/o tecnico industrial " in clave_original
    )
    titulacion = None if variante_no_aprobada else _normalizar_titulacion(texto)
    if titulacion:
        return titulacion
    # Esta formulación de género compuesta está excluida expresamente de la
    # equivalencia de titulaciones. Tampoco se reduce ortotipográficamente, o
    # una pasada posterior perdería el contexto de exclusión y la absorbería.
    if not variante_no_aprobada:
        texto = _normalizar_genero(texto)
    texto = _recuperar_grafia(texto)

    clave = _clave(texto)
    if clave in CANONES:
        return CANONES[clave]
    titulacion = None if variante_no_aprobada else _normalizar_titulacion(texto)
    if titulacion:
        return titulacion
    # Normaliza de forma explícita el núcleo y conserva cualquier especialidad
    # o descriptor posterior.
    nucleo = "Ingeniero Técnico Industrial"
    patron_nucleo = re.compile(r"(?i)^ingeniero\s+t[eé]cnico\s+industrial\b")
    if patron_nucleo.search(texto):
        return patron_nucleo.sub(nucleo, texto, count=1)
    return texto


def normalizar_puesto(texto):
    """Devuelve un canon conservador y estable basado en ``texto``.

    Algunas transformaciones ortotipográficas habilitan una regla posterior
    (por ejemplo, recuperan una grafía o completan una forma de género). Se
    ejecuta el pipeline hasta que no haya cambios, de modo que la salida de la
    API pública nunca requiera una segunda llamada para estabilizarse.
    """
    resultado = _preparar_texto(texto)
    if resultado is None:
        return None
    vistos = set()
    while resultado not in vistos:
        vistos.add(resultado)
        siguiente = _normalizar_puesto_una_vez(resultado)
        if siguiente == resultado:
            return _normalizar_ortografia_puesto(resultado)
        resultado = siguiente
    # Las reglas son reductoras; esta salvaguarda evita un bucle silencioso si
    # una futura regla introdujera una oscilación.
    return resultado
