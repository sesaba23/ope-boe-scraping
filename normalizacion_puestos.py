"""Normalización conservadora y auditable de denominaciones de puestos."""

import re
import unicodedata


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


def normalizar_puesto(texto):
    """Devuelve un canon conservador basado exclusivamente en ``texto``."""
    if texto is None:
        return None
    texto = unicodedata.normalize("NFKC", str(texto))
    texto = texto.translate(str.maketrans({"\u2013": "-", "\u2014": "-", "\u2212": "-"}))
    texto = re.sub(r"\s+", " ", texto).strip()
    if not texto:
        return None
    texto = re.sub(r"\s*/\s*", "/", texto)
    texto = re.sub(r"\s*([,;:])\s*", r"\1 ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    texto = _normalizar_genero(texto)
    texto = _recuperar_grafia(texto)

    clave = _clave(texto)
    if clave in CANONES:
        return CANONES[clave]
    # Normaliza de forma explícita el núcleo y conserva cualquier especialidad
    # o descriptor posterior.
    nucleo = "Ingeniero Técnico Industrial"
    patron_nucleo = re.compile(r"(?i)^ingeniero\s+t[eé]cnico\s+industrial\b")
    if patron_nucleo.search(texto):
        return patron_nucleo.sub(nucleo, texto, count=1)
    return texto
