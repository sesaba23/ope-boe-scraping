import sqlite3

from analizar_normalizacion_puestos import auditar, clasificar_puesto
from normalizacion_puestos import normalizar_puesto


def test_policia_local_y_rangos_se_distinguen():
    assert clasificar_puesto("Agente de Policía Local")[:3] == ("policia_local", "alta_confianza", "Policía Local")
    assert clasificar_puesto("Inspector de Policía Local")[1] == "excluida"
    assert clasificar_puesto("Agentes de la Policía Local")[:3] == ("policia_local", "alta_confianza", "Policía Local")


def test_auxiliar_tiene_precedencia_y_falsos_positivos_se_excluyen():
    assert clasificar_puesto("Auxiliar Administrativa de Secretaría")[:3] == ("auxiliar_administrativo", "alta_confianza", "Auxiliar Administrativo")
    assert clasificar_puesto("Auxiliar de Servicios Administrativos")[1] == "excluida"
    assert clasificar_puesto("Técnico de Administración General")[0] is None


def test_genero_plural_puntuacion_y_espacios_administrativo():
    assert clasificar_puesto("  Administrativas  ")[:3] == ("administrativo", "alta_confianza", "Administrativo")
    assert clasificar_puesto("plaza de Administrativo/a")[:3] == ("administrativo", "alta_confianza", "Administrativo")
    assert clasificar_puesto("Administrativo/va")[1] == "dudosa"


def test_auditoria_y_motor_comparten_preprocesado_antes_de_clasificar():
    # La barra con espacios se limpia igual para la auditoría y el motor.
    assert clasificar_puesto("Administrativo/ a de Personal")[:3] == (
        "administrativo", "alta_confianza", "Administrativo"
    )
    assert normalizar_puesto("Administrativo/ a de Personal") == "Administrativo"


def test_auditoria_detecta_null_inconsistencias_y_no_escribe(tmp_path):
    ruta = tmp_path / "boe.db"; con = sqlite3.connect(ruta)
    con.execute("CREATE TABLE oposiciones(oposicion_id INTEGER,puesto TEXT,puesto_normalizado TEXT)")
    con.executemany("INSERT INTO oposiciones VALUES (?,?,?)", [(1, "Administrativo", None), (2, "Administrativo", "Administrativa"), (3, "Policía Local", "Policía Local")])
    con.commit(); con.close(); antes = ruta.read_bytes()
    informe = auditar(ruta)
    assert informe["puesto_normalizado"]["null"] == 1
    assert informe["familias"]["administrativo"]["potencialmente_modificables"] == 2
    assert len(informe["inconsistencias_mismo_puesto"]) == 1
    assert ruta.read_bytes() == antes


def test_resultado_vacio(tmp_path):
    ruta = tmp_path / "boe.db"; con = sqlite3.connect(ruta)
    con.execute("CREATE TABLE oposiciones(oposicion_id INTEGER,puesto TEXT,puesto_normalizado TEXT)"); con.commit(); con.close()
    assert auditar(ruta)["total_oposiciones"] == 0


def test_motor_productivo_aplica_solo_altas_y_es_idempotente():
    seguros = {
        "Policia Local": "Policía Local", "Agentes de la Policía Local": "Policía Local",
        "Auxiliar Administrativo/a de Administración General": "Auxiliar Administrativo",
        "Administrativos": "Administrativo",
    }
    for texto, canon in seguros.items():
        assert normalizar_puesto(texto) == canon
        assert normalizar_puesto(normalizar_puesto(texto)) == canon
    for texto in ("Oficial de Policía Local", "Cabo de la Policía Local", "Auxiliar de Policía Local", "Auxiliar Administrativo/va", "Administrativo/va", "Técnico de Gestión Administrativa"):
        assert normalizar_puesto(texto) != "Policía Local" or texto == "Policía Local"
        assert normalizar_puesto(texto) not in {"Auxiliar Administrativo", "Administrativo"}
