"""Clasificador experimental v1 del tipo funcional de personal BOE.

El módulo es deliberadamente independiente de SQLite, de la extracción y de la
persistencia. ``clasificar_tipo_personal`` sólo recibe mappings (por ejemplo
``sqlite3.Row`` o ``dict``) y devuelve una explicación reproducible.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

VERSION = "tipo-personal-v1"
CATEGORIAS = (
    "Funcionario",
    "Laboral",
    "Estatutario",
    "Universitario",
    "Militar",
    "Otros",
    "No determinado",
)
TIPOS_PERSONAL = CATEGORIAS
CONFIANZAS = ("alta", "media", "baja")
DEPENDENCIAS_OPOSICION = (
    "puesto", "puesto_normalizado", "administracion", "administracion_normalizada",
    "escala", "subescala", "clase", "ambito", "tipo_entidad", "sistema", "turno",
)
DEPENDENCIAS_PUBLICACION = (
    "titulo_original", "departamento_boe", "administracion_resuelta", "familia_administrativa",
)


def normalizar_texto(valor: object) -> str:
    """Normaliza texto sólo para comparar; nunca modifica el valor de entrada."""
    texto = "" if valor is None else str(valor)
    texto = unicodedata.normalize("NFD", texto.casefold())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"[^\w]+", " ", texto, flags=re.UNICODE)
    return re.sub(r"\s+", " ", texto).strip()


def _valor(registro: Mapping | None, *nombres: str) -> str:
    if registro is None:
        return ""
    for nombre in nombres:
        try:
            valor = registro.get(nombre)  # dict-like mappings
        except AttributeError:
            try:
                valor = registro[nombre]  # sqlite3.Row
            except (IndexError, KeyError):
                valor = None
        if valor not in (None, ""):
            return normalizar_texto(valor)
    return ""


def _contexto(oposicion: Mapping, publicacion: Mapping | None) -> dict[str, str]:
    campos = {
        nombre: _valor(oposicion, nombre)
        for nombre in DEPENDENCIAS_OPOSICION
    }
    campos.update({
        "publicacion_titulo": _valor(publicacion, "titulo_original", "titulo") if publicacion else "",
        "publicacion_departamento": _valor(publicacion, "departamento_boe") if publicacion else "",
        "publicacion_administracion": _valor(publicacion, "administracion_resuelta") if publicacion else "",
        "publicacion_familia": _valor(publicacion, "familia_administrativa") if publicacion else "",
    })
    campos["texto_puesto"] = " ".join(campos[x] for x in ("puesto", "puesto_normalizado"))
    campos["texto_contexto"] = " ".join(campos.values())
    return campos


def _contiene(texto: str, *patrones: str) -> bool:
    return any(re.search(patron, texto) for patron in patrones)


def _texto_fila(contexto: dict[str, str]) -> str:
    return " ".join(contexto[campo] for campo in (
        "puesto", "puesto_normalizado", "administracion", "administracion_normalizada",
        "escala", "subescala", "clase", "ambito", "tipo_entidad", "sistema", "turno",
    ))


def _administracion_universitaria(contexto: dict[str, str]) -> bool:
    administracion = contexto["administracion"]
    if "universidad popular" in administracion:
        return False
    return administracion == "universidades" or bool(
        re.match(r"(?:universidad|universitat|rectorado de la universidad)\b", administracion)
    )


def _arsenales_civiles(puesto: str) -> bool:
    return _contiene(
        puesto,
        r"\b(?:ingenieros tecnicos|maestros|oficiales) de arsenales de la armada\b",
    )


def _puesto_administrativo_reconocible(puesto: str) -> bool:
    # "Policía Local" entre paréntesis puede indicar el destino de una plaza
    # de mantenimiento o apoyo, no el cuerpo al que pertenece la plaza.
    policia_de_apoyo = _contiene(
        puesto,
        r"\b(?:mantenimiento|limpieza|conserje|administrativ[oa])\b.{0,60}\bpolicia local\b",
        r"\bauxiliar(?:es)?\s+(?:de\s+)?(?:la\s+)?policia local\b",
    )
    return _contiene(
        puesto,
        r"tecnico(?:/a)? de administracion general",
        r"cuerpo de .+ del estado",
    ) or (_contiene(puesto, r"policia local") and not policia_de_apoyo)


def _escala_funcionarial_reconocible(escala: str) -> bool:
    return _contiene(
        escala,
        r"administracion (?:general|especial)",
        r"administrativ[oa] general",
        r"\b(?:tecnica|basica|servicios especiales|administrativa|subalterna|especial|admon)\b",
    )


def _militar_inequivoco(puesto: str) -> bool:
    if _arsenales_civiles(puesto):
        return False
    if _contiene(puesto, r"guardia civil") and _contiene(puesto, r"fuerzas armadas"):
        return False  # Fila mixta: no representa un único colectivo.
    if _contiene(puesto, r"reserva.{0,50}militar", r"dirigida.{0,50}militar", r"plaza.{0,50}militar", r"reservad[oa].{0,50}tropa"):
        return False
    return _contiene(
        puesto,
        r"fuerzas armadas",
        r"cuerpos generales de los ejercitos",
        r"\b(?:ejercito|ejercitos)\b",
        r"\barmada\b",
        r"cuerpo[s]? militar",
        r"militar(?:es)? profesional(?:es)?",
        r"tropa y marineria",
    )


def _laboral_explicito(contexto: dict[str, str]) -> bool:
    if contexto["escala"] == "laboral":
        return True
    # El título puede agrupar regímenes distintos (p. ej., ingreso en un cuerpo
    # y cambio de régimen de personal laboral); no lo atribuimos a cada fila.
    todo = " ".join(contexto[campo] for campo in (
        "puesto", "puesto_normalizado", "escala", "subescala", "clase",
    ))
    if _contiene(
        todo,
        r"personal laboral",
        r"plantilla de personal laboral",
        r"laboral fijo",
        r"laboral temporal",
        r"contrato laboral",
        r"regimen laboral",
    ):
        return True
    # En subescala/clase, "grupo profesional C1" también describe plazas de
    # Administración Especial funcionariales (BOE-A-2023-17553).
    if _contiene(contexto["texto_puesto"], r"\bgrupo profesional"):
        return True
    convenio_negado = _contiene(
        todo,
        r"\bno (?:sujet[oa]s?|acogid[oa]s?|adscrit[oa]s?) al convenio",
        r"\bsin convenio",
        r"\bexcluid[oa]s? del convenio",
    )
    return _contiene(todo, r"convenio colectivo") and not convenio_negado


def _familias_detectadas(contexto: dict[str, str]) -> list[str]:
    """Devuelve todas las familias con evidencia, antes de aplicar prioridad."""
    puesto = contexto["texto_puesto"]
    todo = _texto_fila(contexto)
    familias = []
    universidad = (
        contexto["ambito"] == "universitario"
        or contexto["tipo_entidad"] == "universidad"
        or _administracion_universitaria(contexto)
        or _contiene(puesto, r"cuerpos docentes universitarios", r"profesor(?:a)? titular de universidad", r"catedratic[oa] de universidad", r"personal docente e investigador")
        or (_contiene(puesto, r"\bpdi\b") and _contiene(todo, r"universidad|universitario|docente e investigador"))
    )
    if universidad:
        familias.append("Universitario")
    if _militar_inequivoco(puesto):
        familias.append("Militar")
    if _contiene(todo, r"personal estatutario", r"estatutario fijo", r"estatutario temporal"):
        familias.append("Estatutario")
    if _laboral_explicito(contexto):
        familias.append("Laboral")
    inferencia_funcionaria = (
        _contiene(todo, r"personal funcionario", r"funcionario de carrera", r"funcionari[oa]s? de carrera", r"plantilla funcionarial", r"administracion general", r"administracion especial")
        or _puesto_administrativo_reconocible(puesto)
        or _arsenales_civiles(puesto)
        or (
            _escala_funcionarial_reconocible(contexto["escala"])
            and (contexto["subescala"] not in {"", "--", "no disponible"} or contexto["clase"] not in {"", "--", "no disponible"})
        )
    )
    funcionarial_explicito = _contiene(
        todo, r"personal funcionario", r"funcionario de carrera",
        r"funcionari[oa]s? de carrera", r"plantilla funcionarial",
    ) or _arsenales_civiles(puesto)
    if inferencia_funcionaria and (funcionarial_explicito or not _contiene(puesto, r"\bfundacion\b")):
        familias.append("Funcionario")
    if _contiene(todo, r"personal eventual", r"personal de confianza"):
        familias.append("Otros")
    return familias


def _clasificar(contexto: dict[str, str]) -> tuple[str, str, list[str]]:
    puesto = contexto["texto_puesto"]
    todo = _texto_fila(contexto)
    reglas: list[str] = []

    # 1. Sector universitario: las señales estructuradas prevalecen sobre el
    # régimen jurídico que pueda aparecer en la misma denominación.
    if contexto["ambito"] == "universitario":
        reglas.append("ambito_universitario")
        return "Universitario", "alta", reglas
    if contexto["tipo_entidad"] == "universidad":
        reglas.append("tipo_entidad_universidad")
        return "Universitario", "alta", reglas
    if _administracion_universitaria(contexto):
        reglas.append("administracion_universidad")
        return "Universitario", "alta", reglas
    if _contiene(
        puesto,
        r"cuerpos docentes universitarios",
        r"profesor(?:a)? titular de universidad",
        r"catedratic[oa] de universidad",
        r"personal docente e investigador",
    ):
        reglas.append("cuerpo_docente_universitario_explicito")
        return "Universitario", "alta", reglas
    if _contiene(puesto, r"\bpdi\b") and _contiene(todo, r"universidad|universitario|docente e investigador"):
        reglas.append("pdi_contexto_universitario")
        return "Universitario", "alta", reglas

    if _contiene(puesto, r"personal funcionario", r"funcionario(?:s)? de carrera", r"\bfuncionarios?\b") and _contiene(
        puesto, r"personal laboral", r"laboral fijo", r"regimen laboral",
    ):
        return "No determinado", "baja", ["colectivos_mezclados_en_fila"]
    # En anuncios de funcionarización, la categoría laboral de procedencia
    # puede coexistir con la escala funcionarial de destino en una misma fila.
    if _contiene(contexto["subescala"], r"\bcategoria laboral\b") and _contiene(
        contexto["escala"], r"administracion (?:general|especial)",
    ):
        return "No determinado", "baja", ["regimen_de_origen_y_destino"]
    # Una extracción puede reunir dos plazas de distinto régimen en el puesto.
    if _contiene(puesto, r"\bregimen laboral\b", r"\bpersonal laboral\b") and _contiene(
        puesto, r"\by (?:otra|una|\d+) plazas? de .{0,80}administracion general\b",
    ):
        return "No determinado", "baja", ["colectivos_mezclados_en_fila"]

    # 2. Militar: una reserva o requisito militar no convierte el puesto civil.
    if _militar_inequivoco(puesto):
        reglas.append("colectivo_militar_explicito")
        return "Militar", "alta", reglas

    # 3. Sólo evidencia explícita para estatutario.
    if _contiene(todo, r"personal estatutario", r"estatutario fijo", r"estatutario temporal"):
        reglas.append("personal_estatutario_explicito")
        return "Estatutario", "alta", reglas

    # 4. Laboral explícito. Convenios negados no prueban relación laboral.
    if _laboral_explicito(contexto):
        reglas.append("relacion_laboral_explicita")
        return "Laboral", "alta", reglas

    # 5. Funcionario: primero evidencia textual alta; después inferencia
    # contextual media. Una escala aislada no basta.
    if _contiene(todo, r"personal funcionario", r"funcionario de carrera", r"funcionari[oa]s? de carrera", r"plantilla funcionarial"):
        reglas.append("personal_funcionario_explicito")
        return "Funcionario", "alta", reglas
    if _arsenales_civiles(puesto):
        reglas.append("cuerpo_civil_arsenales")
        return "Funcionario", "alta", reglas
    # La escala administrativa también aparece en plazas laborales de
    # fundaciones; por sí sola no prueba régimen funcionarial.
    if _contiene(puesto, r"\bfundacion\b"):
        return "No determinado", "baja", ["fundacion_sin_regimen_explicito"]
    inferencias = []
    if _contiene(todo, r"administracion general", r"administracion especial"):
        inferencias.append("administracion_general_o_especial")
    if _puesto_administrativo_reconocible(puesto):
        inferencias.append("puesto_administrativo_reconocible")
    escala = contexto["escala"] not in {"", "--", "no disponible"}
    subescala = contexto["subescala"] not in {"", "--", "no disponible"}
    clase = contexto["clase"] not in {"", "--", "no disponible"}
    # Una profesión repetida como «escala» y un grupo genérico (C/C2...) no
    # acreditan régimen: BOE-A-2023-12107 contiene precisamente una plaza
    # laboral con escala «Auxiliar Administrativo» y clase «grupo C».
    escala_reconocible = _escala_funcionarial_reconocible(contexto["escala"])
    # Un extractor histórico puede arrastrar la subescala/clase de la plaza
    # anterior. No aceptamos una estructura técnicamente incompatible con el
    # puesto como evidencia funcionarial (BOE-A-2005-1483).
    estructura_incompatible = (
        _contiene(puesto, r"\b(?:peon(?:es)?|personal de limpieza|limpiador(?:a|es)?)\b")
        and _contiene(contexto["subescala"], r"\btecnica\b")
        and _contiene(contexto["clase"], r"\bsuperior\b")
    )
    if estructura_incompatible:
        return "No determinado", "baja", ["estructura_incompatible_con_puesto"]
    if escala and (subescala or clase or inferencias) and (inferencias or subescala or escala_reconocible):
        inferencias.append("escala_con_contexto")
    if subescala and (clase or inferencias):
        inferencias.append("subescala_con_contexto")
    # «Administración General/Especial» aislado no identifica el régimen: el
    # BOE usa también esas denominaciones en plazas expresamente laborales.
    # Conservamos la señal como contexto, pero exigimos otra evidencia.
    if inferencias and inferencias != ["administracion_general_o_especial"]:
        reglas.extend(inferencias)
        return "Funcionario", "media", reglas

    # 6. Otros sólo con evidencia positiva. El fallback es No determinado.
    if _contiene(todo, r"personal eventual", r"personal de confianza"):
        reglas.append("personal_eventual_explicito")
        return "Otros", "media", reglas
    return "No determinado", "baja", ["sin_evidencia_suficiente"]


def clasificar_tipo_personal(
    oposicion: Mapping,
    publicacion: Mapping | None = None,
) -> dict[str, object]:
    """Clasifica una oposición sin consultar ni modificar estado externo."""
    contexto = _contexto(oposicion, publicacion)
    categoria, confianza, reglas = _clasificar(contexto)
    grupos = []
    if categoria == "Funcionario" and any(
        regla in reglas for regla in (
            "administracion_general_o_especial", "escala_con_contexto",
            "subescala_con_contexto",
        )
    ):
        grupos.append("estructura_funcionarial")
    if "puesto_administrativo_reconocible" in reglas:
        grupos.append("denominacion_inequivoca")
    if categoria in {"Laboral", "Estatutario"}:
        grupos.append("regimen_explicito")
    if categoria in {"Universitario", "Militar"}:
        grupos.append("colectivo_inequivoco")
    if categoria == "Funcionario" and any(
        regla in reglas for regla in ("personal_funcionario_explicito", "cuerpo_civil_arsenales")
    ):
        grupos.append("regimen_o_cuerpo_explicito")
    if categoria == "Otros":
        grupos.append("regimen_explicito")
    if categoria == "No determinado" and reglas != ["sin_evidencia_suficiente"]:
        grupos.append("conflicto_o_incompatibilidad")
    return {
        "categoria": categoria,
        "confianza": confianza,
        "reglas_aplicadas": reglas,
        "grupos_evidencia": grupos,
        "familias_detectadas": _familias_detectadas(contexto),
        "version": VERSION,
    }
