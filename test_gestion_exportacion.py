from pathlib import Path
from threading import Event
import time

from gestion_exportacion import GestorExportacionXlsx


def _esperar(gestor, estados={"completada", "error"}):
    limite = time.monotonic() + 2
    while time.monotonic() < limite:
        estado = gestor.obtener()
        if estado and estado["estado"] in estados:
            return estado
        time.sleep(0.01)
    raise AssertionError("El trabajo no terminó")


def test_gestor_reutiliza_trabajo_activo_y_conserva_archivo_hasta_sustituir(tmp_path):
    iniciado, continuar = Event(), Event()

    def exportador(_, salida):
        iniciado.set()
        continuar.wait(1)
        Path(salida).write_bytes(b"xlsx")

    gestor = GestorExportacionXlsx(exportador)
    primero, creado = gestor.iniciar(tmp_path / "base.db")
    assert creado and iniciado.wait(1)
    segundo, creado_otra_vez = gestor.iniciar(tmp_path / "base.db")
    assert not creado_otra_vez and segundo.identificador == primero.identificador
    assert gestor.archivo_preparado() is None

    continuar.set()
    assert _esperar(gestor)["estado"] == "completada"
    anterior = gestor.archivo_preparado()
    assert anterior and anterior.read_bytes() == b"xlsx"

    nuevo, creado_nuevo = gestor.iniciar(tmp_path / "base.db")
    assert creado_nuevo and nuevo.identificador != primero.identificador
    assert not anterior.exists()
    assert _esperar(gestor)["estado"] == "completada"


def test_gestor_limpia_temporal_fallido_y_no_exponen_error(tmp_path):
    def exportador(_, salida):
        Path(salida).write_bytes(b"incompleto")
        raise RuntimeError("detalle interno")

    gestor = GestorExportacionXlsx(exportador)
    gestor.iniciar(tmp_path / "base.db")
    estado = _esperar(gestor)
    assert estado["estado"] == "error"
    assert estado["error"] == "No se pudo preparar la exportación XLSX completa."
    assert gestor.archivo_preparado() is None
