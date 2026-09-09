from analizar_resolucion_texto_boe import analizar_texto, comparar_legacy


def _catalogos():
    madrid = {"codigo_ine": "28079", "nombre": "Madrid", "provincia_maestra": "Madrid", "comunidad_maestra": "Comunidad de Madrid", "latitud": 40.4, "longitud": -3.7}
    ceuta = {"codigo_ine": "51001", "nombre": "Ceuta", "provincia_maestra": None, "comunidad_maestra": "Ceuta", "latitud": 35.9, "longitud": -5.3}
    valencia = {"codigo_ine": "46250", "nombre": "València", "provincia_maestra": "Valencia/València", "comunidad_maestra": "Comunitat Valenciana", "latitud": 39.4, "longitud": -0.4}
    return {"municipios": [madrid, ceuta, valencia], "normalizados": {"madrid": [madrid], "ceuta": [ceuta], "valencia": [valencia]}, "historicos": {"cerdedo": [{"codigo_ine": "36011"}]}, "islas": {}}


def test_municipio_explicito_y_normalizado_es_alta_confianza():
    r = analizar_texto("La plaza tiene destino en Valencia.", _catalogos(), provincia="Valencia/València")
    assert (r["origen_resolucion"], r["confianza"], r["codigo_ine"]) == ("municipio_boe", "ALTA", "46250")


def test_municipio_incidental_y_conflicto_no_son_asignables():
    c = _catalogos()
    assert analizar_texto("Boletín Oficial de la Provincia de Madrid", c)["regla"] == "referencia_administrativa_incidental"
    assert analizar_texto("Destino en Madrid", c, provincia="Valencia/València")["regla"] == "conflicto_municipio_provincia"


def test_ceuta_es_municipio_no_provincia_y_texto_vacio_no_resuelve():
    c = _catalogos()
    assert analizar_texto("Plaza con destino en Ceuta", c)["codigo_ine"] == "51001"
    assert analizar_texto("", c)["origen_resolucion"] is None


def test_provincia_explicita_usa_su_capital_y_homonimo_no_basta():
    c = _catalogos()
    r = analizar_texto("La plaza se prestará en la provincia de Madrid", c)
    assert (r["origen_resolucion"], r["confianza"], r["codigo_ine"]) == ("capital_provincia", "MEDIA", "28079")
    assert analizar_texto("Madrid", c)["origen_resolucion"] is None


def test_historico_y_entidad_insular_no_se_convierten_en_municipio():
    c = _catalogos()
    assert analizar_texto("Destino en Cerdedo", c)["regla"] == "municipio_historico_no_asignable"
    assert analizar_texto("Cabildo Insular de Gran Canaria", c)["regla"] == "referencia_administrativa_incidental"


def test_legacy_solo_verifica_resultados_no_los_crea():
    resultado = {"origen_resolucion": "municipio_boe", "latitud": 40.4, "longitud": -3.7}
    assert comparar_legacy(resultado, 40.4, -3.7) == "coincide"
    assert comparar_legacy(resultado, 41.0, -3.7) == "no_coincide"
    assert comparar_legacy({}, 40.4, -3.7) == "sin_reconstruccion"
    assert comparar_legacy(resultado, None, None) == "sin_coordenadas_legacy"
