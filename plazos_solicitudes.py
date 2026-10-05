"""Extracción conservadora del plazo de presentación de solicitudes.

El BOE no publica este dato con un esquema único. Este módulo conserva la
evidencia textual y sólo calcula una fecha cuando la duración y el punto de
inicio aparecen con suficiente claridad en el documento.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta

from word2number_es import w2n


VERSION = "plazos-solicitudes-v1"
_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
    "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
    "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
_NUMERO = r"(?:\d{1,3}|[a-záéíóúñü]+(?:\s+y\s+[a-záéíóúñü]+){0,3})"
_PATRON_CONTEXTO = re.compile(
    r"(?P<fragmento>.{0,80}(?:plazo|presentaci[oó]n de (?:solicitudes|instancias)|"
    r"solicitudes|presentar(?:se)?\s+(?:las\s+)?solicitudes)"
    r".{0,220})",
    re.IGNORECASE | re.DOTALL,
)
_PATRON_EXPLICITO = re.compile(
    r"(?:hasta|finaliza(?:r[aá]?|s?)|termina(?:r[aá]?|s?)|vence(?:r[aá]?|s?)|concluye|concluir[aá]?)"
    r"[^.]{0,80}?\b(?:el\s+)?(?:d[ií]a\s+)?"
    r"(?P<dia>\d{1,2})\s+de\s+(?P<mes>[a-záéíóúñ]+)\s+de\s+(?P<anio>\d{4})",
    re.IGNORECASE,
)
_PATRON_DURACION = re.compile(
    rf"(?:plazo[^.\n]{{0,100}}?(?:de|ser[aá]|es|por)\s+)?"
    rf"(?P<cantidad>{_NUMERO})\s+"
    r"(?P<unidad>d[ií]as?|mes(?:es)?)"
    r"(?:\s+(?P<tipo>h[aá]biles?|laborables?|naturales?))?",
    re.IGNORECASE,
)


def _fecha(valor) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor or "").strip()
    if not texto:
        return None
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(texto[:10], formato).date()
        except ValueError:
            pass
    coincidencia = re.search(
        r"(?P<dia>\d{1,2})\s+de\s+(?P<mes>[a-záéíóúñ]+)\s+de\s+(?P<anio>\d{4})",
        texto,
        re.IGNORECASE,
    )
    if coincidencia:
        mes = _MESES.get(coincidencia.group("mes").lower())
        if mes:
            try:
                return date(int(coincidencia.group("anio")), mes, int(coincidencia.group("dia")))
            except ValueError:
                return None
    return None


def _numero(texto: str) -> int | None:
    texto = texto.strip().lower()
    if texto in {"un", "una"}:
        return 1
    if texto.isdigit():
        return int(texto)
    try:
        valor = w2n.word_to_num(texto)
    except (TypeError, ValueError):
        return None
    return int(valor) if isinstance(valor, (int, float)) and int(valor) > 0 else None


def _fecha_explicita(texto: str) -> date | None:
    coincidencia = _PATRON_EXPLICITO.search(texto)
    if not coincidencia:
        return None
    mes = _MESES.get(coincidencia.group("mes").lower())
    if not mes:
        return None
    try:
        return date(int(coincidencia.group("anio")), mes, int(coincidencia.group("dia")))
    except ValueError:
        return None


def _sumar_dias_habiles(inicio: date, cantidad: int, festivos=None) -> date:
    festivos = {str(valor)[:10] for valor in (festivos or ())}

    def es_habil(valor):
        return valor.weekday() < 5 and valor.isoformat() not in festivos

    actual, restantes = inicio, cantidad
    while not es_habil(actual):
        actual += timedelta(days=1)
    while restantes > 1:
        actual += timedelta(days=1)
        if es_habil(actual):
            restantes -= 1
    return actual


def recalcular_fin_dias_habiles(fecha_inicio, cantidad, festivos):
    """Recalcula una fecha ya extraída usando un conjunto de festivos."""
    inicio = _fecha(fecha_inicio)
    if inicio is None:
        raise ValueError(f"Fecha de inicio no válida: {fecha_inicio!r}")
    return _sumar_dias_habiles(inicio, int(cantidad), festivos).isoformat()


def _sumar_meses(inicio: date, cantidad: int) -> date:
    indice = inicio.month - 1 + cantidad
    anio, mes = inicio.year + indice // 12, indice % 12 + 1
    return date(anio, mes, min(inicio.day, calendar.monthrange(anio, mes)[1])) - timedelta(days=1)


def extraer_plazo_presentacion(texto: str, fecha_publicacion=None, festivos=None) -> dict[str, str | int | None]:
    """Extrae plazo, fecha de vencimiento y evidencia desde texto BOE.

    Devuelve siempre el mismo contrato. ``fecha_fin_plazo`` queda a ``None``
    cuando no hay una fecha explícita ni una duración calculable.
    """
    limpio = re.sub(r"\s+", " ", str(texto or "")).strip()
    vacio = {
        "Plazo_solicitudes": None,
        "Fecha_inicio_plazo": None,
        "Fecha_fin_plazo": None,
        "Plazo_calculo": None,
        "Evidencia_plazo": None,
    }
    if not limpio:
        return vacio
    contexto = next((m.group("fragmento") for m in _PATRON_CONTEXTO.finditer(limpio)), None)
    if not contexto:
        return vacio
    inicio_publicacion = _fecha(fecha_publicacion)
    fecha_explicita = _fecha_explicita(contexto)
    if fecha_explicita:
        return {
            **vacio,
            "Plazo_solicitudes": "Fecha límite explícita",
            "Fecha_fin_plazo": fecha_explicita.isoformat(),
            "Plazo_calculo": "EXPLICITO",
            "Evidencia_plazo": contexto[:500],
        }
    duraciones = [
        coincidencia for coincidencia in _PATRON_DURACION.finditer(contexto)
        if _numero(coincidencia.group("cantidad"))
    ]
    duracion = duraciones[0] if duraciones else None
    if not duracion or not inicio_publicacion:
        return {**vacio, "Evidencia_plazo": contexto[:500]}
    cantidad = _numero(duracion.group("cantidad"))
    if not cantidad:
        return {**vacio, "Evidencia_plazo": contexto[:500]}
    unidad = duracion.group("unidad").lower()
    tipo = (duracion.group("tipo") or "naturales").lower()
    desde_siguiente = bool(re.search(r"siguiente|d[ií]a posterior", contexto, re.IGNORECASE))
    fecha_inicio = inicio_publicacion + timedelta(days=1) if desde_siguiente else inicio_publicacion
    if "mes" in unidad:
        fecha_fin = _sumar_meses(fecha_inicio, cantidad)
        calculo = "CALCULADO_MESES"
        etiqueta = f"{cantidad} {'meses' if cantidad != 1 else 'mes'}"
    elif "hábil" in tipo or "habil" in tipo or "laborable" in tipo:
        fecha_fin = _sumar_dias_habiles(fecha_inicio, cantidad, festivos)
        calculo = (
            "CALCULADO_DIAS_HABILES_CON_FESTIVOS"
            if festivos is not None else "CALCULADO_DIAS_HABILES_SIN_FESTIVOS"
        )
        etiqueta = f"{cantidad} días hábiles"
    else:
        fecha_fin = fecha_inicio + timedelta(days=cantidad - 1)
        calculo = "CALCULADO_DIAS_NATURALES"
        etiqueta = f"{cantidad} días naturales"
    return {
        **vacio,
        "Plazo_solicitudes": etiqueta,
        "Fecha_inicio_plazo": fecha_inicio.isoformat(),
        "Fecha_fin_plazo": fecha_fin.isoformat(),
        "Plazo_calculo": calculo,
        "Evidencia_plazo": contexto[:500],
    }


def enriquecer_con_plazo(filas, texto: str, fecha_publicacion=None, festivos=None):
    """Añade el mismo plazo documental a cada fila de una publicación."""
    plazo = extraer_plazo_presentacion(texto, fecha_publicacion, festivos=festivos)
    return [{**fila, **plazo} for fila in filas]
