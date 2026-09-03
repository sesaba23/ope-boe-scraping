"""Planificación y ejecución en memoria de actualizaciones BOE para el portal."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import logging
from threading import Lock, Thread
import time
from uuid import uuid4

import base_datos
from cobertura import crear_verificador_cobertura_indice


FECHA_MINIMA_AUTOMATICA = date(2004, 1, 1)
LOG = logging.getLogger(__name__)


def _fecha(valor):
    if not valor:
        return None
    return datetime.strptime(str(valor), "%Y-%m-%d").date()


def _dias(inicio, fin):
    actual = inicio
    while actual <= fin:
        yield actual
        actual += timedelta(days=1)


def determinar_actualizacion_intervalo(ruta_bd, *, fecha_desde=None, fecha_hasta=None, hoy=None):
    """Fechas no cubiertas según la semántica productiva de ``cobertura``.

    Sin ``desde`` no se inicia una actualización masiva: la búsqueda se limita
    a SQLite. Las fechas futuras se recortan a hoy y las anteriores a 2004 no
    provocan scraping automático.
    """
    inicio, fin = _fecha(fecha_desde), _fecha(fecha_hasta)
    hoy = hoy or date.today()
    if inicio is None:
        return {"requiere_actualizacion": False, "fechas_pendientes": []}
    fin = min(fin or hoy, hoy)
    inicio = max(inicio, FECHA_MINIMA_AUTOMATICA)
    if inicio > fin:
        return {"requiere_actualizacion": False, "fechas_pendientes": []}
    datos = base_datos.cargar_para_lectura(ruta_bd, inicio.isoformat(), fin.isoformat())
    cobertura_reutilizable = crear_verificador_cobertura_indice(
        datos["Cobertura"], datos["Publicaciones"]
    )
    pendientes = []
    for dia in _dias(inicio, fin):
        texto = dia.strftime("%Y/%m/%d")
        if not cobertura_reutilizable(texto):
            pendientes.append(dia.isoformat())
    return {
        "requiere_actualizacion": bool(pendientes),
        "fechas_pendientes": pendientes,
    }


def fechas_pendientes(ruta_bd, **kwargs):
    """Compatibilidad para consumidores previos de la lista de pendientes."""
    return determinar_actualizacion_intervalo(ruta_bd, **kwargs)["fechas_pendientes"]


@dataclass
class TrabajoActualizacion:
    trabajo_id: str
    fechas: list
    estado: str = "pendiente"
    completadas: int = 0
    fecha_actual: str | None = None
    mensaje: str = "Comprobando cobertura del BOE…"
    error: str | None = None
    actual: int = 0
    total: int = 0
    fase: str | None = None
    inicio_monotonic: float | None = None
    inicio_fase_monotonic: float | None = None

    def serializar(self):
        total = self.total or len(self.fechas)
        fechas_totales = len(self.fechas)
        ahora = time.monotonic()
        transcurrido = (
            max(0, round(ahora - self.inicio_monotonic))
            if self.inicio_monotonic is not None else 0
        )
        restante = None
        if self.estado == "completado":
            restante = 0
        elif self.inicio_fase_monotonic is not None and self.actual > 0 and self.total > self.actual:
            tiempo_fase = ahora - self.inicio_fase_monotonic
            if tiempo_fase >= 1:
                restante = max(0, round(tiempo_fase * (self.total - self.actual) / self.actual))
        return {"id": self.trabajo_id, "estado": self.estado, "fecha_actual": self.fecha_actual,
                "fechas_totales": fechas_totales, "fechas_completadas": self.completadas,
                "actual": self.actual, "total": total,
                "porcentaje": round(100 * self.actual / total) if total else 100,
                "mensaje": self.mensaje, "error": self.error, "fase": self.fase,
                "transcurrido_segundos": transcurrido,
                "restante_estimado_segundos": restante}


class GestorActualizaciones:
    """Un único trabajo de escritura por proceso Flask.

    El estado no sobrevive un reinicio del servidor; SQLite sí conserva la
    transacción y cobertura que haya terminado el pipeline productivo.
    """
    def __init__(self, ruta_bd, actualizador=None):
        self.ruta_bd = ruta_bd
        self.actualizador = actualizador or _actualizar_productivo
        self._lock = Lock()
        self._trabajo = None

    def iniciar(self, fechas):
        with self._lock:
            if self._trabajo and self._trabajo.estado in {"pendiente", "procesando"}:
                return self._trabajo, False
            trabajo = TrabajoActualizacion(str(uuid4()), list(fechas))
            self._trabajo = trabajo
            Thread(target=self._ejecutar, args=(trabajo,), daemon=True).start()
            return trabajo, True

    def obtener(self, trabajo_id):
        with self._lock:
            if not self._trabajo or self._trabajo.trabajo_id != trabajo_id:
                return None
            return self._trabajo.serializar()

    def _ejecutar(self, trabajo):
        def progreso(evento, estado=None):
            # El pipeline productivo emite diccionarios. El formato anterior de
            # dos argumentos se conserva para actualizadores de pruebas.
            if not isinstance(evento, dict):
                evento = {
                    "fecha": evento, "mensaje": "Actualizando datos del BOE…",
                    "actual": trabajo.completadas + 1, "total": len(trabajo.fechas),
                }
            with self._lock:
                fase = evento.get("fase")
                if fase != trabajo.fase:
                    trabajo.fase = fase
                    trabajo.inicio_fase_monotonic = time.monotonic()
                trabajo.fecha_actual = evento.get("fecha")
                trabajo.actual = max(0, int(evento.get("actual", 0)))
                trabajo.total = max(0, int(evento.get("total", 0)))
                trabajo.completadas = min(len(trabajo.fechas), trabajo.actual)
                trabajo.mensaje = evento.get("mensaje") or "Actualizando datos del BOE…"
        try:
            with self._lock:
                trabajo.estado = "procesando"
                trabajo.mensaje = "Actualizando datos del BOE…"
                trabajo.inicio_monotonic = time.monotonic()
            # La decisión de cobertura ya ha seleccionado exactamente los huecos.
            self.actualizador(trabajo.fechas, self.ruta_bd, progreso)
            with self._lock:
                trabajo.completadas = len(trabajo.fechas)
                trabajo.actual = trabajo.total or len(trabajo.fechas)
                trabajo.estado = "completado"
                trabajo.mensaje = "Actualización completada"
        except Exception:
            LOG.exception("Falló la actualización BOE del trabajo %s (fase=%s, fecha=%s)",
                          trabajo.trabajo_id, trabajo.fase, trabajo.fecha_actual)
            with self._lock:
                trabajo.estado = "error"
                trabajo.error = "No se pudo completar la actualización del BOE. Puedes intentarlo de nuevo."
                trabajo.mensaje = trabajo.error


def _actualizar_productivo(fechas, ruta_bd, progreso):
    from plazasboe import actualizar_fechas
    return actualizar_fechas(fechas, ruta_bd=ruta_bd, on_progress=progreso)
