import sqlite3
import csv

import pytest

import base_datos
import migrar_esquema_sqlite as migracion
import recalcular_geografia


def _base_v2(ruta, puestos=("Ingeniero/a Técnico/a Industrial", "Arquitecto")):
    conexion = base_datos.conectar(ruta)
    esquema_v2 = base_datos.ESQUEMA_V4.replace("    puesto_normalizado TEXT,\n", "")
    conexion.executescript(esquema_v2)
    conexion.executescript(base_datos.INDICES_V4)
    conexion.executemany(
        "INSERT INTO metadata(clave, valor) VALUES (?, ?)",
        [
            ("schema_version", "2"),
            ("data_version", "7"),
            ("created_at", "2026-01-01T00:00:00"),
            ("updated_at", "2026-01-01T00:00:00"),
        ],
    )
    for indice, puesto in enumerate(puestos, 1):
        pid = f"BOE-A-{indice}"
        conexion.execute(
            "INSERT INTO publicaciones VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, f"https://x/{indice}", "2026-01-01", "20260101", None,
             None, "1", "con_coincidencias", 1, None, None, None, None, None,
             None, None),
        )
        conexion.execute(
            """INSERT INTO oposiciones(
                num_plazas,puesto,administracion,escala,subescala,clase,sistema,
                turno,fecha_boe,fecha_boe_original,enlace,publicacion_id,version_extractor
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (1, puesto, "A", "--", "--", "--", "--", "--", "2026-01-01",
             "20260101", f"https://x/{indice}", pid, "1"),
        )
    conexion.commit(); conexion.close()
    return ruta


def test_migracion_v2_v3_preserva_original_y_normaliza(tmp_path):
    ruta = _base_v2(tmp_path / "boe.db")
    resultado = migracion.migrar_v2_v3(ruta, tmp_path / "backups")
    conexion = base_datos.conectar(ruta, readonly=True)
    try:
        filas = conexion.execute(
            "SELECT puesto, puesto_normalizado FROM oposiciones ORDER BY oposicion_id"
        ).fetchall()
        metadata = dict(conexion.execute("SELECT clave, valor FROM metadata"))
        columnas = [fila[1] for fila in conexion.execute("PRAGMA table_info(oposiciones)")]
        assert filas == [
            ("Ingeniero/a Técnico/a Industrial", "Ingeniero Técnico Industrial"),
            ("Arquitecto", "Arquitecto"),
        ]
        assert "puesto_normalizado" in columnas
        assert metadata["schema_version"] == "3"
        assert metadata["data_version"] == "8"
        assert base_datos.integrity_check(conexion) == ["ok"]
        assert base_datos.foreign_key_check(conexion) == []
    finally:
        conexion.close()
    assert resultado["actualizada"] is True
    assert resultado["data_version"] == "8"
    assert resultado["auditoria"]["filas"] == 2
    assert resultado["backup"]


def test_migracion_v3_es_idempotente(tmp_path):
    ruta = _base_v2(tmp_path / "boe.db")
    migracion.migrar_v2_v3(ruta, tmp_path / "backups")
    antes = base_datos.hash_archivo(ruta)
    resultado = migracion.migrar_v2_v3(ruta, tmp_path / "otros-backups")
    assert resultado == {"actualizada": False, "schema_version": "3", "data_version": "8"}
    assert base_datos.hash_archivo(ruta) == antes
    assert not (tmp_path / "otros-backups").exists()


def test_migracion_revierte_si_falla_normalizacion(tmp_path, monkeypatch):
    ruta = _base_v2(tmp_path / "boe.db")
    monkeypatch.setattr(
        migracion, "normalizar_puesto",
        lambda _: (_ for _ in ()).throw(RuntimeError("fallo deliberado")),
    )
    with pytest.raises(RuntimeError, match="fallo deliberado"):
        migracion.migrar_v2_v3(ruta, tmp_path / "backups")
    conexion = sqlite3.connect(ruta)
    try:
        metadata = dict(conexion.execute("SELECT clave, valor FROM metadata"))
        columnas = [fila[1] for fila in conexion.execute("PRAGMA table_info(oposiciones)")]
    finally:
        conexion.close()
    assert metadata["schema_version"] == "2"
    assert metadata["data_version"] == "7"
    assert "puesto_normalizado" not in columnas


def test_v2_da_error_productivo_con_comando_explicito(tmp_path):
    ruta = _base_v2(tmp_path / "boe.db")
    with pytest.raises(base_datos.EspejoSQLiteError, match="migrar_esquema_sqlite.py"):
        base_datos.validar_base_principal(ruta)


def _base_v4(ruta):
    con = base_datos.conectar(ruta)
    con.executescript(base_datos.ESQUEMA_V4)
    con.executescript(base_datos.INDICES_V4)
    con.executemany("INSERT INTO metadata(clave,valor) VALUES (?,?)", [
        ("schema_version", "4"), ("data_version", "7"),
        ("created_at", "2026-01-01T00:00:00"), ("updated_at", "2026-01-01T00:00:00"),
    ])
    casos = [
        ("Palma", "Mallorca", "Illes Balears"),
        ("Maó", "Menorca", "Illes Balears"),
        ("Santa Eulària des Riu", "Ibiza/Eivissa", "Illes Balears"),
        ("Sant Antoni de Portmany", "Ibiza/Eivissa", "Illes Balears"),
        ("Las Palmas de Gran Canaria", "Las Palmas", "Canarias"),
        ("Teguise", "Las Palmas", "Canarias"),
        ("Santa Cruz de Tenerife", "Santa Cruz de Tenerife", "Canarias"),
        ("Melilla", "Melilla", "Melilla"),
        ("", "Ibiza-Formentera", "Illes Balears"),
        ("Raiguer", "Mallorca", "Illes Balears"),
        ("Pollentia", "Mallorca", "Illes Balears"),
    ]
    for indice, (municipio, provincia, comunidad) in enumerate(casos, 1):
        publicacion = f"BOE-A-{indice}"
        con.execute("INSERT INTO publicaciones VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (publicacion, "https://x", "2026-01-01", "20260101", None, None, "1", "ok", 1,
                     None, None, None, None, None, None, None))
        con.execute("""INSERT INTO oposiciones(
            puesto,administracion,escala,subescala,clase,sistema,turno,fecha_boe,fecha_boe_original,
            enlace,publicacion_id,version_extractor,municipio,provincia,comunidad_autonoma
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    ("Auxiliar", "Consorcio Rector del Centro Universitario UNED Melilla (Ciudad de Melilla)" if municipio == "Melilla" else "A",
                     "--", "--", "--", "--", "--", "2026-01-01", "20260101", "https://x",
                     publicacion, "1", municipio or None, provincia, comunidad))
    con.commit(); con.close()
    return ruta


def test_recalculo_alias_municipal_persiste_fk_ine_en_la_primera_pasada(tmp_path):
    ruta = _base_v4(tmp_path / "boe.db")
    migracion.migrar_v4_v5(ruta, tmp_path / "migracion")
    migracion.migrar_v5_territorios_insulares(ruta, tmp_path / "islas")
    con = base_datos.conectar(ruta)
    try:
        con.execute("""UPDATE oposiciones SET administracion='Ayuntamiento de Alaguàs (Valencia)',
                      municipio=NULL, provincia='Valencia/València', comunidad_autonoma='Comunitat Valenciana',
                      ambito='LOCAL', tipo_entidad='MUNICIPAL', evidencia_geografica='', confianza_geografica='NO_ENCONTRADO'
                      WHERE oposicion_id=1""")
        con.commit()
    finally:
        con.close()
    primero = recalcular_geografia.recalcular(ruta, tmp_path / "recalculo")
    con = base_datos.conectar(ruta, readonly=True)
    try:
        assert con.execute("""SELECT municipio,municipio_codigo_ine,provincia,provincia_id,
                                     comunidad_autonoma,comunidad_id,evidencia_geografica
                              FROM oposiciones WHERE oposicion_id=1""").fetchone() == (
            "Alaquàs", "46005", "Valencia/València", "46", "Comunitat Valenciana", 11, "AYUNTAMIENTO"
        )
    finally:
        con.close()
    assert primero["filas_cambiadas"] >= 1
    assert recalcular_geografia.recalcular(ruta, tmp_path / "recalculo")["filas_cambiadas"] == 0


def test_migracion_v4_v5_importa_geografia_administrativa_y_preserva_textos(tmp_path):
    ruta = _base_v4(tmp_path / "boe.db")
    resultado = migracion.migrar_v4_v5(ruta, tmp_path / "backups")
    con = base_datos.conectar(ruta, readonly=True)
    try:
        assert dict(con.execute("SELECT clave,valor FROM metadata"))["schema_version"] == "5"
        assert con.execute("SELECT count(*) FROM comunidades_autonomas").fetchone()[0] == 19
        assert con.execute("SELECT count(*) FROM provincias").fetchone()[0] == 50
        with open(migracion.RUTA_MUNICIPIOS, encoding="utf-8-sig", newline="") as archivo:
            assert con.execute("SELECT count(*) FROM municipios").fetchone()[0] == sum(1 for _ in csv.DictReader(archivo, delimiter=";"))
        assert con.execute("SELECT count(*) FROM provincias WHERE nombre IN ('Ceuta','Melilla')").fetchone()[0] == 0
        ceuta_melilla = con.execute("""SELECT m.nombre,p.nombre,c.nombre,c.es_ciudad_autonoma
                                      FROM municipios m LEFT JOIN provincias p USING(provincia_id)
                                      JOIN comunidades_autonomas c USING(comunidad_id)
                                      WHERE m.nombre IN ('Ceuta','Melilla') ORDER BY m.nombre""").fetchall()
        assert ceuta_melilla == [("Ceuta", None, "Ceuta", 1), ("Melilla", None, "Melilla", 1)]
        filas = {municipio or "": (provincia, provincia_maestra, comunidad, codigo)
                 for municipio, provincia, provincia_maestra, comunidad, codigo in con.execute("""SELECT municipio, provincia,
            (SELECT nombre FROM provincias WHERE provincia_id=o.provincia_id),
            (SELECT nombre FROM comunidades_autonomas WHERE comunidad_id=o.comunidad_id), municipio_codigo_ine
            FROM oposiciones o""")}
        assert filas["Palma"] == ("Mallorca", "Illes Balears", "Illes Balears", "07040")
        assert filas["Maó"] == ("Menorca", "Illes Balears", "Illes Balears", "07032")
        assert filas["Santa Eulària des Riu"] == ("Ibiza/Eivissa", "Illes Balears", "Illes Balears", "07054")
        assert filas["Sant Antoni de Portmany"] == ("Ibiza/Eivissa", "Illes Balears", "Illes Balears", "07046")
        assert filas["Teguise"] == ("Las Palmas", "Las Palmas", "Canarias", "35024")
        assert filas["Santa Cruz de Tenerife"] == ("Santa Cruz de Tenerife", "Santa Cruz de Tenerife", "Canarias", "38038")
        assert filas["Melilla"] == ("Melilla", None, "Melilla", "52001")
        assert filas[""] == ("Ibiza-Formentera", "Illes Balears", "Illes Balears", None)
        assert filas["Raiguer"][0] == "Mallorca" and filas["Raiguer"][1:] == ("Illes Balears", "Illes Balears", None)
        assert filas["Pollentia"][0] == "Mallorca" and filas["Pollentia"][1:] == ("Illes Balears", "Illes Balears", None)
        assert base_datos.integrity_check(con) == ["ok"]
        assert base_datos.foreign_key_check(con) == []
    finally:
        con.close()
    assert resultado["actualizada"] is True and resultado["data_version"] == "8"
    with open(migracion.RUTA_MUNICIPIOS, encoding="utf-8-sig", newline="") as archivo:
        assert resultado["auditoria"]["municipios_fuente"] == sum(1 for _ in csv.DictReader(archivo, delimiter=";"))
    assert resultado["auditoria"]["metadata_municipios"] == resultado["auditoria"]["municipios_fuente"]


def test_migracion_v4_v5_es_idempotente(tmp_path):
    ruta = _base_v4(tmp_path / "boe.db")
    migracion.migrar_v4_v5(ruta, tmp_path / "backups")
    firma = base_datos.hash_archivo(ruta)
    assert migracion.migrar_v4_v5(ruta, tmp_path / "otros-backups") == {
        "actualizada": False, "schema_version": "5", "data_version": "8"
    }
    assert base_datos.hash_archivo(ruta) == firma
    assert not (tmp_path / "otros-backups").exists()


def test_migracion_v5_v6_crea_catalogo_historico_e_idempotente(tmp_path):
    ruta = _base_v4(tmp_path / "boe.db")
    migracion.migrar_v4_v5(ruta, tmp_path / "v5")
    migracion.migrar_v5_territorios_insulares(ruta, tmp_path / "islas")
    resultado = migracion.migrar_v5_v6_municipios_historicos(ruta, tmp_path / "v6")
    con = base_datos.conectar(ruta, readonly=True)
    try:
        assert dict(con.execute("SELECT clave,valor FROM metadata"))["schema_version"] == "6"
        assert con.execute("SELECT codigo_ine,fecha_hasta,codigo_ine_sucesor FROM municipios_historicos ORDER BY codigo_ine").fetchall() == [
            ("36011", "2016-10-19", "36902"), ("36012", "2016-10-19", "36902")]
        assert "municipio_historico_id" in {x[1] for x in con.execute("PRAGMA table_info(oposiciones)")}
        assert base_datos.integrity_check(con) == ["ok"] and base_datos.foreign_key_check(con) == []
    finally:
        con.close()
    assert resultado["actualizada"] is True
    assert migracion.migrar_v5_v6_municipios_historicos(ruta, tmp_path / "otra") == {
        "actualizada": False, "schema_version": "6", "data_version": resultado["data_version"]
    }


def test_recalculo_v6_guarda_fk_historica_sin_codigo_vigente(tmp_path):
    ruta = _base_v4(tmp_path / "boe.db")
    migracion.migrar_v4_v5(ruta, tmp_path / "v5")
    migracion.migrar_v5_territorios_insulares(ruta, tmp_path / "islas")
    con = base_datos.conectar(ruta)
    try:
        con.execute("""UPDATE oposiciones SET administracion='Ayuntamiento de Cerdedo (Pontevedra)',
            fecha_boe='2015-06-01', municipio=NULL, municipio_codigo_ine=NULL, provincia='Pontevedra',
            comunidad_autonoma='Galicia', ambito='LOCAL', tipo_entidad='MUNICIPAL' WHERE oposicion_id=1""")
        con.commit()
    finally:
        con.close()
    migracion.migrar_v5_v6_municipios_historicos(ruta, tmp_path / "v6")
    assert recalcular_geografia.recalcular(ruta, tmp_path / "recalculo")["filas_cambiadas"] >= 1
    con = base_datos.conectar(ruta, readonly=True)
    try:
        assert con.execute("""SELECT o.municipio,o.municipio_codigo_ine,h.codigo_ine
                             FROM oposiciones o JOIN municipios_historicos h USING(municipio_historico_id)
                             WHERE o.oposicion_id=1""").fetchone() == ("Cerdedo", None, "36011")
    finally:
        con.close()
    assert recalcular_geografia.recalcular(ruta, tmp_path / "recalculo")["filas_cambiadas"] == 0


def test_etapa_insular_v5_carga_catalogo_y_solo_decisiones_aprobadas(tmp_path):
    ruta = _base_v4(tmp_path / "boe.db")
    migracion.migrar_v4_v5(ruta, tmp_path / "admin")
    resultado = migracion.migrar_v5_territorios_insulares(ruta, tmp_path / "insular")
    con = base_datos.conectar(ruta, readonly=True)
    try:
        assert con.execute("SELECT count(*) FROM territorios_insulares").fetchone()[0] == 13
        assert con.execute("SELECT clase FROM territorios_insulares WHERE nombre='Ibiza-Formentera'").fetchone()[0] == "AGRUPACION_INSULAR_HISTORICA"
        assert con.execute("SELECT count(*) FROM provincias WHERE nombre IN ('Ceuta','Melilla')").fetchone()[0] == 0
        assert con.execute("SELECT count(*) FROM municipios WHERE codigo_ine='35024'").fetchone()[0] == 1
        assert con.execute("SELECT count(*) FROM municipios_territorios_insulares WHERE codigo_ine='35024'").fetchone()[0] == 2
        assert con.execute("SELECT count(*) FROM oposiciones_territorios_insulares").fetchone()[0] == 0
        assert base_datos.foreign_key_check(con) == []
    finally:
        con.close()
    assert resultado["actualizada"] is True and resultado["data_version"] == "9"
    catalogo = migracion.migrar_v5_territorios_insulares(ruta, tmp_path / "catalogo")
    assert catalogo["actualizada"] is True and catalogo["data_version"] == "10"
    assert catalogo["auditoria"] == {"nuevas": 154, "modificadas": 2, "relaciones": 156}
    provincia = migracion.migrar_v5_territorios_insulares(ruta, tmp_path / "provincia")
    assert provincia["actualizada"] is True and provincia["data_version"] == "11"
    assert provincia["filas_modificadas"] == 8
    con = base_datos.conectar(ruta, readonly=True)
    try:
        provincias = dict(con.execute("SELECT municipio,provincia FROM oposiciones"))
        assert provincias["Palma"] == "Illes Balears"
        assert provincias["Maó"] == "Illes Balears"
        assert provincias["Las Palmas de Gran Canaria"] == "Las Palmas"
        assert provincias["Santa Cruz de Tenerife"] == "Santa Cruz de Tenerife"
        assert provincias["Melilla"] is None
    finally:
        con.close()
    sedes = migracion.migrar_v5_territorios_insulares(ruta, tmp_path / "sedes")
    assert sedes["actualizada"] is True and sedes["data_version"] == "12"
    assert sedes["sedes_importadas"] == 84 and sedes["filas_modificadas"] == 0
    aliases = migracion.migrar_v5_territorios_insulares(ruta, tmp_path / "aliases")
    assert aliases["actualizada"] is True and aliases["data_version"] == "13"
    assert aliases["alias_importados"] == 4 and aliases["filas_modificadas"] == 0
    universidades = migracion.migrar_v5_territorios_insulares(ruta, tmp_path / "universidades")
    assert universidades["actualizada"] is True and universidades["data_version"] == "14"
    assert universidades["universidades"] == 27
    con = base_datos.conectar(ruta, readonly=True)
    try:
        assert con.execute("SELECT count(*) FROM universidades").fetchone()[0] == 27
        assert con.execute("SELECT count(*) FROM alias_universidades").fetchone()[0] == 3
    finally:
        con.close()
    assert migracion.migrar_v5_territorios_insulares(ruta, tmp_path / "segundo") == {
        "actualizada": False, "schema_version": "5", "data_version": "14"
    }


def test_catalogo_municipio_isla_v5_es_completo_y_no_altera_oposiciones(tmp_path):
    ruta = _base_v4(tmp_path / "boe.db")
    migracion.migrar_v4_v5(ruta, tmp_path / "admin")
    migracion.migrar_v5_territorios_insulares(ruta, tmp_path / "insular")
    con = base_datos.conectar(ruta)
    try:
        lanzarote = con.execute("SELECT territorio_id FROM territorios_insulares WHERE nombre='Lanzarote'").fetchone()[0]
        con.execute("INSERT INTO oposiciones_territorios_insulares VALUES (?,?,?,?)", (1, lanzarote, "PRUEBA", "v1"))
        con.commit()
    finally:
        con.close()


def test_correcciones_aprobadas_de_sede_son_exactas_e_idempotentes(tmp_path):
    ruta = _base_v4(tmp_path / "boe.db")
    migracion.migrar_v4_v5(ruta, tmp_path / "admin")
    migracion.migrar_v5_territorios_insulares(ruta, tmp_path / "islas")
    migracion.migrar_v5_catalogo_municipios_territorios_insulares(ruta, tmp_path / "catalogo")
    migracion.migrar_v5_provincias_administrativas(ruta, tmp_path / "provincia")
    con = base_datos.conectar(ruta)
    try:
        con.execute("""UPDATE oposiciones SET administracion='Consejo de Seguridad Nuclear',
                     administracion_normalizada='Consejo de Seguridad Nuclear',ambito='INDETERMINADO',
                     tipo_entidad='INDETERMINADO',municipio='Ea',municipio_codigo_ine=NULL,provincia='Vizcaya',
                     provincia_id=NULL,comunidad_autonoma=NULL,comunidad_id=NULL,confianza_geografica='NO_ENCONTRADO',
                     evidencia_geografica='' WHERE oposicion_id <= 9""")
        con.execute("""UPDATE oposiciones SET administracion='Consorcio de Teatro Fortuny',
                     administracion_normalizada='Consorcio de Teatro Fortuny',ambito='LOCAL',
                     tipo_entidad='SUPRAMUNICIPAL',municipio='Ea',municipio_codigo_ine=NULL,provincia='Vizcaya',
                     provincia_id=NULL,comunidad_autonoma=NULL,comunidad_id=NULL,confianza_geografica='NO_ENCONTRADO',
                     evidencia_geografica='' WHERE oposicion_id IN (10,11)""")
        con.commit()
    finally:
        con.close()
    resultado = migracion.migrar_v5_correcciones_geograficas_aprobadas(ruta, tmp_path / "sedes")
    con = base_datos.conectar(ruta, readonly=True)
    try:
        assert resultado["filas_modificadas"] == 11
        datos = {r[0]: r[1:] for r in con.execute("""SELECT administracion,ambito,tipo_entidad,municipio,
            municipio_codigo_ine,provincia,provincia_id,comunidad_autonoma,comunidad_id,confianza_geografica,
            evidencia_geografica FROM oposiciones WHERE oposicion_id IN (1,10)""")}
        assert datos["Consejo de Seguridad Nuclear"] == ("ESTATAL", "ESTATAL", "Madrid", "28079", "Madrid", "28", "Comunidad de Madrid", 10, "ALTA", "SEDE_ADMINISTRATIVA_CATALOGADA")
        assert datos["Consorcio de Teatro Fortuny"] == ("LOCAL", "SUPRAMUNICIPAL", "Reus", "43123", "Tarragona", "43", "Cataluña/Catalunya", 7, "ALTA", "ENTIDAD_TERRITORIAL_CATALOGADA")
    finally:
        con.close()
    assert migracion.migrar_v5_correcciones_geograficas_aprobadas(ruta, tmp_path / "segundo") == {
        "actualizada": False, "schema_version": "5", "data_version": "12"
    }


def test_catalogo_sedes_v5_importa_y_protege_destino(tmp_path):
    ruta = _base_v4(tmp_path / "boe.db")
    migracion.migrar_v4_v5(ruta, tmp_path / "admin")
    migracion.migrar_v5_territorios_insulares(ruta, tmp_path / "islas")
    migracion.migrar_v5_catalogo_municipios_territorios_insulares(ruta, tmp_path / "catalogo")
    migracion.migrar_v5_provincias_administrativas(ruta, tmp_path / "provincia")
    con = base_datos.conectar(ruta)
    try:
        con.execute("""UPDATE oposiciones SET administracion='Ministerio de Justicia', puesto='Fiscalía Provincial de Sevilla',
                     administracion_normalizada='Ministerio de Justicia', ambito='ESTATAL', tipo_entidad='ESTATAL', municipio='',
                     municipio_codigo_ine=NULL, provincia='Sevilla', provincia_id=NULL, comunidad_autonoma='Andalucía', comunidad_id=NULL,
                     confianza_geografica='ALTA', evidencia_geografica='DESTINO_PUESTO' WHERE oposicion_id=1""")
        con.commit()
    finally:
        con.close()
    resultado = migracion.migrar_v5_sedes_administrativas(ruta, tmp_path / "sedes")
    con = base_datos.conectar(ruta, readonly=True)
    try:
        assert resultado["sedes_importadas"] == 84 and resultado["filas_modificadas"] == 1
        assert con.execute("SELECT count(*) FROM sedes_administraciones").fetchone()[0] == 84
        assert con.execute("SELECT municipio,municipio_codigo_ine,provincia,provincia_id,comunidad_autonoma,comunidad_id,evidencia_geografica FROM oposiciones WHERE oposicion_id=1").fetchone() == (
            "Madrid", "28079", "Madrid", "28", "Comunidad de Madrid", 10, "SEDE_ADMINISTRATIVA_CATALOGADA")
        assert base_datos.integrity_check(con) == ["ok"] and base_datos.foreign_key_check(con) == []
    finally:
        con.close()
    assert migracion.migrar_v5_sedes_administrativas(ruta, tmp_path / "segundo") == {
        "actualizada": False, "schema_version": "5", "data_version": "12"
    }


def test_alias_historicos_comparten_sede_canonica(tmp_path):
    ruta = _base_v4(tmp_path / "boe.db")
    migracion.migrar_v4_v5(ruta, tmp_path / "admin")
    migracion.migrar_v5_territorios_insulares(ruta, tmp_path / "islas")
    migracion.migrar_v5_catalogo_municipios_territorios_insulares(ruta, tmp_path / "catalogo")
    migracion.migrar_v5_provincias_administrativas(ruta, tmp_path / "provincia")
    migracion.migrar_v5_sedes_administrativas(ruta, tmp_path / "sedes")
    con = base_datos.conectar(ruta)
    try:
        con.execute("UPDATE oposiciones SET administracion='Ministerio de Hacienda y Administraciones Públicas', municipio='', provincia='', comunidad_autonoma='', evidencia_geografica='' WHERE oposicion_id=1")
        con.execute("UPDATE oposiciones SET administracion='Ministerio de Hacienda y Función Pública', municipio='', provincia='', comunidad_autonoma='', evidencia_geografica='' WHERE oposicion_id=2")
        con.commit()
    finally: con.close()
    resultado = migracion.migrar_v5_alias_sedes_administrativas(ruta, tmp_path / "aliases")
    con = base_datos.conectar(ruta, readonly=True)
    try:
        assert resultado["alias_importados"] == 4 and resultado["filas_modificadas"] == 2
        assert con.execute("SELECT count(DISTINCT sede_id) FROM alias_sedes_administraciones").fetchone()[0] == 1
        assert con.execute("SELECT count(*) FROM oposiciones WHERE oposicion_id IN (1,2) AND municipio='Madrid' AND evidencia_geografica='SEDE_ADMINISTRATIVA_CATALOGADA'").fetchone()[0] == 2
    finally: con.close()


def test_etapa4_solo_anade_las_mancomunidades_mallorquinas_aprobadas(tmp_path):
    ruta = _base_v4(tmp_path / "boe.db")
    con = base_datos.conectar(ruta)
    try:
        for oid, admin in enumerate((
            "Mancomunidad Migjorn de Mallorca", "Mancomunidad Migjorn de Mallorca",
            "Mancomunidad Migjorn de Mallorca", "Mancomunidad Migjorn de Mallorca",
            "Mancomunidad Migjorn de Mallorca", "Mancomunidad Pla de Mallorca",
        ), 1):
            con.execute("""UPDATE oposiciones SET administracion=?,administracion_normalizada=?,municipio=NULL,
                         provincia='Mallorca',comunidad_autonoma='Illes Balears',ambito='LOCAL',
                         tipo_entidad='SUPRAMUNICIPAL',confianza_geografica='ALTA',
                         evidencia_geografica='MANCOMUNIDAD_TERRITORIO' WHERE oposicion_id=?""", (admin, admin, oid))
        con.commit()
    finally:
        con.close()
    migracion.migrar_v4_v5(ruta, tmp_path / "admin")
    migracion.migrar_v5_territorios_insulares(ruta, tmp_path / "islas")
    migracion.migrar_v5_catalogo_municipios_territorios_insulares(ruta, tmp_path / "catalogo")
    resultado = migracion.migrar_v5_provincias_administrativas(ruta, tmp_path / "provincia")
    con = base_datos.conectar(ruta, readonly=True)
    try:
        assert resultado["relaciones_territorios_nuevas"] == 6
        assert con.execute("SELECT count(*) FROM oposiciones_territorios_insulares").fetchone()[0] == 6
        assert con.execute("SELECT count(*) FROM oposiciones WHERE oposicion_id <= 6 AND provincia='Illes Balears' AND provincia_id='07'").fetchone()[0] == 6
        assert con.execute("""SELECT count(*) FROM oposiciones_territorios_insulares ot
                              JOIN territorios_insulares t USING(territorio_id)
                              WHERE t.nombre='Mallorca' AND ot.evidencia='MANCOMUNIDAD_TERRITORIO'""").fetchone()[0] == 6
        assert migracion.normalizar_referencias_administrativas(con, "Ceuta", "Ceuta", "") == (
            "51001", None, "Ceuta", None, 8,
        )
        assert migracion.normalizar_referencias_administrativas(con, "Melilla", "Melilla", "Melilla") == (
            "52001", None, "Melilla", None, 16,
        )
    finally:
        con.close()
    migracion.migrar_v5_catalogo_municipios_territorios_insulares(ruta, tmp_path / "catalogo")
    con = base_datos.conectar(ruta, readonly=True)
    try:
        universo = con.execute("""SELECT count(*) FROM municipios m JOIN provincias p USING(provincia_id)
                                  WHERE p.nombre IN ('Illes Balears','Las Palmas','Santa Cruz de Tenerife')""").fetchone()[0]
        cobertura = con.execute("""SELECT count(*) FROM (
            SELECT m.codigo_ine FROM municipios m JOIN provincias p USING(provincia_id)
            LEFT JOIN municipios_territorios_insulares mt USING(codigo_ine)
            WHERE p.nombre IN ('Illes Balears','Las Palmas','Santa Cruz de Tenerife')
            GROUP BY m.codigo_ine HAVING count(mt.territorio_id)=0)""").fetchone()[0]
        distribucion = dict(con.execute("""SELECT t.nombre,count(*) FROM municipios_territorios_insulares mt
                                           JOIN territorios_insulares t USING(territorio_id)
                                           GROUP BY t.nombre"""))
        assert universo == 155 and cobertura == 0
        assert distribucion == {"El Hierro": 3, "Formentera": 1, "Fuerteventura": 6, "Gran Canaria": 21,
                                "Ibiza/Eivissa": 5, "La Gomera": 6, "La Graciosa": 1, "La Palma": 14,
                                "Lanzarote": 7, "Mallorca": 53, "Menorca": 8, "Tenerife": 31}
        assert con.execute("SELECT count(*) FROM municipios_territorios_insulares").fetchone()[0] == 156
        assert con.execute("SELECT count(*) FROM municipios_territorios_insulares WHERE codigo_ine='35024'").fetchone()[0] == 2
        assert con.execute("SELECT count(*) FROM municipios WHERE nombre='La Graciosa'").fetchone()[0] == 0
        assert con.execute("""SELECT count(*) FROM municipios_territorios_insulares mt
                              JOIN territorios_insulares t USING(territorio_id)
                              WHERE t.nombre='Ibiza-Formentera'""").fetchone()[0] == 0
        assert con.execute("SELECT count(*) FROM oposiciones_territorios_insulares").fetchone()[0] == 6
        assert con.execute("""SELECT count(*) FROM oposiciones o
                              JOIN oposiciones_territorios_insulares ot USING(oposicion_id)
                              WHERE o.municipio='Teguise'""").fetchone()[0] == 0
        assert con.execute("SELECT count(*) FROM municipios WHERE nombre IN ('Raiguer','Pollentia')").fetchone()[0] == 0
        ejemplos = {
            "07040": ["Mallorca"], "07033": ["Mallorca"], "07032": ["Menorca"], "07015": ["Menorca"],
            "07026": ["Ibiza/Eivissa"], "07054": ["Ibiza/Eivissa"], "07046": ["Ibiza/Eivissa"], "07024": ["Formentera"],
            "35016": ["Gran Canaria"], "35026": ["Gran Canaria"], "35004": ["Lanzarote"],
            "35024": ["La Graciosa", "Lanzarote"], "35017": ["Fuerteventura"], "38038": ["Tenerife"],
            "38023": ["Tenerife"], "38037": ["La Palma"], "38024": ["La Palma"],
            "38036": ["La Gomera"], "38048": ["El Hierro"],
        }
        for codigo, esperado in ejemplos.items():
            actual = [x[0] for x in con.execute("""SELECT t.nombre FROM municipios_territorios_insulares mt
                                                  JOIN territorios_insulares t USING(territorio_id)
                                                  WHERE mt.codigo_ine=? ORDER BY t.nombre""", (codigo,))]
            assert actual == esperado
        assert con.execute("""SELECT count(*) FROM municipios_territorios_insulares mt
                              JOIN municipios m USING(codigo_ine) JOIN territorios_insulares t USING(territorio_id)
                              WHERE m.provincia_id != t.provincia_id OR m.comunidad_id != t.comunidad_id""").fetchone()[0] == 0
        assert base_datos.integrity_check(con) == ["ok"]
        assert base_datos.foreign_key_check(con) == []
    finally:
        con.close()
