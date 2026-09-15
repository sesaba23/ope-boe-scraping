import sqlite3
from pathlib import Path

from scripts.audit.auditar_universo_docente_pendiente_paso9i import auditar, clasificar_fila


def _fila(puesto, normalizado=None, ambito="ESTATAL"):
    return {"puesto": puesto, "puesto_normalizado": normalizado, "ambito": ambito}


def test_categorias_son_excluyentes_y_protegen_falsos_positivos():
    assert clasificar_fila(_fila("Maestro de obras"))[0] == "FALSO_POSITIVO"
    assert clasificar_fila(_fila("Músico de banda"))[0] == "FALSO_POSITIVO"
    assert clasificar_fila(_fila("Profesor de Danza"))[1:] == (
        "Docencia artística no musical", "SEGURA_CON_ESPECIALIDAD", "especialidad artística explícita"
    )


def test_universidad_laboral_no_es_cuerpo_funcionarial():
    estado, familia, seguridad, _ = clasificar_fila(_fila("Profesor Contratado Doctor de Universidad"))
    assert (estado, familia, seguridad) == ("PENDIENTE_REAL", "Universidad laboral/contractual", "DUDOSA")


def test_canones_aplicados_no_aparecen_como_pendientes():
    estado, familia, _, _ = clasificar_fila(_fila("Profesor/a de Piano", "Profesor de Música - Piano"))
    assert (estado, familia) == ("YA_NORMALIZADA", "Música normalizada")
    estado, familia, _, _ = clasificar_fila(_fila("Maestro", "Maestros"))
    assert (estado, familia) == ("YA_NORMALIZADA", "Maestros")
    estado, familia, _, _ = clasificar_fila(_fila("Catedrático de Universidad", "Catedráticos de Universidad"))
    assert (estado, familia) == ("YA_NORMALIZADA", "Universidad funcionarial")


def test_auditoria_reconcilia_y_no_modifica_sqlite():
    base = Path("datos/boe.db")
    mtime = base.stat().st_mtime_ns
    informe = auditar()
    assert informe["reconciliacion_filas"]["universo"] == informe["reconciliacion_filas"]["suma_estados"]
    assert informe["cruce_paso9h6"]["filas_detectadas"] == 1363
    assert not informe["cruce_paso9h6"]["contradicciones"]
    assert [fila["id"] for fila in informe["cruce_paso9h6"]["nuevos_casos_post31"]] == [70412]
    assert informe["estado_inicial"] == informe["estado_final"]
    assert base.stat().st_mtime_ns == mtime
    with sqlite3.connect(base) as con:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
