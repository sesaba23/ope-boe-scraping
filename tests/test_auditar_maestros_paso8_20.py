import json
import sqlite3
from pathlib import Path

import pytest

from scripts.audit import auditar_maestros_paso8_20 as audit


def fila(oid, puesto, actual=None, plazas=1, **contexto):
    return {"oposicion_id": oid, "puesto": puesto,
            "puesto_normalizado": audit.textual.normalizar_puesto(puesto) if actual is None else actual,
            "num_plazas": plazas, "administracion": "Ayuntamiento de Ejemplo", "ambito": "LOCAL",
            "tipo_entidad": "MUNICIPAL", "escala": "--", "subescala": "--", "clase": "--",
            "sistema": "Oposición", "municipio": "Ejemplo", "provincia": "Madrid",
            "fecha_boe": "2025-01-01", "publicacion_id": f"PUBLICACION-{oid}", "titulo_original": None,
            **contexto}


@pytest.fixture
def filas():
    return [
        fila(1, "Maestro/a de Educación Infantil", plazas=2),
        fila(2, "Maestro o Maestra de Educación Infantil", plazas=4),
        fila(3, "Maestro-a de Educación Infantil", plazas=1),
        fila(4, "Maestro/maestra en educación infantil", plazas=1),
        fila(5, "funcionarios docentes para el Cuerpo de Maestros", plazas=20, ambito="AUTONOMICO"),
        fila(6, "Maestro de Obras", plazas=3),
        fila(7, "Maestras de Educación Infantil", plazas=6),
        fila(8, "Maestro/a (Educación Infantil)"),
        fila(9, "Maestro/a Director/a Escuela Infantil"),
        fila(10, "Maestro/a de Educación Infantil de la plantilla de personal laboral fijo"),
        fila(11, "Maestro/a"),
        fila(12, "Maestro/a de Educación Física"),
        fila(13, "Educador Infantil"),
        fila(14, "Técnico de Educación Infantil"),
        fila(15, "Contramaestre"),
        fila(16, "Docente", clase="Cuerpo de Maestras"),
        fila(17, "Profesor", titulo_original="Convocatoria para Maestros"),
        fila(18, "Docente (código 597)"),
        fila(19, "Policía", actual="Policía Local", plazas=7),
    ]


def test_universo_reproducible_y_particiones_aditivas(filas):
    d = audit.reconstruir(filas)
    assert d == audit.reconstruir(list(reversed(filas)))
    ids = d["universo"]["ids"]
    assert ids == list(range(1, 13)) + [16, 17, 18]
    assert d["reconstruccion_b"]["ids"] == ids
    assert len(ids) == len(set(ids))
    for grupos in (d["microfamilias"], d["estados"]):
        assert sum(g["filas"] for g in grupos.values()) == d["universo"]["filas"]
        assert sum(g["plazas"] for g in grupos.values()) == d["universo"]["plazas"]
        assert sorted(i for g in grupos.values() for i in g["ids"]) == ids
    for medida in ("filas", "plazas"):
        assert sum(d["clasificacion_seguridad"][k][medida] for k in "ABCD") == d["candidatos_clasificados"][medida]
    assert sum(d["grupos_por_seguridad"].values()) == len(d["grupos_candidatos"])


def test_rechaza_duplicados(filas):
    with pytest.raises(ValueError, match="duplicados"):
        audit.reconstruir(filas + [filas[0]])


def test_infantil_previo_no_es_pendiente(filas):
    d = audit.reconstruir(filas)
    r = d["registros"][0]
    assert r["puesto_normalizado"] == "Maestro de Educación Infantil"
    assert r["estado"] == "ya_normalizado_regla_previa"
    assert r["seguridad"] is None and r["canon_propuesto"] is None
    assert r["oposicion_id"] not in d["pendientes"]["ids"]


@pytest.mark.parametrize("puesto", ["Educador Infantil", "Técnico de Educación Infantil",
    "Técnico Superior de Educación Infantil", "Técnico Especialista en Educación Infantil",
    "Auxiliar de Educación Infantil", "Personal de Escuela Infantil", "Contramaestre", "Maestría", "Maetro"])
def test_no_incluye_otras_profesiones_ni_similitud(puesto):
    assert audit.fuentes_candidato(fila(8000, puesto)) == []
    assert audit.candidato_por_tokens(fila(8000, puesto)) is False


@pytest.mark.parametrize("puesto", ["Maestro de Educación Física", "Maestro Audición y Lenguaje",
    "Maestro de Pedagogía Terapéutica", "Maestro/a de Música para la Educación Infantil y Especial",
    "Maestro/a de Primaria", "Maestro/a de Inglés", "Maestro/a de Escuela Infantil",
    "Maestro/a de Educación Infantil de la plantilla de personal laboral fijo"])
def test_preserva_denominacion_y_no_propone_canon_generico(puesto):
    r = audit.ficha(fila(31, puesto))
    assert r["descriptor_original_integro"] == puesto
    assert r["canon_propuesto"] is None
    assert r["puesto_normalizado"] == audit.textual.normalizar_puesto(puesto)


def test_cuerpo_local_y_generico_se_auditan_separadamente():
    local = audit.ficha(fila(1, "Maestro"))
    assert local["microfamilia"] == "maestro_generico"
    assert local["acredita_cuerpo_docente"] is False
    assert local["canon_propuesto"] is None
    cuerpo = audit.ficha(fila(2, "Cuerpo de Maestros", ambito="AUTONOMICO"))
    assert cuerpo["microfamilia"] == "cuerpo_docente_explicito"
    assert cuerpo["acredita_cuerpo_docente"] is True
    inconsistente = audit.ficha(fila(3, "funcionarios docentes para el Cuerpo de Maestros"))
    assert inconsistente["seguridad"] == "C" and inconsistente["canon_propuesto"] is None


