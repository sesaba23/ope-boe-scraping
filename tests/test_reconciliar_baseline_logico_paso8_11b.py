from scripts.audit.reconciliar_baseline_logico_paso8_11b import BASELINE, ACTUAL, _meta, _op_rows


def test_reconciliacion_data39_data40_es_reproducible():
    assert _meta(BASELINE)["data_version"] == "39"
    # El baseline operativo avanzó posteriormente a data 42 por cobertura;
    # la propiedad que se audita aquí sigue siendo la incorporación de IDs.
    assert int(_meta(ACTUAL)["data_version"]) >= 40
    old, new = _op_rows(BASELINE), _op_rows(ACTUAL)
    assert set(old) - set(new) == set()
    assert set(new) - set(old)
