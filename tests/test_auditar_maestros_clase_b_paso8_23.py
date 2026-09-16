import hashlib
import json
from pathlib import Path

from scripts.audit import auditar_maestros_clase_b_paso8_23 as audit


def test_reconstruccion_y_clasificacion_b_exacta():
    data, rows = audit.cargar_b()
    assert len(rows) == 4
    assert sum(r["plazas"] for r in rows) == 11
    assert [r["oposicion_id"] for r in rows] == [11203, 48880, 52935, 97495]
    result = audit.auditar()
    assert [x["clasificacion_paso23"] for x in result["clasificacion_individual"]] == ["B"] * 4
    assert [x["decision"] for x in result["clasificacion_individual"]] == ["MANTENER_B"] * 4
    assert all(x["clasificacion_paso23"] in {"A", "B", "C", "D"} for x in result["clasificacion_individual"])
    assert all(x["decision"] in audit.DECISIONES for x in result["clasificacion_individual"])


def test_no_fuzzy_no_ids_y_casos_c_preservados():
    result = audit.auditar()
    for simulation in result["simulaciones"]:
        assert simulation["usa_fuzzy"] is False
        assert simulation["usa_ids_como_criterio"] is False
        assert all(not row["absorbida_por_simulacion"] for row in simulation["casos_c_no_absorbidos"])
    assert result["ascensos"] == {"filas": 0, "plazas": 0, "ids": [], "decision": "ninguno"}


def test_preserva_especialidad_laboral_centros_y_cuerpos():
    result = audit.auditar()
    assert all(f["especialidad"] == "Educación Infantil" for f in result["casos"])
    assert all(not f["elementos_adicionales"]["laboral"] for f in result["casos"])
    assert all(not f["elementos_adicionales"]["centro"] for f in result["casos"])
    assert all(not f["elementos_adicionales"]["cuerpo"] for f in result["casos"])
    assert result["casos"][-1]["analisis_parentesis"]["clasificacion_elemento"] == "semantico_significativo"


def test_gate_hash_sqlite_y_normalizador_inmutables():
    db = Path("datos/boe.db")
    before = (db.stat().st_size, db.stat().st_mtime_ns, hashlib.sha256(db.read_bytes()).hexdigest())
    normalizer = hashlib.sha256(Path("normalizacion_puestos.py").read_bytes()).hexdigest()
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
    assert result["normalizador_sha256_inicial"] == result["normalizador_sha256_final"] == normalizer


def test_informe_generado_si_existe():
    path = Path("informes/normalizacion_puestos/fase8_paso23_maestros_clase_b.json")
    if path.exists():
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["reconstruccion_paso20"]["plazas"] == 11
        assert report["sqlite_modificada"] is False
