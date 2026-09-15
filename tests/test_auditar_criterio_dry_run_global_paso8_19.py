import sqlite3

from normalizacion_puestos import normalizar_puesto
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import CATEGORIAS, auditar


def _crear_bd(ruta):
    con = sqlite3.connect(ruta)
    con.executescript("""
        CREATE TABLE metadata (clave TEXT, valor TEXT);
        INSERT INTO metadata VALUES ('schema_version', '6'), ('data_version', '47');
        CREATE TABLE oposiciones (
            oposicion_id INTEGER, puesto TEXT, puesto_normalizado TEXT, num_plazas REAL,
            administracion TEXT, ambito TEXT, tipo_entidad TEXT, escala TEXT, subescala TEXT,
            sistema TEXT, municipio TEXT, provincia TEXT);
    """)
    con.executemany("INSERT INTO oposiciones VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
        (1, 'Policía', 'Policía Local', 2, 'Ayuntamiento de Pinto', 'LOCAL', 'MUNICIPAL', '', '', '', 'Pinto', 'Madrid'),
        (2, 'Policía', 'Policía Nacional', 3, 'Ministerio del Interior', 'ESTATAL', 'ESTATAL', 'Básica', '', 'Oposición', '', ''),
        (3, 'Trabajadora Social', 'Trabajadora Social', 5, '', '', '', '', '', '', '', ''),
        (4, 'Policía', 'Otro canon', 7, 'Ayuntamiento de Pinto', 'LOCAL', 'MUNICIPAL', '', '', '', 'Pinto', 'Madrid'),
    ])
    con.commit(); con.close()


def test_invariantes_textuales_policia_no_inventan_contexto():
    assert normalizar_puesto('Policía Local') == 'Policía Local'
    assert normalizar_puesto('Policía') != 'Policía Local'
    assert normalizar_puesto('Policía') != 'Policía Nacional'


def test_auditoria_separa_contexto_texto_e_incierto_y_es_solo_lectura(tmp_path):
    ruta = tmp_path / 'prueba.db'; _crear_bd(ruta); antes = ruta.read_bytes()
    informe = auditar(ruta)
    assert ruta.read_bytes() == antes and informe['sqlite_modificada'] is False
    assert informe['total_discrepancias'] == 4
    assert informe['cambios_reales_recalculables']['ids'] == [3]
    assert informe['discrepancias_contextuales_no_recalculables']['ids'] == [1, 2]
    assert informe['discrepancias_no_clasificables_automaticamente']['ids'] == [4]
    assert sum(informe[c]['filas'] for c in CATEGORIAS) == informe['total_discrepancias']
    assert sum(informe[c]['plazas'] for c in CATEGORIAS) == informe['total_plazas_discrepantes']
    assert informe['sin_duplicados'] is True


def test_criterio_no_depende_de_exclusion_lexica_ni_ids_fijos():
    fuente = __import__('inspect').getsource(__import__('scripts.audit.auditar_criterio_dry_run_global_paso8_19', fromlist=['*']))
    assert 'if puesto == "Policía"' not in fuente
    assert 'if puesto == \'Policía\'' not in fuente