def test_propuestas_cerradas_no_se_aplican_ni_usan_ids(filas):
    d = audit.reconstruir(filas)
    assert len(d["conjuntos_cerrados_seguros"]) == 1
    assert d["clasificacion_seguridad"]["A"]["ids"] == [5]
    for r in d["registros"]:
        if r["seguridad"] == "A":
            assert r["canon_propuesto"] in {"Maestro de Educación Infantil", "Maestros"}
    desplazados = [dict(r, oposicion_id=r["oposicion_id"] + 90000) for r in filas]
    assert audit.reconstruir(desplazados)["clasificacion_seguridad"]["A"]["ids"] == [90005]
    con_sufijo = audit.ficha(fila(50, "Maestro o Maestra de Educación Infantil de la plantilla de personal laboral fijo"))
    assert con_sufijo["seguridad"] != "A" and con_sufijo["canon_propuesto"] is None


def test_no_inventa_especialidades_ausentes():
    d = audit.reconstruir([fila(1, "Maestro de Educación Física")])
    assert set(d["especialidades"]) == {"Educación Física"}


def test_canon_musical_reproducible_no_certifica_un_oficio():
    r = audit.ficha(fila(1, "Maestro/a de Fotocomposición"))
    assert r["puesto_normalizado"] == "Maestro/a de Fotocomposición"
    assert r["textual"] == "Maestro/a de Fotocomposición"
    assert r["alerta_canon_previo_ajeno_a_profesion"] is False
    assert r["canon_validado_pipeline_previo"] is False
    assert r["estado"] == "fuera_de_familia" and r["seguridad"] == "D"
    assert r["canon_propuesto"] is None


def crear_bd(ruta, filas):
    con = sqlite3.connect(ruta)
    con.executescript("""
        CREATE TABLE metadata(clave TEXT PRIMARY KEY, valor TEXT);
        INSERT INTO metadata VALUES ('schema_version','6'),('data_version','47');
        CREATE TABLE publicaciones(publicacion_id TEXT PRIMARY KEY, titulo_original TEXT);
        CREATE TABLE oposiciones(oposicion_id INTEGER PRIMARY KEY, puesto TEXT, puesto_normalizado TEXT,
            num_plazas REAL, administracion TEXT, ambito TEXT, tipo_entidad TEXT, escala TEXT,
            subescala TEXT, clase TEXT, sistema TEXT, municipio TEXT, provincia TEXT,
            fecha_boe TEXT, publicacion_id TEXT REFERENCES publicaciones(publicacion_id));
        CREATE TABLE busquedas(codigo TEXT);
        CREATE TABLE cobertura(fecha TEXT);
    """)
    campos = [r[1] for r in con.execute("PRAGMA table_info(oposiciones)")]
    for r in filas:
        con.execute("INSERT INTO publicaciones VALUES (?,?)", (r["publicacion_id"], r["titulo_original"]))
        con.execute(f"INSERT INTO oposiciones VALUES ({','.join('?' for _ in campos)})", [r[k] for k in campos])
    con.commit()
    con.close()


def test_read_only_normalizador_y_gate_real_paso19(tmp_path, filas, monkeypatch):
    db = tmp_path / "fixture.db"
    crear_bd(db, filas)
    antes = audit.paso19._estado(db)
    codigo = Path(audit.textual.__file__).read_bytes()
    llamadas = []
    original = audit.paso19.auditar

    def observar(ruta):
        llamadas.append(ruta)
        return original(ruta)

    monkeypatch.setattr(audit.paso19, "auditar", observar)
    d = audit.auditar(db, historicos=tmp_path)
    assert llamadas == [db, db]
    gate = d["gate_global_paso19"]
    assert gate["sin_diferencias"] is True
    assert gate["despues"]["total_discrepancias"] == 1
    assert gate["despues"]["discrepancias_contextuales_no_recalculables"]["ids"] == [19]
    assert gate["despues"]["cambios_reales_recalculables"]["filas"] == 0
    assert gate["despues"]["discrepancias_no_clasificables_automaticamente"]["filas"] == 0
    assert audit.paso19._estado(db) == antes == d["sqlite_final"] == d["baseline_sqlite"]
    assert Path(audit.textual.__file__).read_bytes() == codigo
    assert d["normalizacion_puestos_modificada"] is False and d["sqlite_modificada"] is False


def test_gate_precheck_incorrecto_detiene_sin_restaurar(tmp_path, filas):
    db = tmp_path / "fixture.db"
    crear_bd(db, filas)
    datos = db.read_bytes()
    with pytest.raises(RuntimeError, match="Gate SQLite"):
        audit.auditar(db, precheck={"sqlite": {}})
    assert db.read_bytes() == datos


def test_historico_reconstruye_datos_actuales_sin_ids_para_candidatos(tmp_path):
    r = fila(70, "Maestra de Educación Infantil", plazas=3)
    (tmp_path / "fase8_paso7_educacion_infantil.json").write_text(json.dumps({
        "conjunto_seguro": {"mapa_id_canon": {"70": "Maestro de Educación Infantil", "99": "Maestro de Educación Infantil"},
                            "filas": 2, "plazas": 10}}))
    d = audit.reconciliar_historicos([r], tmp_path)["fase8_7"]
    assert d["historico"]["filas"] == 2
    assert d["actual"]["filas"] == 1 and d["actual"]["plazas"] == 3
    assert d["ids_ausentes"] == [99]
    assert d["ids_con_canon_distinto"] == []
