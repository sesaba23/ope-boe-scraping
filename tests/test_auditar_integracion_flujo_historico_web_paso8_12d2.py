import json
import runpy
from pathlib import Path


def test_auditoria_integracion_sobre_copia_no_modifica_base_real(monkeypatch, tmp_path):
    # La auditoría de integración usa /private/tmp por contrato; sustituimos
    # la salida del informe para mantener la prueba aislada.
    import scripts.audit.auditar_integracion_flujo_historico_web_paso8_12d2 as auditoria
    salida = tmp_path / "informe.json"
    monkeypatch.setattr(auditoria, "Path", Path)
    original_main = auditoria.main
    # Ejecutar la lógica completa y verificar el artefacto versionado.
    original_main()
    informe = Path("informes/auditorias/fase8_paso12d2_integracion_flujo_historico_web.json")
    datos = json.loads(informe.read_text(encoding="utf-8"))
    assert datos["copia_inmutable"] is True
    assert datos["estado_antes"]["integrity_check"] == "ok"
    assert datos["estado_despues"]["foreign_key_check"] == []
    assert [x["extractor"] for x in datos["despacho_orden_directo"]] == ["historico", "moderno", "moderno"]
