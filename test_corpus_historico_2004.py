import copy
import hashlib
import json
from pathlib import Path

import pytest

from corpus_historico_2004 import (CORPUS, ESCANEO, OBLIGATORIAS, SELECCION_INICIAL_10,
                                   aplicar_revision, comparar, construir_corpus,
                                   diagnosticar_puesto, generar_markdown_revision, generar_revision_inicial,
                                   seleccionar_publicaciones, seleccionar_revision_inicial,
                                   validar_corpus)


@pytest.fixture(scope="module")
def escaneo():
    return json.loads(ESCANEO.read_text(encoding="utf-8"))["resultados"]


@pytest.fixture
def corpus():
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def test_seleccion_determinista_de_50_y_obligatorias(escaneo):
    a = seleccionar_publicaciones(escaneo); b = seleccionar_publicaciones(list(reversed(escaneo)))
    assert len(a) == 50
    assert [x["Publicacion_ID"] for x in a] == [x["Publicacion_ID"] for x in b]
    assert OBLIGATORIAS <= {x["Publicacion_ID"] for x in a}


def test_diversidad_temporal_y_tipos(corpus):
    publicaciones = corpus["publicaciones"]
    assert len({p["Fecha_boe"][5:7] for p in publicaciones}) == 12
    tipos = {p["clasificacion_documento"] for p in publicaciones}
    assert len(tipos) >= 5
    assert {"SUBCUPOS", "TOTAL_DESGLOSE", "ESTRUCTURAL_TABLA", "SIN_CONVOCATORIA"} <= tipos
    assert len({p["departamento"] for p in publicaciones}) >= 4


def test_campos_opcionales_y_estado_del_corpus(corpus):
    validar_corpus(corpus)
    assert sum(p["estado_revision"] == "REVISADO" for p in corpus["publicaciones"]) == 10
    assert all(not p["convocatorias_esperadas"] for p in corpus["publicaciones"] if p["estado_revision"] == "PENDIENTE")
    assert any(any(c.get("Turno") is None for c in p["propuesta_extractor"]) for p in corpus["publicaciones"] if p["propuesta_extractor"])


def _corpus_revisado(esperadas):
    return {"publicaciones": [{"Publicacion_ID": "X", "estado_revision": "REVISADO",
             "convocatorias_esperadas": esperadas}]}


def _fila(puesto="Auxiliar", plazas=2, **kw):
    return {"Puesto": puesto, "Num_plazas": plazas, **kw}


def test_comparacion_correcta_y_campos_opcionales_diferentes():
    c = _corpus_revisado([_fila(Turno="Libre", tipo_cantidad="CONVOCATORIA")])
    r = comparar(c, {"X": [_fila(Turno="Promoción interna")]})
    assert (r["verdaderos_positivos"], r["falsos_positivos"], r["falsos_negativos"]) == (1, 0, 0)
    assert r["detalle"][0]["diferencias_campos_opcionales"] == 1


def test_falso_positivo_falso_negativo_y_doble_conteo():
    c = _corpus_revisado([_fila()])
    r = comparar(c, {"X": [_fila(), _fila(), _fila("Técnico", 1)]})
    assert r["verdaderos_positivos"] == 1 and r["falsos_positivos"] == 2
    assert r["posibles_dobles_conteos"] >= 1
    r = comparar(c, {"X": []})
    assert r["falsos_negativos"] == 1


def test_total_y_subcupo_no_son_convocatorias():
    c = _corpus_revisado([_fila(tipo_cantidad="TOTAL"), _fila("Reserva", 1, tipo_cantidad="SUBCUPO")])
    r = comparar(c, {"X": []})
    assert r["convocatorias_esperadas"] == 0 and r["falsos_negativos"] == 0


def test_pendiente_con_etiquetas_es_invalido(corpus):
    malo = copy.deepcopy(corpus)
    pendiente = next(p for p in malo["publicaciones"] if p["estado_revision"] == "PENDIENTE")
    pendiente["convocatorias_esperadas"] = [_fila(tipo_cantidad="CONVOCATORIA")]
    with pytest.raises(ValueError, match="PENDIENTE"):
        validar_corpus(malo)


def test_no_modificacion_excel_al_construir(escaneo):
    excel_path = Path("BOE-oposiciones.xlsx")
    antes = hashlib.sha256(excel_path.read_bytes()).hexdigest()
    construir_corpus(escaneo)
    assert hashlib.sha256(excel_path.read_bytes()).hexdigest() == antes


def test_seleccion_inicial_exacta_determinista_y_composicion(corpus):
    a, b = seleccionar_revision_inicial(corpus), seleccionar_revision_inicial(corpus)
    assert [p["Publicacion_ID"] for p in a["publicaciones"]] == [x[0] for x in SELECCION_INICIAL_10]
    assert a == b and len(a["publicaciones"]) == 10
    assert dict(__import__("collections").Counter(p["categoria_seleccion"] for p in a["publicaciones"])) == {
        "SENCILLA_UNICA": 3, "SIN_CONVOCATORIA": 2, "TABLA": 2,
        "TOTAL_DESGLOSE": 1, "SUBCUPO": 1, "MULTICONVOCATORIA": 1,
    }


