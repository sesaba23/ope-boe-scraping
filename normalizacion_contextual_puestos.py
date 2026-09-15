"""Normalización contextual trazable, separada del normalizador textual."""
from __future__ import annotations

from dataclasses import dataclass

from normalizacion_puestos import _clave, _preparar_texto, normalizar_puesto


AMBIGUOS_POLICIA = {"policia"}
PREFIJOS_MUNICIPALES = ("ayuntamiento de", "concello de", "ajuntament de", "udal")


@dataclass(frozen=True)
class ResultadoNormalizacionContextual:
    original: str | None
    textual: str | None
    normalizado: str | None
    cambio_contextual: bool
    regla: str | None
    confianza: str | None
    evidencia: tuple[str, ...]


def _ambiguo_policia(texto):
    return _clave(_preparar_texto(texto) or "") in AMBIGUOS_POLICIA


def _resultado(original, textual, *, normalizado=None, regla=None, evidencia=()):
    final = textual if normalizado is None else normalizado
    return ResultadoNormalizacionContextual(
        original=original, textual=textual, normalizado=final,
        cambio_contextual=final != textual, regla=regla,
        confianza="ALTA" if regla else None, evidencia=tuple(evidencia),
    )


def normalizar_puesto_contextual(
    puesto, *, administracion=None, ambito=None, tipo_entidad=None,
    escala=None, subescala=None, sistema=None, municipio=None, provincia=None,
):
    """Complementa la normalización textual sólo con evidencia positiva.

    La API recibe campos simples y no depende de SQLite, Flask o pandas. Las
    reglas se limitan a puestos ``Policía`` aislados; cualquier puesto ya
    reconocido textualmente conserva su resultado.
    """
    textual = normalizar_puesto(puesto)
    # La capa ortográfica puede añadir tildes o mayúscula inicial al texto
    # sin resolver todavía la ambigüedad Policía. La decisión contextual se
    # bloquea sólo si cambió la clave semántica, no por esa presentación.
    if not _ambiguo_policia(puesto) or _clave(textual or "") != _clave(_preparar_texto(puesto) or ""):
        return _resultado(puesto, textual)
    if (ambito, tipo_entidad, administracion, escala, sistema) == (
        "ESTATAL", "ESTATAL", "Ministerio del Interior", "Básica", "Oposición"
    ):
        return _resultado(
            puesto, textual, normalizado="Policía Nacional",
            regla="POLICIA_NACIONAL_MINISTERIO_INTERIOR_ESCALA_BASICA",
            evidencia=("ámbito estatal", "Ministerio del Interior", "Escala Básica", "oposición"),
        )
    admin = (administracion or "").casefold()
    if ambito == "LOCAL" and tipo_entidad == "MUNICIPAL" and admin.startswith(PREFIJOS_MUNICIPALES):
        evidencia = ("ámbito local", "entidad municipal", "administración municipal identificada")
        if municipio:
            return _resultado(
                puesto, textual, normalizado="Policía Local",
                regla="POLICIA_LOCAL_ADMINISTRACION_MUNICIPAL_MUNICIPIO",
                evidencia=evidencia + ("municipio resuelto",),
            )
        if provincia:
            return _resultado(
                puesto, textual, normalizado="Policía Local",
                regla="POLICIA_LOCAL_ADMINISTRACION_MUNICIPAL_PROVINCIA",
                evidencia=evidencia + ("provincia coherente",),
            )
    return _resultado(puesto, textual)


def normalizar_puesto_efectivo(
    puesto, *, administracion=None, ambito=None, tipo_entidad=None,
    escala=None, subescala=None, sistema=None, municipio=None, provincia=None,
):
    """Devuelve el resultado compuesto textual y contextual sin persistir.

    ``normalizar_puesto_contextual`` conserva el resultado textual y aplica
    únicamente reglas contextuales con evidencia positiva. Este punto de
    entrada fija que los recalculadores deben persistir ``normalizado`` y no
    la capa textual aislada.
    """
    return normalizar_puesto_contextual(
        puesto, administracion=administracion, ambito=ambito,
        tipo_entidad=tipo_entidad, escala=escala, subescala=subescala,
        sistema=sistema, municipio=municipio, provincia=provincia,
    )
