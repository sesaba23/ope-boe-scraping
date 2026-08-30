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
    "administrativo": "Administrativo",
    "arquitecto": "Arquitecto",
    "arquitecto tecnico": "Arquitecto Técnico",
    "auxiliar administrativo": "Auxiliar Administrativo",
    "educador social": "Educador Social",
    "ingeniero tecnico industrial": "Ingeniero Técnico Industrial",
    "tecnico de administracion general": "Técnico de Administración General",
    "trabajador social": "Trabajador Social",
}


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


def _normalizar_genero(texto):
    resultado = texto
    for patron, reemplazo in REGLAS_GENERO:
        resultado = re.sub(rf"(?i)\b(?:{patron})(?!\w)", reemplazo, resultado)
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


def normalizar_puesto(texto):
    """Devuelve un canon conservador basado exclusivamente en ``texto``."""
    if texto is None:
        return None
    texto = unicodedata.normalize("NFKC", str(texto))
    texto = texto.translate(str.maketrans({"\u2013": "-", "\u2014": "-", "\u2212": "-"}))
    texto = re.sub(r"\s+", " ", texto).strip()
    clave_original = _clave(texto)
    if not texto:
        return None
    texto = re.sub(r"\s*/\s*", "/", texto)
    texto = re.sub(r"\s*([,;:])\s*", r"\1 ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    variante_no_aprobada = (
        "ingeniera/o tecnica/o industrial " in clave_original
        or "ingeniera/o tecnico industrial " in clave_original
    )
    titulacion = None if variante_no_aprobada else _normalizar_titulacion(texto)
    if titulacion:
        return titulacion
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
