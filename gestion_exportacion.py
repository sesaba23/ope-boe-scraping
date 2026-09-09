"""Trabajo en segundo plano, por proceso, para el XLSX completo descargable."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
import shutil
import tempfile
from threading import Lock, Thread
import time
from uuid import uuid4

from servicio_exportacion import exportar_base_xlsx


LOG = logging.getLogger(__name__)


@dataclass
class TrabajoExportacionXlsx:
    identificador: str
    estado: str = "preparando"
    error: str | None = None
    inicio: float = 0.0
    finalizado: float | None = None
    ruta: Path | None = None
    directorio: Path | None = None

    def serializar(self):
        fin = self.finalizado if self.finalizado is not None else time.monotonic()
        return {
            "id": self.identificador,
            "estado": self.estado,
            "error": self.error,
            "transcurrido_segundos": round(fin - self.inicio),
            "terminal": self.estado in {"completada", "error"},
        }


class GestorExportacionXlsx:
    """Mantiene como máximo un XLSX completo activo por proceso Flask.

    El archivo terminado permanece disponible hasta que una nueva exportación
    lo sustituye. No existe persistencia del estado tras reiniciar el proceso.
    """

    def __init__(self, exportador=exportar_base_xlsx):
        self._exportador = exportador
        self._lock = Lock()
        self._trabajo = None

    def iniciar(self, ruta_bd):
        with self._lock:
            if self._trabajo and self._trabajo.estado == "preparando":
                return self._trabajo, False
            self._limpiar_anterior_bloqueado()
            directorio = Path(tempfile.mkdtemp(prefix="boe-exportacion-xlsx-"))
            trabajo = TrabajoExportacionXlsx(
                identificador=str(uuid4()), inicio=time.monotonic(), directorio=directorio,
                ruta=directorio / "boe_base_completa.xlsx",
            )
            self._trabajo = trabajo
            Thread(target=self._ejecutar, args=(trabajo, Path(ruta_bd)), daemon=True).start()
            return trabajo, True

    def obtener(self):
        with self._lock:
            return self._trabajo.serializar() if self._trabajo else None

    def archivo_preparado(self):
        with self._lock:
            if (
                self._trabajo
                and self._trabajo.estado == "completada"
                and self._trabajo.ruta
                and self._trabajo.ruta.is_file()
            ):
                return self._trabajo.ruta
            return None

    def _limpiar_anterior_bloqueado(self):
        if self._trabajo and self._trabajo.directorio:
            shutil.rmtree(self._trabajo.directorio, ignore_errors=True)
        self._trabajo = None

    def _ejecutar(self, trabajo, ruta_bd):
        try:
            self._exportador(ruta_bd, trabajo.ruta)
            if not trabajo.ruta.is_file():
                raise RuntimeError("El archivo de exportación no se generó.")
            with self._lock:
                trabajo.estado = "completada"
        except Exception:
            LOG.exception("Falló la exportación XLSX completa del trabajo %s", trabajo.identificador)
            if trabajo.directorio:
                shutil.rmtree(trabajo.directorio, ignore_errors=True)
            with self._lock:
                trabajo.ruta = None
                trabajo.estado = "error"
                trabajo.error = "No se pudo preparar la exportación XLSX completa."
        finally:
            with self._lock:
                trabajo.finalizado = time.monotonic()
