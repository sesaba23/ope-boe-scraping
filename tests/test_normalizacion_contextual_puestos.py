import pytest
import sqlite3

from normalizacion_contextual_puestos import normalizar_puesto_contextual, normalizar_puesto_efectivo
from scripts.audit.dry_run_policia_contextual_paso5 import ejecutar
from recalcular_puestos_contextuales import _plan


def test_policia_nacional_exige_toda_la_evidencia_y_es_trazable():
    r=normalizar_puesto_contextual('Policía',administracion='Ministerio del Interior',ambito='ESTATAL',tipo_entidad='ESTATAL',escala='Básica',sistema='Oposición')
    assert (r.normalizado,r.regla,r.confianza)==('Policía Nacional','POLICIA_NACIONAL_MINISTERIO_INTERIOR_ESCALA_BASICA','ALTA')
    assert normalizar_puesto_contextual('Policía',administracion='Ministerio del Interior',ambito='ESTATAL',tipo_entidad='ESTATAL',escala='Ejecutiva',sistema='Oposición').regla is None


@pytest.mark.parametrize(("oposicion_id", "plazas"), [(24085, 153), (24559, 140), (25324, 254)])
def test_casos_estatales_auditados_son_policia_nacional(oposicion_id, plazas):
    resultado = normalizar_puesto_contextual('Policía', administracion='Ministerio del Interior', ambito='ESTATAL', tipo_entidad='ESTATAL', escala='Básica', sistema='Oposición')
    assert oposicion_id in {24085, 24559, 25324}
    assert plazas in {153, 140, 254}
    assert resultado.normalizado == 'Policía Nacional'


def test_contexto_municipal_positivo_y_precedencia_textual():
    r=normalizar_puesto_contextual('Policia',administracion='Ayuntamiento de Pinto',ambito='LOCAL',tipo_entidad='MUNICIPAL',municipio='Pinto',provincia='Madrid')
    assert (r.normalizado,r.regla)==('Policía Local','POLICIA_LOCAL_ADMINISTRACION_MUNICIPAL_MUNICIPIO')
    assert normalizar_puesto_contextual('Policía Local',administracion='Ayuntamiento de Pinto',ambito='LOCAL',tipo_entidad='MUNICIPAL',municipio='Pinto').regla is None


def test_contextos_incompletos_y_guardia_urbana_no_cambian():
    assert normalizar_puesto_contextual('Policía').regla is None
    assert normalizar_puesto_contextual('Policía',administracion='Administración Local',ambito='INDETERMINADO',tipo_entidad='INDETERMINADO',escala='Administración Especial',subescala='Servicios Especiales').regla is None
    assert normalizar_puesto_contextual('Guardia Urbana',administracion='Ayuntamiento de Barcelona',ambito='LOCAL',tipo_entidad='MUNICIPAL',municipio='Barcelona').regla is None


@pytest.mark.parametrize("oposicion_id", [27123, 27694, 28254])
def test_casos_probables_indeterminados_siguen_sin_cambio(oposicion_id):
    resultado = normalizar_puesto_contextual('Policía', administracion='Administración Local', ambito='INDETERMINADO', tipo_entidad='INDETERMINADO', escala='Administración Especial', subescala='Servicios Especiales')
    assert oposicion_id in {27123, 27694, 28254}
    assert resultado.regla is None


def test_dry_run_contextual_es_solo_lectura(tmp_path):
    ruta = tmp_path / 'prueba.db'
    con = sqlite3.connect(ruta)
    con.execute('CREATE TABLE metadata(clave TEXT PRIMARY KEY, valor TEXT)')
    con.executemany('INSERT INTO metadata VALUES (?,?)', [('schema_version', '6'), ('data_version', '28')])
    con.execute('''CREATE TABLE oposiciones(
        oposicion_id INTEGER, puesto TEXT, puesto_normalizado TEXT, num_plazas INTEGER,
        administracion TEXT, ambito TEXT, tipo_entidad TEXT, escala TEXT, subescala TEXT,
        sistema TEXT, clase TEXT, municipio TEXT, provincia TEXT)''')
    con.execute("INSERT INTO oposiciones VALUES (1,'Policía','Policía',1,'Ministerio del Interior','ESTATAL','ESTATAL','Básica','','Oposición','','Madrid','Madrid')")
    con.commit(); con.close(); antes = ruta.read_bytes()
    informe = ejecutar(ruta)
    assert informe['total_propuestas'] == 1
    assert ruta.read_bytes() == antes


def test_plan_contextual_solo_actualiza_puesto_normalizado():
    fila = [None] * 25
    fila[0] = 1; fila[1] = 2; fila[2] = 'Policía'; fila[3] = 'Ministerio del Interior'; fila[4] = 'Básica'; fila[5] = ''; fila[7] = 'Oposición'; fila[13] = 'Madrid'; fila[14] = 'Madrid'; fila[21] = 'Policía'; fila[23] = 'ESTATAL'; fila[24] = 'ESTATAL'
    cambios, informe = _plan([tuple(fila)])
    assert informe['filas_que_cambiarian'] == 1
    assert cambios[0]['nuevo'] == 'Policía Nacional'


def test_composicion_conserva_policia_local_contextual_frente_a_textual():
    resultado = normalizar_puesto_contextual(
        'Policía', administracion='Ayuntamiento de Pinto', ambito='LOCAL',
        tipo_entidad='MUNICIPAL', municipio='Pinto', provincia='Madrid',
    )
    assert resultado.textual == 'Policía'
    assert resultado.normalizado == 'Policía Local'
    assert resultado.normalizado != resultado.textual


def test_composicion_conserva_policia_nacional_contextual_frente_a_textual():
    resultado = normalizar_puesto_contextual(
        'Policía', administracion='Ministerio del Interior', ambito='ESTATAL',
        tipo_entidad='ESTATAL', escala='Básica', sistema='Oposición',
    )
    assert resultado.textual == 'Policía'
    assert resultado.normalizado == 'Policía Nacional'
    assert resultado.normalizado != resultado.textual


def test_nueva_regla_textual_no_sobrescribe_una_capa_contextual_inexistente():
    resultado = normalizar_puesto_contextual(
        'Ayudantes de Instituciones Penitenciarias por el sistema general de acceso libre'
    )
    assert resultado.textual == 'Ayudantes de Instituciones Penitenciarias'
    assert resultado.normalizado == resultado.textual
    assert resultado.regla is None
    assert normalizar_puesto_contextual(
        resultado.original
    ).normalizado == resultado.normalizado


def test_normalizador_efectivo_compone_texto_y_contexto_y_es_idempotente():
    datos = dict(
        administracion='Ayuntamiento de Pinto', ambito='LOCAL',
        tipo_entidad='MUNICIPAL', municipio='Pinto', provincia='Madrid',
    )
    resultado = normalizar_puesto_efectivo('Policía', **datos)
    assert (resultado.textual, resultado.normalizado) == ('Policía', 'Policía Local')
    assert normalizar_puesto_efectivo('Policía', **datos).normalizado == resultado.normalizado


def test_normalizador_efectivo_aplica_ayudantes_sin_contexto():
    resultado = normalizar_puesto_efectivo(
        'Ayudantes de Instituciones Penitenciarias por el sistema general de acceso libre'
    )
    assert resultado.normalizado == 'Ayudantes de Instituciones Penitenciarias'
    assert resultado.regla is None
