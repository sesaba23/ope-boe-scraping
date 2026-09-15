import hashlib
import json
from pathlib import Path

from scripts.audit.reconciliar_actualizacion_cobertura_paso8_13a1 import main


def test_reconciliacion_determinista_y_read_only(tmp_path):
    base = Path("datos/boe.db")
    antes = (hashlib.sha256(base.read_bytes()).hexdigest(), base.stat().st_size, base.stat().st_mtime_ns)
    salida = tmp_path / "reconciliacion.json"
    informe = main(salida)
    despues = (hashlib.sha256(base.read_bytes()).hexdigest(), base.stat().st_size, base.stat().st_mtime_ns)
    assert despues == antes
    # La transición 41→42 se conserva en el backup; la base operativa puede
    # haber avanzado posteriormente. La cadena vigente se audita en 16A-1.
    assert informe["estado_backup"]["data_version"] == "41"
    assert informe["estado_actual"]["data_version"] >= "41"
    assert informe["dry_run_normalizador_cambios"] == 0
    assert informe["cobertura_2026_09_06"]["backup"] == []
    assert informe["cobertura_2026_09_06"]["actual"][0][1] == "sin_edicion"
    serializado = json.loads(salida.read_text(encoding="utf-8"))["diferencias"]
    assert json.dumps(serializado, sort_keys=True) == json.dumps(informe["diferencias"], sort_keys=True, default=list)
