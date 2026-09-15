import json
from pathlib import Path

def test_informe_9k2b_conjunto_efectivo():
    p=Path('informes/normalizacion_puestos/fase7_universidad_funcionarial_paso9k2b.json')
    assert p.exists()
    d=json.loads(p.read_text())
    assert d['conjunto_cerrado']['filas'] == 60
    assert d['conjunto_cerrado']['plazas'] == 240
    assert len(d['cuatro_ids']) == 4
    assert d['auditoria_inversa']['falsos_positivos'] == 0
