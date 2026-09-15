from pathlib import Path

from scripts.audit.auditar_estabilizacion_genero_paso8_18 import auditar


def test_auditoria_genero_reproducible_y_read_only(tmp_path):
    db = Path("datos/boe.db")
    antes = (db.stat().st_size, db.stat().st_mtime_ns, db.read_bytes()[:32])
    resultado = auditar(db)
    assert resultado["total_cambios"] == len(resultado["ids"]) == 329
    assert len(resultado["ids"]) == len(set(resultado["ids"]))
    assert all(x["denominacion_original"] and x["canon_propuesto"] for x in resultado["inventario"])
    assert sum(g["oposiciones"] for g in resultado["grupos_original_canon"]) == 329
    assert sum(g["plazas"] for g in resultado["grupos_original_canon"]) == resultado["total_plazas"]
    assert resultado["clasificacion"]["D_no_normalizar"] == 329
    assert resultado["aplicacion_real_recomendada"] is False
    despues = (db.stat().st_size, db.stat().st_mtime_ns, db.read_bytes()[:32])
    assert despues == antes


def test_auditoria_explicita_transicion_cero_a_329():
    resultado = auditar()
    assert ("0" in resultado["causa_0_a_329"] or "cero" in resultado["causa_0_a_329"]) and "329" in resultado["causa_0_a_329"]
    assert resultado["comparacion_paso16"]["paso16"] == 0