def test_revision_json_markdown_y_las_40_restantes(corpus, tmp_path):
    antes = copy.deepcopy(corpus)
    revision = generar_revision_inicial(CORPUS, tmp_path / "revision.json", tmp_path / "revision.md")
    texto = (tmp_path / "revision.md").read_text(encoding="utf-8")
    assert len(revision["publicaciones"]) == 10
    assert "### Etiqueta manual" in texto and "- incluida_en:" in texto
    assert all(p["estado_revision"] == "PENDIENTE" and not p["convocatorias_esperadas"] for p in revision["publicaciones"])
    assert corpus == antes


def _copiar_para_aplicar(corpus, tmp_path):
    destino = tmp_path / "corpus.json"
    destino.write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8")
    revision = seleccionar_revision_inicial(corpus)
    entrada = tmp_path / "revision.json"
    entrada.write_text(json.dumps(revision, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino, entrada, revision


def test_aplicar_revision_valida_backup_atomica_y_exclusiva(corpus, tmp_path, monkeypatch):
    destino, entrada, revision = _copiar_para_aplicar(corpus, tmp_path)
    revision["publicaciones"][0].update({"clasificacion_documento_revision": "CONVOCATORIA",
                                         "convocatorias_esperadas": [_fila("Ordenanza", 1, tipo_cantidad="CONVOCATORIA")]})
    entrada.write_text(json.dumps(revision, ensure_ascii=False), encoding="utf-8")
    reemplazos = []
    import corpus_historico_2004
    original = corpus_historico_2004.os.replace
    monkeypatch.setattr(corpus_historico_2004.os, "replace", lambda a, b: (reemplazos.append((a, b)), original(a, b))[1])
    backup = aplicar_revision(entrada, destino)
    resultado = json.loads(destino.read_text(encoding="utf-8"))["publicaciones"]
    assert backup.exists() and reemplazos
    por_id = {p["Publicacion_ID"]: p for p in resultado}
    assert por_id[revision["publicaciones"][0]["Publicacion_ID"]]["estado_revision"] == "REVISADO"
    seleccionadas = {x[0] for x in SELECCION_INICIAL_10}
    assert all(p["estado_revision"] == "PENDIENTE" for p in resultado if p["Publicacion_ID"] not in seleccionadas)
    originales = {p["Publicacion_ID"]: p for p in corpus["publicaciones"]}
    assert all(p == originales[p["Publicacion_ID"]] for p in resultado if p["Publicacion_ID"] not in seleccionadas)


@pytest.mark.parametrize("convocatoria", [
    {"Puesto": "Auxiliar", "tipo_cantidad": "CONVOCATORIA"},
    {"Num_plazas": 1, "tipo_cantidad": "CONVOCATORIA"},
    {"Puesto": "Auxiliar", "Num_plazas": 0, "tipo_cantidad": "CONVOCATORIA"},
    {"Puesto": "Auxiliar", "Num_plazas": 1, "tipo_cantidad": "OTRO"},
])
def test_revision_invalida_no_escribe(corpus, tmp_path, convocatoria):
    destino, entrada, revision = _copiar_para_aplicar(corpus, tmp_path)
    antes = destino.read_bytes()
    revision["publicaciones"][0].update({"clasificacion_documento_revision": "CONVOCATORIA", "convocatorias_esperadas": [convocatoria]})
    entrada.write_text(json.dumps(revision), encoding="utf-8")
    with pytest.raises(ValueError):
        aplicar_revision(entrada, destino)
    assert destino.read_bytes() == antes


def test_no_convocatoria_sin_filas_es_revision_valida(corpus, tmp_path):
    destino, entrada, revision = _copiar_para_aplicar(corpus, tmp_path)
    revision["publicaciones"][3]["clasificacion_documento_revision"] = "NO_CONVOCATORIA"
    entrada.write_text(json.dumps(revision), encoding="utf-8")
    aplicar_revision(entrada, destino)
    actual = json.loads(destino.read_text(encoding="utf-8"))["publicaciones"]
    publicada = next(p for p in actual if p["Publicacion_ID"] == revision["publicaciones"][3]["Publicacion_ID"])
    assert publicada["estado_revision"] == "REVISADO" and publicada["convocatorias_esperadas"] == []


def test_diagnostico_puesto_se_limita_a_revisadas_y_no_muta(corpus):
    antes = copy.deepcopy(corpus)
    diagnostico = diagnosticar_puesto(corpus)
    assert len(diagnostico["publicaciones"]) == 10
    assert diagnostico["resultado_antes"]["verdaderos_positivos"] < diagnostico["resultado_despues"]["verdaderos_positivos"]
    assert "BOE-A-2004-6309" in diagnostico["casos_no_resueltos"]
    assert corpus == antes
