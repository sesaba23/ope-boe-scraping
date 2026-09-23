import hashlib
import json
import sqlite3
from pathlib import Path

from scripts.audit import auditar_educacion_adultos_paso8_24 as audit


def test_universo_reproducible_y_reconciliado():
    result = audit.auditar()
    u = result["definicion_universo"]
    assert (u["filas"], u["plazas"]) == (14, 17)
    rec = result["reconciliacion_paso20"]
    assert rec["solo_paso20"] == rec["solo_paso24"] == []
    assert rec["interseccion"] == rec["ids_paso20"]
    assert len({r["id"] for r in result["registros"]}) == 14


def test_subfamilias_clases_y_plazas_consistentes():
    result = audit.auditar()
    assert sum(x["filas"] for x in result["subfamilias"].values()) == 14
    assert sum(x["plazas"] for x in result["subfamilias"].values()) == 17
    assert sum(result["clasificacion"]["por_clase"].values()) == 14
    assert result["clasificacion"]["plazas"] == 17
    assert result["conjuntos_a"] == []


def test_maestro_profesor_especialidad_laboral_y_centros():
    result = audit.auditar()
    assert result["analisis_maestro_profesor"] == {"maestro": 14, "profesor": 0, "decision": "no se fusionan automáticamente"}
    assert any(r["especialidad"] == "Informática" for r in result["registros"])
    assert any(r["relacion_laboral_en_texto"] for r in result["registros"])
    assert any(r["centro_en_texto"] for r in result["registros"])
    assert all(r["clasificacion_paso24"] in {"A", "B", "C", "D"} for r in result["registros"])


def test_simulaciones_sin_fuzzy_ni_colisiones():
    result = audit.auditar()
    for simulation in result["simulaciones_a"]:
        assert simulation["usa_fuzzy"] is False
        assert simulation["usa_ids_como_criterio"] is False
        assert simulation["faltantes"] == []
        assert simulation["inesperados"] == []
    assert result["puerta_global_paso19"]["cambios_reales_recalculables"] in (0, 1)


def test_normalizador_y_sqlite_inmutables():
    db = Path("datos/boe.db")
    before = (db.stat().st_size, db.stat().st_mtime_ns, hashlib.sha256(db.read_bytes()).hexdigest())
    result = audit.auditar()
    after = (db.stat().st_size, db.stat().st_mtime_ns, hashlib.sha256(db.read_bytes()).hexdigest())
    assert before == after
    assert result["sqlite_modificada"] is False
    assert result["normalizador_modificado"] is False
    with sqlite3.connect(db) as conexion:
        metadata = dict(conexion.execute("SELECT clave, valor FROM metadata WHERE clave IN ('schema_version', 'data_version')"))
    assert result["baseline"]["schema_version"] == metadata["schema_version"]
    assert result["baseline"]["data_version"] == metadata["data_version"]
    assert result["puerta_global_paso19"] in ({
        "total_discrepancias": 329, "total_plazas_discrepantes": 2215.0,
        "cambios_reales_recalculables": 0,
        "discrepancias_contextuales_no_recalculables": 329,
        "discrepancias_no_clasificables_automaticamente": 0,
    }, {
        "total_discrepancias": 330, "total_plazas_discrepantes": 2216.0,
        "cambios_reales_recalculables": 1,
        "discrepancias_contextuales_no_recalculables": 329,
        "discrepancias_no_clasificables_automaticamente": 0,
    })


def test_informe_si_existe():
    path = Path("informes/normalizacion_puestos/fase8_paso24_educacion_adultos.json")
    if path.exists():
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["definicion_universo"]["filas"] == 14
        assert report["sqlite_modificada"] is False
