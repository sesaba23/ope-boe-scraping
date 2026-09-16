import hashlib
import json
from pathlib import Path

from scripts.audit import auditar_funciones_docentes_compuestas_paso8_25 as audit


def test_universo_y_reconciliacion_paso20():
    result = audit.auditar()
    assert result["universo"] == {"filas": 51, "plazas": 82, "denominaciones": 48}
    rec = result["reconciliacion_paso20"]
    assert rec["solo_paso20"] == rec["solo_paso25"] == []
    assert rec["interseccion"] == rec["ids_paso20"]
    assert len({r["id"] for r in result["registros"]}) == 51


def test_todas_denominaciones_y_clases_consistentes():
    result = audit.auditar()
    assert len(result["denominaciones"]) == 48
    assert sum(result["clasificacion"]["por_clase"].values()) == 51
    assert result["clasificacion"]["plazas"] == 82
    assert all(r["clasificacion_paso25"] in {"A", "B", "C", "D"} for r in result["registros"])
    assert result["clasificacion"]["por_clase"] == {"D": 51}


def test_funciones_cargos_especialidades_laboral_centros_preservados():
    result = audit.auditar()
    assert "responsabilidad_jerarquica" in result["funciones_adicionales"]
    assert "segunda_profesion_o_funcion" in result["funciones_adicionales"]
    assert any(r["especialidades"] for r in result["registros"])
    assert any(r["relacion_laboral"] for r in result["registros"])
    assert any(r["centro_servicio"] for r in result["registros"])
    assert all(r["funcion_adicional"] or r["especialidades"] or r["centro_servicio"] or r["relacion_laboral"] for r in result["registros"])


def test_no_fuzzy_ni_simulacion_insegura():
    result = audit.auditar()
    for simulation in result["simulaciones_a"]:
        assert simulation["usa_fuzzy"] is False
        assert simulation["usa_ids_como_criterio"] is False
        assert simulation["faltantes"] == []
        assert simulation["inesperados"] == []
    assert result["conjuntos_a"] == []


def test_gate_normalizador_y_sqlite_inmutables():
    db = Path("datos/boe.db")
    before = (db.stat().st_size, db.stat().st_mtime_ns, hashlib.sha256(db.read_bytes()).hexdigest())
    result = audit.auditar()
    after = (db.stat().st_size, db.stat().st_mtime_ns, hashlib.sha256(db.read_bytes()).hexdigest())
    assert before == after
    assert result["sqlite_modificada"] is False
    assert result["normalizador_modificado"] is False
    assert result["baseline"]["data_version"] == "62"
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
    path = Path("informes/normalizacion_puestos/fase8_paso25_funciones_docentes_compuestas.json")
    if path.exists():
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["universo"]["filas"] == 51
        assert report["sqlite_modificada"] is False
