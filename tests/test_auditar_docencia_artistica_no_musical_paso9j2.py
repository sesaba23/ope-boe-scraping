import sqlite3
from pathlib import Path

from scripts.audit.auditar_docencia_artistica_no_musical_paso9j2 import auditar


def test_reconcilia_exactamente_con_9j1_y_detecta_sexta_segura():
    informe = auditar()
    assert informe["reconciliacion_9j1"]["coincide"]
    assert informe["reconciliacion_9j1"]["calculado_desde_sqlite"]["filas"] == 535
    assert informe["reconciliacion_9j1"]["calculado_desde_sqlite"]["plazas"] == 983
    assert informe["discrepancia_sexta_fila_segura"]["id"] == 78433


def test_conjunto_aprobable_cerrado_y_simulacion_idempotente():
    informe = auditar()
    conjunto = informe["conjunto_aprobable_9j2"]
    assert (conjunto["reglas_total"], conjunto["ids_total"], conjunto["filas"], conjunto["plazas"]) == (4, 6, 6, 7)
    assert conjunto["canones"] == 4
    assert informe["dry_run_simulado"]["segunda_pasada"] == 0
    assert informe["dry_run_simulado"]["idempotencia"]


def test_revision_individual_y_falsos_positivos():
    informe = auditar()
    final = informe["clasificacion_final"]
    assert sum(x["filas"] for x in final.values()) == 13
    assert final["APROBAR_SEGURA"]["filas"] == 6
    assert final["REQUIERE_CONTEXTO"]["filas"] == 6
    assert final["EXCLUIR"]["ids"] == [72683]
    assert all(x["auditoria_inversa"]["falsos_positivos"] == 0 for x in informe["conjunto_aprobable_9j2"]["reglas"])


def test_auditoria_no_escribe_sqlite():
    p = Path("datos/boe.db")
    mtime = p.stat().st_mtime_ns
    auditar()
    assert p.stat().st_mtime_ns == mtime
    with sqlite3.connect(p) as con:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
