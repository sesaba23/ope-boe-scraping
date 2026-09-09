from analizar_sin_coordenadas import _ejemplo, clasificar_registro


def _catalogos():
    municipios = [
        {"codigo_ine": "28079", "nombre": "Madrid", "provincia_maestra": "Madrid", "comunidad_maestra": "Comunidad de Madrid"},
        {"codigo_ine": "03065", "nombre": "Elche/Elx", "provincia_maestra": "Alicante/Alacant", "comunidad_maestra": "Comunitat Valenciana"},
        {"codigo_ine": "01001", "nombre": "Vitoria-Gasteiz", "provincia_maestra": "Araba/Álava", "comunidad_maestra": "País Vasco/Euskadi"},
        {"codigo_ine": "02001", "nombre": "Madrid", "provincia_maestra": "Albacete", "comunidad_maestra": "Castilla-La Mancha"},
    ]
    return {
        "exactos": {"Madrid": [municipios[0], municipios[3]]},
        "casefold": {"madrid": [municipios[0], municipios[3]]},
        "normalizados": {"madrid": [municipios[0], municipios[3]], "elche elx": [municipios[1]], "vitoria gasteiz": [municipios[2]]},
        "aliases": {"elx/elche": [{"municipio": municipios[1]}]},
        "historicos": {"cededo": [{"codigo_ine": "36011", "tipo_alteracion": "FUSION_EXTINCION"}]},
        "islas": {}, "sedes": {"ministerio de prueba": {"municipio_codigo_ine": "28079"}},
    }


def _fila(municipio, provincia="", comunidad=""):
    return {"municipio": municipio, "provincia": provincia, "comunidad_autonoma": comunidad, "administracion": ""}


def test_exacta_y_desambiguacion_provincial():
    c = _catalogos()
    assert clasificar_registro(_fila("Madrid", "Madrid"), c)["categoria"] == "resoluble_con_provincia"
    assert clasificar_registro(_fila("Madrid", "Murcia"), c)["categoria"] == "inconsistencia_territorial"


def test_normalizada_alias_historico_y_sin_texto():
    c = _catalogos()
    assert clasificar_registro(_fila("Vítoria-Gasteiz"), c)["categoria"] == "coincidencia_normalizada_unica"
    assert clasificar_registro(_fila("Elx/Elche", "Alicante/Alacant"), c)["categoria"] == "alias_existente"
    assert clasificar_registro(_fila("Cededo"), c)["categoria"] == "municipio_historico"
    assert clasificar_registro(_fila("", "Madrid"), c)["categoria"] == "sin_texto_municipio"


def test_entidad_multiples_e_irresoluble_no_se_convierten_en_municipio():
    c = _catalogos()
    assert clasificar_registro(_fila("Mancomunidad de prueba"), c)["categoria"] == "texto_administrativo"
    assert clasificar_registro(_fila("Madrid y otras localidades"), c)["categoria"] == "multiples_localizaciones"
    assert clasificar_registro(_fila("Lugar inexistente"), c)["categoria"] == "sin_resolver"


def test_ceuta_melilla_y_coordenadas_historicas_se_conservan_como_diagnostico():
    c = _catalogos()
    ceuta = clasificar_registro(_fila("", "Ceuta"), c)
    assert ceuta["categoria"] == "sin_texto_municipio"
    ejemplo = _ejemplo({"oposicion_id": 7, "municipio": "", "latitud": 35.9, "longitud": -5.3}, ceuta)
    assert (ejemplo["latitud"], ejemplo["longitud"], ejemplo["codigo_ine_candidato"] if "codigo_ine_candidato" in ejemplo else None) == (35.9, -5.3, None)
