from types import SimpleNamespace

import base_datos
from reprocesar_plazos import _descargar_plazo, _texto_documento, reprocesar


def _base(tmp_path, schema="8"):
    ruta = tmp_path / "boe.db"
    conexion = base_datos.conectar(ruta)
    base_datos.crear_esquema(conexion)
    base_datos.guardar_metadata(conexion, schema_version=int(schema), data_version=2)
    conexion.execute(
        """INSERT INTO publicaciones(
            publicacion_id,enlace,fecha_boe,fecha_boe_original,version_extractor,
            estado_analisis,coincidencias
        ) VALUES (?,?,?,?,?,?,?)""",
        ("BOE-A-2026-1", "https://example.test/boe/txt.php", "2026-01-10",
         "10 de enero de 2026", "v1", "con_coincidencias", 1),
    )
    conexion.execute(
        """INSERT INTO oposiciones(
            oposicion_id,puesto,escala,subescala,clase,sistema,turno,fecha_boe,
            fecha_boe_original,enlace,publicacion_id,version_extractor
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (1, "Auxiliar", "--", "--", "--", "--", "--", "2026-01-10",
         "10 de enero de 2026", "https://example.test/boe/txt.php", "BOE-A-2026-1", "v1"),
    )
    conexion.commit()
    conexion.close()
    return ruta


def _respuesta(texto):
    return SimpleNamespace(
        content=texto.encode("utf-8"),
        raise_for_status=lambda: None,
    )


def test_documento_historico_usa_parser_xml_estandar():
    respuesta = _respuesta("<documento><p>Plazo de solicitudes: veinte días naturales.</p></documento>")
    assert _texto_documento(respuesta, "2004-01-10") == "Plazo de solicitudes: veinte días naturales."


def test_enlace_vacio_usa_url_canonica_del_publicacion_id():
    llamadas = []

    def obtener(url, timeout):
        llamadas.append(url)
        return _respuesta("<div id='textoxslt'>Plazo de solicitudes: veinte días naturales.</div>")

    _descargar_plazo({"publicacion_id": "BOE-A-2018-41", "enlace": "", "fecha_boe": "2018-01-01"}, obtener)
    assert llamadas == ["https://www.boe.es/diario_boe/txt.php?id=BOE-A-2018-41"]


def test_dry_run_no_escribe_y_devuelve_evidencia(tmp_path):
    ruta = _base(tmp_path)
    html = "<div id='textoxslt'>El plazo de solicitudes será de 20 días naturales desde el siguiente al de la publicación.</div>"
    llamadas = []

    def obtener(url, timeout):
        llamadas.append((url, timeout))
        return _respuesta(html)

    resultado = reprocesar(ruta, limite=1, estado=tmp_path / "estado.json", obtener=obtener)
    assert resultado["publicaciones_con_plazo"] == 1
    assert resultado["filas_oposiciones_actualizadas"] == 0
    assert llamadas[0][0].endswith("txt.php")
    conexion = base_datos.conectar(ruta, readonly=True)
    try:
        assert conexion.execute("SELECT fecha_fin_plazo FROM oposiciones").fetchone()[0] is None
    finally:
        conexion.close()


def test_aplicar_actualiza_filas_y_data_version_con_backup(tmp_path):
    ruta = _base(tmp_path)
    html = "<div id='textoxslt'>El plazo de solicitudes será de 20 días naturales desde el siguiente al de la publicación.</div>"
    resultado = reprocesar(
        ruta, limite=1, aplicar=True, directorio_backup=tmp_path / "backups",
        estado=tmp_path / "estado.json",
        obtener=lambda url, timeout: _respuesta(html),
    )
    assert resultado["filas_oposiciones_actualizadas"] == 1
    assert resultado["backup"]
    conexion = base_datos.conectar(ruta, readonly=True)
    try:
        fila = conexion.execute(
            "SELECT plazo_solicitudes,fecha_inicio_plazo,fecha_fin_plazo FROM oposiciones"
        ).fetchone()
        assert fila == ("20 días naturales", "2026-01-11", "2026-01-30")
        assert dict(conexion.execute("SELECT clave,valor FROM metadata"))["data_version"] == "3"
    finally:
        conexion.close()


def test_estado_persistente_evita_descarga_repetida(tmp_path):
    ruta = _base(tmp_path)
    estado = tmp_path / "estado.json"
    html = "<div id='textoxslt'>El plazo de solicitudes será de 10 días naturales.</div>"
    llamadas = []

    def obtener(url, timeout):
        llamadas.append(url)
        return _respuesta(html)

    reprocesar(ruta, limite=1, estado=estado, obtener=obtener)
    segundo = reprocesar(
        ruta, limite=1, aplicar=True, estado=estado, directorio_backup=tmp_path / "backups",
        obtener=lambda url, timeout: (_ for _ in ()).throw(AssertionError("no debe descargar")),
    )
    assert len(llamadas) == 1
    assert segundo["publicaciones_reanudadas"] == 1
    assert segundo["solicitudes_http"] == 0
    assert segundo["filas_oposiciones_actualizadas"] == 1


def test_reintentos_y_pausa_se_registran_en_estado(tmp_path, monkeypatch):
    ruta = _base(tmp_path)
    estado = tmp_path / "estado.json"
    llamadas = []
    pausas = []

    def obtener(url, timeout):
        llamadas.append(url)
        raise ValueError("fallo temporal")

    monkeypatch.setattr("reprocesar_plazos.time.sleep", lambda segundos: pausas.append(segundos))
    resultado = reprocesar(
        ruta, limite=1, estado=estado, reintentos=2, pausa=0.5, obtener=obtener
    )
    assert len(llamadas) == 2
    assert pausas
    assert resultado["errores"][0]["tipo_error"] == "ValueError"
