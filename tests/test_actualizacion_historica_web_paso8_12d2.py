import actualizacion_boe
import time


def test_dispatcher_separa_historica_y_modernas(monkeypatch):
    llamadas = []
    monkeypatch.setattr(actualizacion_boe, "_actualizar_historico", lambda f, r, p: llamadas.append(("H", f)) or {"ok": True})
    moderno = lambda fs, ruta_bd, on_progress: llamadas.append(("M", fs)) or {"ok": True}
    import plazasboe
    monkeypatch.setattr(plazasboe, "actualizar_fechas", moderno)
    monkeypatch.setattr(plazasboe, "seleccionar_extractor", lambda f: "historico" if "2004" in str(f) else "actual")
    resultado = actualizacion_boe._actualizar_productivo(["2004/01/01", "2026/09/12"], "copia.db", None)
    assert llamadas == [("H", "2004/01/01"), ("M", ["2026/09/12"])]
    assert len(resultado) == 2


def test_dispatcher_moderno_historico_en_orden_inverso(monkeypatch):
    llamadas = []
    monkeypatch.setattr(actualizacion_boe, "_actualizar_historico", lambda f, r, p: llamadas.append(("H", f)) or {})
    import plazasboe
    monkeypatch.setattr(plazasboe, "actualizar_fechas", lambda fs, **k: llamadas.append(("M", fs)) or {})
    monkeypatch.setattr(plazasboe, "seleccionar_extractor", lambda f: "historico" if "2004" in str(f) else "actual")
    actualizacion_boe._actualizar_productivo(["2026/09/12", "2004/01/01"], "copia.db", None)
    assert llamadas == [("M", ["2026/09/12"]), ("H", "2004/01/01")]


def test_historica_no_entra_en_aplicacion_moderno(monkeypatch):
    monkeypatch.setattr(actualizacion_boe, "_actualizar_historico", lambda *a: "historico")
    import plazasboe
    monkeypatch.setattr(plazasboe, "seleccionar_extractor", lambda f: "historico")
    monkeypatch.setattr(plazasboe, "_ejecutar_aplicacion", lambda **k: (_ for _ in ()).throw(AssertionError("no debe llamarse")))
    assert actualizacion_boe._actualizar_productivo(["2004/01/01"], "copia.db", None) == ["historico"]


def test_adaptador_historico_conecta_callbacks_y_persiste(monkeypatch):
    """El adaptador traduce el contrato web al orquestador histórico."""
    import cargar_historico_boe as historico
    import plazasboe

    llamadas = []
    monkeypatch.setattr(historico, "descubrir", lambda inicio, fin: (
        [{"Publicacion_ID": "PUB-1", "titulo": "t"}], ["indice-1"]
    ))
    monkeypatch.setattr(historico, "procesar_publicacion", lambda ficha: (
        "CONVOCATORIA", [{"Puesto": "Auxiliar", "Num_plazas": 1}]
    ))
    monkeypatch.setattr(historico, "aplicar", lambda *args, **kwargs: (
        llamadas.append((args, kwargs)) or {"cambios": True}
    ))

    def orquestador(inicio, fin, *, descubrir, procesar, commit):
        assert (inicio, fin) == ("2004-01-01", "2004-01-01")
        fichas, indices = descubrir()
        assert indices == ["indice-1"]
        dato = procesar(fichas[0])
        assert dato["clasificacion"] == "CONVOCATORIA"
        assert dato["convocatorias"][0]["Puesto"] == "Auxiliar"
        return commit({"resultados": {"PUB-1": dato}})

    monkeypatch.setattr(plazasboe, "ejecutar_flujo_historico", orquestador)
    progreso = []
    resultado = actualizacion_boe._actualizar_historico("2004/01/01", "copia.db", progreso.append)
    assert resultado == {"cambios": True}
    assert llamadas == [(("2004-01-01", "2004-01-01"), {
        "ruta_bd": "copia.db", "directorio": "informes/procesamiento_historico_2004"
    })]
    # La notificación de fecha completada la emite el dispatcher después de
    # retornar este adaptador, garantizando que el commit ya terminó.


def test_error_historico_se_propaga_sin_entrar_en_moderno(monkeypatch):
    """Un fallo del flujo histórico no se oculta ni ejecuta el pipeline moderno."""
    import plazasboe
    monkeypatch.setattr(plazasboe, "seleccionar_extractor", lambda _: "historico")
    monkeypatch.setattr(actualizacion_boe, "_actualizar_historico", lambda *a: (_ for _ in ()).throw(RuntimeError("fallo historico")))
    monkeypatch.setattr(plazasboe, "actualizar_fechas", lambda *a, **k: (_ for _ in ()).throw(AssertionError("moderno inesperado")))
    import pytest
    with pytest.raises(RuntimeError, match="fallo historico"):
        actualizacion_boe._actualizar_productivo(["2004-01-01"], "copia.db", None)


def test_trabajo_expone_fecha_solo_despues_de_persistencia():
    eventos = []
    def actualizar(fechas, ruta, progreso):
        eventos.append("persistiendo")
        progreso({"fase": "fecha_completada", "actual": 1, "total": 1,
                  "fecha": fechas[0], "fecha_completada": True, "resultado": "sin_edicion"})
        eventos.append("persistida")
    gestor = actualizacion_boe.GestorActualizaciones("copia.db", actualizar)
    trabajo, creado = gestor.iniciar(["2026-09-06"])
    assert creado
    for _ in range(50):
        estado = gestor.obtener(trabajo.trabajo_id)
        if estado["estado"] == "completado": break
        time.sleep(0.01)
    assert estado["fechas_completadas"] == [{"fecha": "2026-09-06", "resultado": "sin_edicion"}]
    assert estado["fechas_completadas_count"] == 1


def test_trabajo_con_error_no_notifica_fecha_completada():
    def actualizar(*args): raise RuntimeError("fallo de persistencia")
    gestor = actualizacion_boe.GestorActualizaciones("copia.db", actualizar)
    trabajo, _ = gestor.iniciar(["2026-09-06"])
    for _ in range(50):
        estado = gestor.obtener(trabajo.trabajo_id)
        if estado["estado"] == "error": break
        time.sleep(0.01)
    assert estado["fechas_completadas"] == []
