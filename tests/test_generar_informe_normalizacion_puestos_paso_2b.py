import sqlite3

from generar_informe_normalizacion_puestos_paso_2b import generar_informe


def test_informe_paso_2b_es_solo_lectura_y_expone_idempotencia(tmp_path):
    ruta = tmp_path / "boe.db"
    con = sqlite3.connect(ruta)
    con.executescript(
        "CREATE TABLE metadata(clave TEXT, valor TEXT);"
        "INSERT INTO metadata VALUES ('schema_version', '6'), ('data_version', '26');"
        "CREATE TABLE oposiciones(oposicion_id INTEGER, puesto TEXT, puesto_normalizado TEXT);"
    )
    con.execute(
        "INSERT INTO oposiciones VALUES (1, ?, ?)",
        ("Tècnico/a Superior", "Técnico/a Superior"),
    )
    con.commit()
    con.close()
    antes = ruta.read_bytes()

    informe = generar_informe(ruta)

    assert informe["resultado_idempotencia_final"]["fallos"] == 0
    assert informe["dry_run"]["cambios_fuera_objetivo"] == 1
    assert ruta.read_bytes() == antes
