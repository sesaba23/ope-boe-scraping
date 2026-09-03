from datetime import date
import time

import pandas as pd
import pytest

import actualizacion_boe


def _datos_cobertura():
    return {"Cobertura": pd.DataFrame(), "Publicaciones": pd.DataFrame(), "Oposiciones": pd.DataFrame()}


def test_fechas_pendientes_respeta_intervalo_limites_y_cobertura(monkeypatch):
    monkeypatch.setattr(actualizacion_boe.base_datos, "cargar_para_lectura", lambda *a: _datos_cobertura())
    monkeypatch.setattr(actualizacion_boe, "crear_verificador_cobertura_indice", lambda *_: lambda fecha: fecha == "2025/01/02")
    assert actualizacion_boe.fechas_pendientes("x", fecha_desde="2025-01-01", fecha_hasta="2025-01-03") == ["2025-01-01", "2025-01-03"]
    assert actualizacion_boe.fechas_pendientes("x", fecha_desde="2003-12-01", fecha_hasta="2003-12-31") == []
    assert actualizacion_boe.fechas_pendientes("x", fecha_hasta="2025-01-03") == []
    assert actualizacion_boe.fechas_pendientes("x", fecha_desde="2099-01-01", hoy=date(2026, 1, 1)) == []


def test_gestor_progreso_error_y_unico_trabajo():
    llamadas = []
    def actualizar(fechas, ruta, progreso):
        llamadas.append((fechas, ruta)); progreso(fechas[0], "consultado")
    gestor = actualizacion_boe.GestorActualizaciones("prueba.db", actualizador=actualizar)
    trabajo, creado = gestor.iniciar(["2025-01-01"])
    otro, creado_otro = gestor.iniciar(["2025-01-02"])
    assert trabajo.trabajo_id == otro.trabajo_id
    assert creado is True and creado_otro is False
    for _ in range(30):
        estado = gestor.obtener(trabajo.trabajo_id)
        if estado["estado"] == "completado": break
        time.sleep(.01)
    assert estado["estado"] == "completado"
    assert estado["porcentaje"] == 100
    assert llamadas == [(["2025-01-01"], "prueba.db")]


def test_gestor_no_expone_traceback_en_error():
    gestor = actualizacion_boe.GestorActualizaciones("prueba.db", actualizador=lambda *a: (_ for _ in ()).throw(RuntimeError("secreto")))
    trabajo, _ = gestor.iniciar(["2025-01-01"])
    for _ in range(30):
        estado = gestor.obtener(trabajo.trabajo_id)
        if estado["estado"] == "error": break
        time.sleep(.01)
    assert estado["estado"] == "error"
    assert "secreto" not in estado["error"]


def test_estado_de_trabajo_expone_porcentaje_real_del_pipeline():
    trabajo = actualizacion_boe.TrabajoActualizacion("id", ["2025-01-01"])
    trabajo.actual, trabajo.total = 43, 100
    trabajo.mensaje = "Analizando publicaciones…"
    estado = trabajo.serializar()
    assert estado["porcentaje"] == 43
    assert (estado["actual"], estado["total"]) == (43, 100)
    trabajo.actual = 100
    assert trabajo.serializar()["porcentaje"] == 100


def test_gestor_acepta_eventos_de_progreso_del_pipeline():
    def actualizar(fechas, ruta, progreso):
        progreso({"fase": "publicaciones", "actual": 43, "total": 100,
                  "mensaje": "Analizando publicaciones…", "fecha": None})

    gestor = actualizacion_boe.GestorActualizaciones("prueba.db", actualizador=actualizar)
    trabajo, _ = gestor.iniciar(["2025-01-01"])
    for _ in range(30):
        estado = gestor.obtener(trabajo.trabajo_id)
        if estado["estado"] == "completado":
            break
        time.sleep(.01)
    assert estado["estado"] == "completado"
    assert estado["porcentaje"] == 100
    assert estado["mensaje"] == "Actualización completada"


def test_decision_cobertura_y_gestor_procesan_solo_huecos(monkeypatch):
    monkeypatch.setattr(actualizacion_boe.base_datos, "cargar_para_lectura", lambda *a: _datos_cobertura())
    monkeypatch.setattr(actualizacion_boe, "crear_verificador_cobertura_indice", lambda *_: lambda fecha: fecha != "2025/01/02")
    decision = actualizacion_boe.determinar_actualizacion_intervalo(
        "x", fecha_desde="2025-01-01", fecha_hasta="2025-01-03",
    )
    assert decision == {"requiere_actualizacion": True, "fechas_pendientes": ["2025-01-02"]}
    llamadas = []
    gestor = actualizacion_boe.GestorActualizaciones(
        "prueba.db", actualizador=lambda fechas, ruta, progreso: llamadas.append(fechas)
    )
    trabajo, _ = gestor.iniciar(decision["fechas_pendientes"])
    for _ in range(30):
        if gestor.obtener(trabajo.trabajo_id)["estado"] == "completado":
            break
        time.sleep(.01)
    assert llamadas == [["2025-01-02"]]


