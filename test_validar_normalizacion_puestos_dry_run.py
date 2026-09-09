import sqlite3

from validar_normalizacion_puestos_dry_run import ejecutar_dry_run


def test_dry_run_lee_sin_escribir_y_detecta_solo_familias_objetivo(tmp_path):
    ruta = tmp_path / "boe.db"; con = sqlite3.connect(ruta)
    con.executescript("CREATE TABLE metadata(clave TEXT,valor TEXT); INSERT INTO metadata VALUES ('schema_version','6'),('data_version','26'); CREATE TABLE oposiciones(oposicion_id INTEGER,puesto TEXT,puesto_normalizado TEXT);")
    con.executemany("INSERT INTO oposiciones VALUES (?,?,?)", [(1, "Agente de Policía Local", "Agente de Policía Local"), (2, "Auxiliar Administrativo", "Auxiliar Administrativo"), (3, "Oficial de Policía Local", "Oficial de Policía Local")])
    con.commit(); con.close(); antes = ruta.read_bytes()
    r = ejecutar_dry_run(ruta)
    assert r["cambios_totales"] == 1 and r["cambios_fuera_objetivo"] == 0
    assert r["validacion_cruzada"]["auditoria_no_segura_y_motor_cambia"] == 0
    assert r["idempotencia_fallos"] == 0 and ruta.read_bytes() == antes
