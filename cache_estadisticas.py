"""Caché LRU, por proceso y por data_version, exclusiva de estadísticas."""

from collections import OrderedDict
from threading import RLock


MAX_ENTRADAS_ESTADISTICAS = 8


def clave_estadisticas(version, *, fecha_inicio, fecha_final, puesto, provincia,
                       ambito, sistema, turno, tipo_personal, comparadores,
                       plazo=None):
    """Usa parámetros efectivos; sólo el filtro multivalor OR ignora el orden."""
    return (
        int(version), fecha_inicio, fecha_final, puesto, provincia, ambito,
        sistema, turno, plazo, tuple(sorted(set(tipo_personal))), tuple(comparadores),
    )


class CacheEstadisticas:
    def __init__(self, max_entradas=MAX_ENTRADAS_ESTADISTICAS):
        if max_entradas < 1:
            raise ValueError("max_entradas debe ser positivo")
        self.max_entradas = max_entradas
        self._entradas = OrderedDict()
        self._version = None
        self._lock = RLock()
        self.hits = 0
        self.misses = 0

    def _actualizar_version(self, version):
        # Un MISS iniciado antes de una actualización no puede reintroducir
        # entradas de una versión antigua tras un MISS más reciente.
        if self._version is None or version > self._version:
            self._entradas.clear()
            self._version = version
        return version == self._version

    def obtener(self, clave):
        with self._lock:
            if not self._actualizar_version(clave[0]) or clave not in self._entradas:
                self.misses += 1
                return None
            self._entradas.move_to_end(clave)
            self.hits += 1
            return self._entradas[clave]

    def guardar(self, clave, json_bytes, tipos_originales):
        with self._lock:
            if not self._actualizar_version(clave[0]):
                return
            self._entradas[clave] = (bytes(json_bytes), tuple(tipos_originales))
            self._entradas.move_to_end(clave)
            if len(self._entradas) > self.max_entradas:
                self._entradas.popitem(last=False)

    def limpiar(self):
        with self._lock:
            self._entradas.clear()
            self._version = None
            self.hits = 0
            self.misses = 0

    def __len__(self):
        with self._lock:
            return len(self._entradas)
