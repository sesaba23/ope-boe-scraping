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

# Familias profesionales aprobadas en Fase 4.  Estas reglas se mantienen
# separadas de los cánones ortotipográficos: eliminan sólo variación de una
# misma categoría y nunca rangos, especialidades o descriptores dudosos.
FAMILIAS_PUESTO_CANONICAS = {
    "policia_local": "Policía Local",
    "auxiliar_administrativo": "Auxiliar Administrativo",
    "administrativo": "Administrativo",
}
RANGOS_POLICIA_LOCAL = re.compile(r"\b(?:inspector|subinspector|oficial|jefe|comisario|intendente)\b")
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


def clasificar_familia_puesto(texto):
    """Clasifica las familias Fase 4 sin decidir equivalencias dudosas.

    Devuelve ``(familia, clasificación, canon, motivo)``.  El motor sólo usa
    los casos ``alta_confianza``; el resto se expone para auditoría y tests.
    """
    texto = _preparar_texto(texto)
    clave = _clave(texto or "")
    if re.search(r"\bpolicia(?:s)? local(?:es)?\b", clave):
        if RANGOS_POLICIA_LOCAL.search(clave) or re.search(r"\b(?:tecnico|coordinador)\b", clave):
            return "policia_local", "excluida", None, "rango o categoría profesional distinta"
        if re.fullmatch(r"(?:agentes?(?: de(?: la)?)? )?policia(?:s)? local(?:es)?", clave):
            return "policia_local", "alta_confianza", FAMILIAS_PUESTO_CANONICAS["policia_local"], "denominación base o agente equivalente"
        return "policia_local", "dudosa", None, "contiene Policía Local con texto accesorio no validado"
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


def _normalizar_puesto_una_vez(texto):
    """Aplica una pasada del pipeline sobre una representación preparada."""
    texto = _preparar_texto(texto)
    if texto is None:
        return None
    clave_original = _clave(texto)
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
            return resultado
        resultado = siguiente
    # Las reglas son reductoras; esta salvaguarda evita un bucle silencioso si
    # una futura regla introdujera una oscilación.
    return resultado
