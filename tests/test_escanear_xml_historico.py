import json
from pathlib import Path

import pytest

import escanear_xml_historico as escaner


def _publicaciones():
    return [{"Publicacion_ID": f"BOE-A-2004-{i}", "Fecha_BOE": "2004-01-01", "titulo": "Convocatoria de plazas", "departamento": "Prueba", "url_xml": f"xml:{i}"} for i in range(3)]


class Respuesta:
    def __init__(self, texto, error=False): self.content = texto.encode(); self.error = error
    def raise_for_status(self):
        if self.error: raise RuntimeError("fallo")


def _xml(texto): return f"<documento><metadatos><titulo>Prueba</titulo></metadatos><texto><p>{texto}</p></texto></documento>"


def test_estado_inicial_deduplica_y_contadores():
    estado = escaner.crear_estado(2004, _publicaciones() + [_publicaciones()[0]])
    assert estado["publicaciones_totales"] == 3
    assert estado["publicaciones_pendientes"] == 3


def test_descubrimiento_conserva_familias_de_titulos():
    def api(_):
        return {"estado": "OK", "sumario": {"diario": [{"seccion": {"codigo": "2B", "departamento": {"item": [
            {"identificador": "BOE-A-2004-1", "titulo": "Convocatorias de plazas", "url_xml": "xml:1"},
            {"identificador": "BOE-A-2004-2", "titulo": "Información administrativa", "url_xml": "xml:2"},
        ]}}}]}}
    resultado = escaner.descubrir_publicaciones(2004, api)
    assert [x["Publicacion_ID"] for x in resultado] == ["BOE-A-2004-1"]


def test_limite_reanuda_y_no_repite_procesadas(tmp_path):
    estado = escaner.crear_estado(2004, _publicaciones()); ruta = tmp_path / "estado.json"
    obtener = lambda url, **k: Respuesta(_xml("Sin señales."))
    assert escaner.ejecutar_escaneo(estado, 2, obtener, ruta) == 2
    assert escaner.ejecutar_escaneo(estado, 2, obtener, ruta) == 1
    assert len(estado["resultados"]) == 3
    assert json.loads(ruta.read_text())["publicaciones_pendientes"] == 0


def test_evidencia_debil_sin_senales_y_error():
    p = _publicaciones()[0]
    assert escaner.analizar_publicacion(p, lambda *a, **k: Respuesta(_xml("100 plazas con la siguiente distribución.")))["clasificacion"] == "EVIDENCIA_ESTRUCTURAL"
    assert escaner.analizar_publicacion(p, lambda *a, **k: Respuesta(_xml("Se convocan plazas.")))["clasificacion"] == "SENALES_DEBILES"
    assert escaner.analizar_publicacion(p, lambda *a, **k: Respuesta(_xml("Texto administrativo.")))["clasificacion"] == "SIN_SENALES"
    assert escaner.analizar_publicacion(p, lambda *a, **k: Respuesta("", True))["clasificacion"] == "ERROR"


def test_reintentar_errores_y_escritura_atomica(tmp_path):
    estado = escaner.crear_estado(2004, _publicaciones()[:1]); ruta = tmp_path / "estado.json"
    escaner.ejecutar_escaneo(estado, obtener=lambda *a, **k: Respuesta("", True), ruta=ruta)
    assert escaner.ejecutar_escaneo(estado, obtener=lambda *a, **k: Respuesta(_xml("Texto.")), ruta=ruta, reintentar_errores=True) == 1
    assert estado["resultados"]["BOE-A-2004-0"]["clasificacion"] == "SIN_SENALES"
    assert not list(tmp_path.glob("*.tmp"))


def test_reinicio_protegido_y_carga(tmp_path):
    ruta = tmp_path / "estado_escaneo_2004.json"; ruta.write_text("{}")
    with pytest.raises(ValueError): escaner.cargar_o_crear(2004, tmp_path, reiniciar=True)
    estado, _ = escaner.cargar_o_crear(2004, tmp_path, reiniciar=True, confirmar=True, descubrir=lambda _: _publicaciones())
    assert estado["publicaciones_totales"] == 3


def test_informe_top_30_y_excel_intacto(tmp_path):
    estado = escaner.crear_estado(2004, _publicaciones())
    for p in estado["candidatas"]:
        estado["resultados"][p["Publicacion_ID"]] = escaner.analizar_publicacion(p, lambda *a, **k: Respuesta(_xml("100 plazas con la siguiente distribución.")))
    escaner.actualizar_contadores(estado)
    excel = tmp_path / "BOE-oposiciones.xlsx"; excel.write_bytes(b"intacto")
    rutas = escaner.guardar_informe_final(estado, tmp_path)
    assert len(escaner.seleccionar_prioritarias(estado, 30)) == 3
    assert Path(rutas[0]).exists() and "Candidatos prioritarios" in Path(rutas[1]).read_text()
    assert excel.read_bytes() == b"intacto"


def test_migracion_reutiliza_resultados_y_conserva_fuera_catalogo(tmp_path):
    antiguo = escaner.crear_estado(2004, _publicaciones()[:2])
    antiguo["resultados"] = {
        "BOE-A-2004-0": {"clasificacion": "SIN_SENALES"},
        "BOE-A-2004-fuera": {"clasificacion": "ERROR"},
    }
    escaner.actualizar_contadores(antiguo)
    ruta = escaner.ruta_estado(tmp_path); escaner.escribir_json_atomico(ruta, antiguo)
    nuevas = [_publicaciones()[0], {"Publicacion_ID": "BOE-A-2004-nueva", "Fecha_BOE": "2004-01-02", "titulo": "Plazas", "url_xml": "xml:n"}]
    migrado, backup = escaner.migrar_estado(2004, tmp_path, descubrir=lambda _: nuevas)
    assert backup.exists()
    assert migrado["version_regla_descubrimiento"] == "2"
    assert set(migrado["resultados"]) == {"BOE-A-2004-0"}
    assert "BOE-A-2004-fuera" in migrado["resultados_fuera_catalogo_actual"]
    assert migrado["publicaciones_totales"] == 2
    assert migrado["publicaciones_pendientes"] == 1


def test_estado_obsoleto_no_continua_sin_migrar(tmp_path):
    estado = escaner.crear_estado(2004, _publicaciones())
    estado.pop("version_regla_descubrimiento")
    escaner.escribir_json_atomico(escaner.ruta_estado(tmp_path), estado)
    with pytest.raises(RuntimeError, match="Debe migrarse"):
        escaner.cargar_o_crear(2004, tmp_path)


def test_fallo_de_migracion_conserva_estado_y_backup(tmp_path):
    estado = escaner.crear_estado(2004, _publicaciones())
    ruta = escaner.ruta_estado(tmp_path); escaner.escribir_json_atomico(ruta, estado)
    original = ruta.read_bytes()
    with pytest.raises(RuntimeError):
        escaner.migrar_estado(2004, tmp_path, descubrir=lambda _: (_ for _ in ()).throw(RuntimeError("api")))
    assert ruta.read_bytes() == original
    assert list(tmp_path.glob("estado_escaneo_2004_pre_migracion_*.json"))