def test_intervalo_historico_no_reconsulta_version_antigua_y_aísla_incoherencia(monkeypatch):
    cobertura = pd.DataFrame([
        {"Fecha": "2008-01-01", "Estado": "consultado", "Version_extractor": "historico-experimental-2004", "Numero_publicaciones": 1},
        {"Fecha": "2008-01-02", "Estado": "sin_edicion", "Version_extractor": "historico-experimental-2004", "Numero_publicaciones": 0},
        {"Fecha": "2008-01-03", "Estado": "consultado", "Version_extractor": "historico-experimental-2004", "Numero_publicaciones": 0},
    ])
    publicaciones = pd.DataFrame([
        {"Publicacion_ID": "BOE-A-2008-1", "Fecha_BOE": "2008-01-01"},
        {"Publicacion_ID": "BOE-A-2008-2", "Fecha_BOE": "2008-01-03"},
    ])
    monkeypatch.setattr(actualizacion_boe.base_datos, "cargar_para_lectura", lambda *a: {
        "Cobertura": cobertura, "Publicaciones": publicaciones, "Oposiciones": pd.DataFrame(),
    })
    decision = actualizacion_boe.determinar_actualizacion_intervalo(
        "x", fecha_desde="2008-01-01", fecha_hasta="2008-01-03", hoy=date(2026, 1, 1),
    )
    assert decision == {"requiere_actualizacion": True, "fechas_pendientes": ["2008-01-03"]}


@pytest.mark.parametrize("inicio,fin", [
    ("2024-01-01", "2024-12-31"), ("2025-01-01", "2025-12-31"),
    ("2026-08-01", "2026-08-31"), ("2004-01-01", "2026-09-03"),
])
def test_intervalos_cerrados_no_reactivan_incoherencias_verificadas(monkeypatch, inicio, fin):
    monkeypatch.setattr(actualizacion_boe.base_datos, "cargar_para_lectura", lambda *a: _datos_cobertura())
    monkeypatch.setattr(actualizacion_boe, "crear_verificador_cobertura_indice", lambda *_: lambda fecha: True)

    assert actualizacion_boe.determinar_actualizacion_intervalo(
        "x", fecha_desde=inicio, fecha_hasta=fin, hoy=date(2026, 9, 3)
    ) == {"requiere_actualizacion": False, "fechas_pendientes": []}


def test_hueco_nuevo_sigue_detectandose(monkeypatch):
    monkeypatch.setattr(actualizacion_boe.base_datos, "cargar_para_lectura", lambda *a: _datos_cobertura())
    monkeypatch.setattr(actualizacion_boe, "crear_verificador_cobertura_indice", lambda *_: lambda fecha: fecha != "2026/09/02")

    assert actualizacion_boe.fechas_pendientes(
        "x", fecha_desde="2026-09-01", fecha_hasta="2026-09-03", hoy=date(2026, 9, 3)
    ) == ["2026-09-02"]


@pytest.mark.parametrize("fecha", ["2024-05-11", "2025-05-17", "2025-06-28", "2026-08-19"])
def test_incoherencia_verificada_no_vuelve_a_ser_pendiente(monkeypatch, fecha):
    cobertura = pd.DataFrame([{
        "Fecha": fecha, "Estado": "incoherencia_historica_verificada",
        "Version_extractor": "1", "Numero_publicaciones": 0,
    }])
    publicaciones = pd.DataFrame([{
        "Publicacion_ID": "BOE-A-2024-1", "Fecha_BOE": fecha,
    }])
    monkeypatch.setattr(actualizacion_boe.base_datos, "cargar_para_lectura", lambda *a: {
        "Cobertura": cobertura, "Publicaciones": publicaciones, "Oposiciones": pd.DataFrame(),
    })

    assert actualizacion_boe.determinar_actualizacion_intervalo(
        "x", fecha_desde=fecha, fecha_hasta=fecha, hoy=date(2026, 9, 3)
    ) == {"requiere_actualizacion": False, "fechas_pendientes": []}


def test_tiempos_del_trabajo_son_nulos_sin_progreso_y_finalizan_a_cero():
    trabajo = actualizacion_boe.TrabajoActualizacion("id", ["2025-01-01"], estado="procesando")
    trabajo.inicio_monotonic = time.monotonic() - 2
    assert trabajo.serializar()["restante_estimado_segundos"] is None
    trabajo.actual, trabajo.total = 1, 2
    trabajo.inicio_fase_monotonic = time.monotonic() - 2
    assert trabajo.serializar()["restante_estimado_segundos"] is not None
    trabajo.estado, trabajo.actual = "completado", 2
    assert trabajo.serializar()["restante_estimado_segundos"] == 0
