"""Pruebas herméticas del cargador histórico de fase 1 (solo JSON)."""
import json
from pathlib import Path
import shutil
from io import StringIO

import pandas as pd

import pytest

import cargar_historico_boe as cargador
from procesamiento_historico import cargar_estado, ruta_estado


def _catalogo(numero=4):
    return [
        {"Publicacion_ID": f"BOE-A-2004-{indice}", "Fecha_boe": "2004-01-01",
         "Enlace": f"https://ejemplo.test/txt.php?id={indice}"}
        for indice in range(1, numero + 1)
    ]


def _descubrimiento(catalogo, llamadas=None):
    def descubrir(desde, hasta):
        if llamadas is not None:
            llamadas.append((desde, hasta))
        return catalogo, [{"fecha": "2004/01/01", "estado": "CON_PUBLICACIONES",
                            "numero_publicaciones": len(catalogo)}]
    return descubrir


def _procesador(resultados, llamadas=None, comprobar_estado=None):
    def procesar(ficha):
        if llamadas is not None:
            llamadas.append(ficha["Publicacion_ID"])
        if comprobar_estado is not None:
            assert comprobar_estado.exists()
        valor = resultados[ficha["Publicacion_ID"]]
        if isinstance(valor, BaseException):
            raise valor
        return valor
    return procesar


def test_cli_parsea_y_transmite_argumentos(monkeypatch):
    recibido = {}

    def ejecutar(desde, hasta, limite, reintentar):
        recibido.update(desde=desde, hasta=hasta, limite=limite, reintentar=reintentar)
        return {"publicaciones_procesadas": 0, "publicaciones_totales": 0,
                "publicaciones_pendientes": 0, "publicaciones_error": 0,
                "publicaciones_indeterminadas": 0}, Path("estado.json")

    monkeypatch.setattr(cargador, "ejecutar", ejecutar)
    cargador.main(["--desde", "2004-01-01", "--hasta", "2004-01-31",
                   "--limite-publicaciones", "10", "--reintentar-errores"])
    assert recibido == {"desde": "2004-01-01", "hasta": "2004-01-31",
                        "limite": 10, "reintentar": True}


def test_descubrimiento_catalogo_completo_y_deduplicado():
    def api(fecha):
        return {"estado": "OK", "sumario": {"fecha": fecha}}

    def extraer(resultado):
        return {"estado": "CON_PUBLICACIONES", "publicaciones": [
            {"Publicacion_ID": "BOE-A-2004-1", "url_html": "https://x/1/txt.php", "titulo": "Título", "departamento": "Departamento"},
            {"Publicacion_ID": "BOE-A-2004-1", "url_html": "https://x/1/txt.php"},
            {"Publicacion_ID": "BOE-A-2004-2", "url_html": "https://x/2/txt.php"},
        ]}

    original = cargador.extraer_publicaciones_2b_api
    cargador.extraer_publicaciones_2b_api = extraer
    try:
        publicaciones, dias = cargador.descubrir("2004-01-01", "2004-01-02", api)
    finally:
        cargador.extraer_publicaciones_2b_api = original
    assert [x["Publicacion_ID"] for x in publicaciones] == ["BOE-A-2004-1", "BOE-A-2004-2"]
    assert publicaciones[0]["titulo"] == "Título" and publicaciones[0]["departamento"] == "Departamento"
    assert len(dias) == 2


def test_paso_metadatos_no_enriquece_convocatorias(monkeypatch):
    original = {"Puesto": "Auxiliar", "Num_plazas": 1, "Administración": "Administración Local",
                "Municipio": "", "Provincia": ""}
    class Respuesta:
        content = b"x"
        def raise_for_status(self): pass
    monkeypatch.setattr(cargador, "extraer_desde_contenido", lambda *args: {
        "clasificacion_documento": "CONVOCATORIA", "convocatorias": [dict(original)]
    })
    _, filas = cargador.procesar_publicacion({"Publicacion_ID": "BOE-A-2004-1", "Enlace": "https://x/txt.php"},
                                              obtener=lambda *args, **kwargs: Respuesta())
    assert filas == [original]


def test_historico_enriquece_con_el_mismo_motor_y_conserva_clasificacion(monkeypatch):
    class Respuesta:
        content = b"x"
        def raise_for_status(self): pass
    original = {"Puesto": "Auxiliar", "Num_plazas": 1, "Administración": "Administración Local",
                "Turno": "--", "Sistema": "--"}
    monkeypatch.setattr(cargador, "extraer_desde_contenido", lambda *args: {
        "clasificacion_documento": "CONVOCATORIA", "convocatorias": [dict(original)]
    })
    clase, filas = cargador.procesar_publicacion({
        "Publicacion_ID": "BOE-A-2004-1", "Enlace": "https://x/txt.php",
        "titulo": "Resolución del Ayuntamiento de Ciudad Real, referente a la convocatoria.",
        "departamento": "Administración Local",
    }, obtener=lambda *args, **kwargs: Respuesta())
    assert clase == "CONVOCATORIA" and len(filas) == 1
    assert (filas[0]["Administración"], filas[0]["Municipio"], filas[0]["Provincia"]) == (
        "Ayuntamiento de Ciudad Real", "Ciudad Real", "Ciudad Real"
    )
    assert (filas[0]["Puesto"], filas[0]["Num_plazas"], filas[0]["Turno"], filas[0]["Sistema"]) == (
        original["Puesto"], original["Num_plazas"], original["Turno"], original["Sistema"]
    )


def test_historico_antiguo_sin_metadatos_no_inventa_administracion(monkeypatch):
    class Respuesta:
        content = b"x"
        def raise_for_status(self): pass
    monkeypatch.setattr(cargador, "extraer_desde_contenido", lambda *args: {
        "clasificacion_documento": "INDETERMINADO",
        "convocatorias": [{"Puesto": "Auxiliar", "Num_plazas": 1, "Administración": "Administración Local"}],
    })
    clase, filas = cargador.procesar_publicacion({"Publicacion_ID": "BOE-A-2004-1", "Enlace": "https://x/txt.php"},
                                                 obtener=lambda *args, **kwargs: Respuesta())
    assert clase == "INDETERMINADO" and filas[0]["Administración"] == "Administración Local"


def test_estado_previo_limite_y_reanudacion_sin_repetir(tmp_path):
    catalogo, llamadas_descubrir, llamadas = _catalogo(), [], []
    ruta = ruta_estado("2004-01-01", "2004-01-31", tmp_path)
    resultados = {x["Publicacion_ID"]: ("CONVOCATORIA", [{"Puesto": "Auxiliar", "Num_plazas": 1}]) for x in catalogo}
    estado, _ = cargador.ejecutar("2004-01-01", "2004-01-31", limite=2, directorio=tmp_path,
        descubrir_fn=_descubrimiento(catalogo, llamadas_descubrir),
        procesar_fn=_procesador(resultados, llamadas, ruta))
    assert llamadas == ["BOE-A-2004-1", "BOE-A-2004-2"]
    assert estado["publicaciones_procesadas"] == 2
    assert llamadas_descubrir == [("2004-01-01", "2004-01-31")]
    estado, _ = cargador.ejecutar("2004-01-01", "2004-01-31", limite=2, directorio=tmp_path,
        descubrir_fn=lambda *_: pytest.fail("no debe redescubrir"),
        procesar_fn=_procesador(resultados, llamadas))
    assert llamadas == ["BOE-A-2004-1", "BOE-A-2004-2", "BOE-A-2004-3", "BOE-A-2004-4"]
    assert estado["publicaciones_procesadas"] == 4


def test_clasificaciones_error_reintento_e_interrupcion(tmp_path):
    catalogo = _catalogo(4)
    resultados = {
        "BOE-A-2004-1": ("CONVOCATORIA", [{"Puesto": "Oficial", "Num_plazas": 2}, {"Puesto": "", "Num_plazas": 4}]),
        "BOE-A-2004-2": ("NO_CONVOCATORIA", []),
        "BOE-A-2004-3": ("INDETERMINADO", []),
        "BOE-A-2004-4": RuntimeError("fallo de red"),
    }
    estado, ruta = cargador.ejecutar("2004-01-01", "2004-01-31", directorio=tmp_path,
        descubrir_fn=_descubrimiento(catalogo), procesar_fn=_procesador(resultados))
    filas = estado["resultados"]
    assert filas["BOE-A-2004-1"]["convocatorias"] == [{"Puesto": "Oficial", "Num_plazas": 2}]
    assert filas["BOE-A-2004-2"]["estado"] == "NO_CONVOCATORIA"
    assert filas["BOE-A-2004-3"]["estado"] == "INDETERMINADO"
    assert filas["BOE-A-2004-4"]["estado"] == "ERROR"
    assert "fallo de red" in filas["BOE-A-2004-4"]["error"]

    reintentos = []
    estado, _ = cargador.ejecutar("2004-01-01", "2004-01-31", directorio=tmp_path, reintentar=True,
        descubrir_fn=lambda *_: pytest.fail("no debe redescubrir"),
        procesar_fn=_procesador({"BOE-A-2004-4": ("NO_CONVOCATORIA", [])}, reintentos))
    assert reintentos == ["BOE-A-2004-4"]
    assert estado["publicaciones_procesadas"] == 4

    interrupcion = _catalogo(2)
    with pytest.raises(KeyboardInterrupt):
        cargador.ejecutar("2004-02-01", "2004-02-01", directorio=tmp_path,
            descubrir_fn=_descubrimiento(interrupcion),
            procesar_fn=_procesador({"BOE-A-2004-1": ("NO_CONVOCATORIA", []),
                                     "BOE-A-2004-2": KeyboardInterrupt()}))
    guardado = cargar_estado(ruta_estado("2004-02-01", "2004-02-01", tmp_path), "2004-02-01", "2004-02-01")
    assert guardado["publicaciones_procesadas"] == 1
    assert guardado["publicaciones_pendientes"] == 1


def test_estado_incompatible_y_guardado_atomico_validado(tmp_path, monkeypatch):
    catalogo = _catalogo(1)
    reemplazos = []
    import procesamiento_historico
    original = procesamiento_historico.os.replace
    monkeypatch.setattr(procesamiento_historico.os, "replace", lambda origen, destino: (reemplazos.append((origen, destino)), original(origen, destino))[1])
    estado, ruta = cargador.ejecutar("2004-01-01", "2004-01-31", directorio=tmp_path,
        descubrir_fn=_descubrimiento(catalogo),
        procesar_fn=_procesador({"BOE-A-2004-1": ("NO_CONVOCATORIA", [])}))
    assert reemplazos
    assert json.loads(ruta.read_text(encoding="utf-8"))["resultados"]
    ruta.write_text(json.dumps({"version_formato": 1, "fecha_inicio": "2004-01-02", "fecha_fin": "2004-01-31"}), encoding="utf-8")
    with pytest.raises(ValueError, match="incompatible"):
        cargador.ejecutar("2004-01-01", "2004-01-31", directorio=tmp_path)


def test_cargador_no_tiene_ruta_de_escritura_excel():
    codigo = Path(cargador.__file__).read_text(encoding="utf-8")
    for prohibido in ("ExcelWriter", "openpyxl"):
        assert prohibido not in codigo
    assert "guardar_excel(" in codigo


def _excel_temporal(tmp_path):
    destino = tmp_path / "prueba.xlsx"
    from publicaciones import COLUMNAS_PUBLICACIONES
    from cobertura import COLUMNAS_COBERTURA
    columnas_oposiciones = ["Num_plazas", "Puesto", "Administración", "Escala", "Subescala", "Clase",
                            "Sistema", "Turno", "Fecha_boe", "Enlace", "Municipio", "Provincia",
                            "Latitud", "Longitud", "Habitantes", "Publicacion_ID", "Version_extractor", "Fecha_analisis"]
    with pd.ExcelWriter(destino, engine="openpyxl") as escritor:
        pd.DataFrame(columns=["Código"]).to_excel(escritor, sheet_name="Búsquedas", index=False)
        pd.DataFrame(columns=columnas_oposiciones).to_excel(escritor, sheet_name="Oposiciones", index=False)
        pd.DataFrame(columns=["Fecha", "Tipo de error", "Enlace Web"]).to_excel(escritor, sheet_name="Log-errores", index=False)
        pd.DataFrame(columns=COLUMNAS_PUBLICACIONES).to_excel(escritor, sheet_name="Publicaciones", index=False)
        pd.DataFrame(columns=COLUMNAS_COBERTURA).to_excel(escritor, sheet_name="Cobertura", index=False)
    return destino


def _estado_aplicable(tmp_path, *, indeterminado=False, error=False, pendiente=False):
    estado = {
        "version_formato": 1, "estado": "EN_PROGRESO", "excel_escrito": False,
        "fecha_inicio": "2004-01-01", "fecha_fin": "2004-01-01",
        "resultados": {
            "BOE-A-2004-1": {"Publicacion_ID": "BOE-A-2004-1", "Fecha_boe": "2004-01-01",
                "Enlace": "https://ejemplo.test/txt.php?id=BOE-A-2004-1", "estado": "CONVOCATORIA",
                "convocatorias": [{"Puesto": "Auxiliar", "Num_plazas": 2, "Administración": "Ayuntamiento de Prueba"}],
                "fecha_analisis": "2026-01-01T00:00:00"},
            "BOE-A-2004-2": {"Publicacion_ID": "BOE-A-2004-2", "Fecha_boe": "2004-01-01",
                "Enlace": "https://ejemplo.test/txt.php?id=BOE-A-2004-2", "estado": "INDETERMINADO" if indeterminado else "NO_CONVOCATORIA",
                "convocatorias": [], "fecha_analisis": "2026-01-01T00:00:00"},
        },
        "indices_diarios": [{"fecha": "2004/01/01", "estado": "CON_PUBLICACIONES", "numero_publicaciones": 2}],
    }
    if error:
        estado["resultados"]["BOE-A-2004-2"]["estado"] = "ERROR"
    if pendiente:
        estado["resultados"]["BOE-A-2004-2"]["estado"] = "PENDIENTE"
    from procesamiento_historico import guardar_estado
    ruta = ruta_estado("2004-01-01", "2004-01-01", tmp_path)
    guardar_estado(ruta, estado)
    return ruta


@pytest.mark.parametrize("opcion", ["pendiente", "error"])
def test_aplicar_rechaza_estado_no_final(tmp_path, opcion):
    _estado_aplicable(tmp_path, **{opcion: True})
    with pytest.raises((RuntimeError, ValueError)):
        cargador.aplicar("2004-01-01", "2004-01-01", excel=_excel_temporal(tmp_path), directorio=tmp_path)


def test_validar_estado_pendiente_informa_que_esta_incompleto():
    estado = {"fecha_inicio": "2008-01-01", "fecha_fin": "2011-12-31",
              "resultados": {"BOE-A-2008-1": {"Publicacion_ID": "BOE-A-2008-1", "estado": "PENDIENTE"}}}
    with pytest.raises(RuntimeError, match="estado histórico está incompleto.*1 publicaciones pendientes"):
        cargador._validar_estado_aplicable(estado, "2008-01-01", "2011-12-31")


def test_validar_estado_error_bloquea_y_completo_es_valido():
    base = {"fecha_inicio": "2004-01-01", "fecha_fin": "2004-01-01",
            "resultados": {"BOE-A-2004-1": {"Publicacion_ID": "BOE-A-2004-1", "estado": "ERROR"}}}
    with pytest.raises(RuntimeError, match="1 publicaciones con ERROR"):
        cargador._validar_estado_aplicable(base, "2004-01-01", "2004-01-01")
    base["resultados"]["BOE-A-2004-1"]["estado"] = "NO_CONVOCATORIA"
    cargador._validar_estado_aplicable(base, "2004-01-01", "2004-01-01")


def test_dry_run_admite_indeterminado_y_no_escribe(tmp_path, monkeypatch):
    _estado_aplicable(tmp_path, indeterminado=True)
    monkeypatch.setattr(cargador, "enriquecer_filas_sin_coordenadas", lambda df: df)
    excel = _excel_temporal(tmp_path); antes = excel.read_bytes()
    resultado = cargador.aplicar("2004-01-01", "2004-01-01", excel=excel, directorio=tmp_path, dry_run=True)
    assert resultado["dry_run"] and resultado["indeterminado"] == 1
    assert resultado["convocatorias_validas"] == 1 and excel.read_bytes() == antes
    assert cargar_estado(ruta_estado("2004-01-01", "2004-01-01", tmp_path), "2004-01-01", "2004-01-01")["estado"] == "EN_PROGRESO"


def test_aplicar_actualiza_hojas_hace_backup_e_idempotente(tmp_path, monkeypatch):
    _estado_aplicable(tmp_path, indeterminado=True)
    monkeypatch.setattr(cargador, "enriquecer_filas_sin_coordenadas", lambda df: df)
    excel = _excel_temporal(tmp_path); llamadas = []
    original = preparar = cargador.preparar_archivo_datos.guardar_excel
    monkeypatch.setattr(cargador.preparar_archivo_datos, "guardar_excel", lambda *a, **k: (llamadas.append(1), original(*a, **k))[1])
    resultado = cargador.aplicar("2004-01-01", "2004-01-01", excel=excel, directorio=tmp_path,
                                 backup_directorio=tmp_path / "backups")
    assert len(llamadas) == 1 and Path(resultado["backup"]).exists()
    hojas = cargador.preparar_archivo_datos.preparar_excel_y_dataframes(excel)
    publicacion = hojas["Publicaciones"].set_index("Publicacion_ID")
    assert publicacion.loc["BOE-A-2004-1", "Estado_analisis"] == "con_coincidencias"
    assert publicacion.loc["BOE-A-2004-2", "Estado_analisis"] == "indeterminado"
    assert len(hojas["Oposiciones"][hojas["Oposiciones"]["Publicacion_ID"] == "BOE-A-2004-1"]) == 1
    assert len(hojas["Cobertura"][hojas["Cobertura"]["Fecha"] == "2004-01-01"]) == 1
    assert cargador.aplicar("2004-01-01", "2004-01-01", excel=excel, directorio=tmp_path,
                            backup_directorio=tmp_path / "backups")["ya_aplicado"]
    assert len(llamadas) == 1


def test_aplicar_descarta_fila_parcial_y_no_completa_si_falla_guardado(tmp_path, monkeypatch):
    _estado_aplicable(tmp_path)
    monkeypatch.setattr(cargador, "enriquecer_filas_sin_coordenadas", lambda df: df)
    ruta = ruta_estado("2004-01-01", "2004-01-01", tmp_path)
    estado = cargar_estado(ruta, "2004-01-01", "2004-01-01")
    estado["resultados"]["BOE-A-2004-1"]["convocatorias"].append({"Puesto": "Incompleto"})
    from procesamiento_historico import guardar_estado
    guardar_estado(ruta, estado)
    monkeypatch.setattr(cargador.preparar_archivo_datos, "guardar_excel", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fallo")))
    with pytest.raises(RuntimeError, match="fallo"):
        cargador.aplicar("2004-01-01", "2004-01-01", excel=_excel_temporal(tmp_path), directorio=tmp_path,
                         backup_directorio=tmp_path / "backups")
    assert cargar_estado(ruta, "2004-01-01", "2004-01-01")["estado"] == "EN_PROGRESO"


def test_geolocalizacion_reutiliza_la_funcion_existente_por_administracion(monkeypatch):
    llamadas = []
    def localizar(df):
        llamadas.append(len(df))
        df = df.copy()
        df["Latitud"] = 1.0
        return df
    monkeypatch.setattr(cargador, "enriquecer_filas_sin_coordenadas", localizar)
    filas = cargador._geolocalizar_nuevas([
        {"Administración": "Entidad", "Puesto": "Uno", "Num_plazas": 1},
        {"Administración": "Entidad", "Puesto": "Dos", "Num_plazas": 1},
    ])
    assert llamadas == [1] and filas["Latitud"].tolist() == [1.0, 1.0]


@pytest.mark.parametrize(("inicio", "mes"), [
    ("2004-01-01", "2004-01"),
    ("2004-02-01", "2004-02"),
    ("2004-03-01", "2004-03"),
])
def test_nombre_backup_deriva_el_mes_de_inicio_del_intervalo(inicio, mes):
    nombre = cargador._nombre_backup(inicio)
    assert f"pre_commit_{mes}_" in nombre


@pytest.mark.parametrize(("clasificacion", "convocatorias", "esperado"), [
    ("CONVOCATORIA", [{"Puesto": "Auxiliar", "Num_plazas": 1}], ("con_coincidencias", 1)),
    ("CONVOCATORIA", [], ("indeterminado", 0)),
    ("NO_CONVOCATORIA", [], ("sin_coincidencias", 0)),
    ("INDETERMINADO", [], ("indeterminado", 0)),
])
def test_semantica_historica_se_basa_en_filas_validas(clasificacion, convocatorias, esperado):
    estado, coincidencias, _ = cargador._semantica_publicacion_historica(
        {"estado": clasificacion, "convocatorias": convocatorias})
    assert (estado, coincidencias) == esperado


def test_plan_distingue_deduplicacion_legitima_de_inconsistencia(tmp_path, monkeypatch):
    excel = _excel_temporal(tmp_path)
    datos = cargador.preparar_archivo_datos.preparar_excel_y_dataframes(excel)
    datos["Publicaciones"] = pd.DataFrame([
        {"Publicacion_ID": "BOE-A-2004-1", "Enlace": "u1", "Fecha_BOE": "2004-01-01", "Titulo_original": "",
         "Fecha_ultimo_analisis": "", "Version_extractor": "historico-experimental-2004", "Estado_analisis": "con_coincidencias", "Coincidencias": 2},
        {"Publicacion_ID": "BOE-A-2004-2", "Enlace": "u2", "Fecha_BOE": "2004-01-01", "Titulo_original": "",
         "Fecha_ultimo_analisis": "", "Version_extractor": "historico-experimental-2004", "Estado_analisis": "con_coincidencias", "Coincidencias": 3},
    ])
    datos["Oposiciones"] = pd.DataFrame([{"Publicacion_ID": "BOE-A-2004-1"}, {"Publicacion_ID": "BOE-A-2004-2"}])
    monkeypatch.setattr(cargador.preparar_archivo_datos, "preparar_excel_y_dataframes", lambda _: datos)
    monkeypatch.setattr(cargador, "_estados_historicos_2004", lambda _: {
        "BOE-A-2004-1": {"estado": "CONVOCATORIA", "convocatorias": [{"Puesto": "A", "Num_plazas": 1}, {"Puesto": "B", "Num_plazas": 1}]},
        "BOE-A-2004-2": {"estado": "CONVOCATORIA", "convocatorias": [{"Puesto": "A", "Num_plazas": 1}]},
    })
    plan = cargador.plan_correccion_publicaciones_2004(excel, tmp_path)
    assert [x["tipo"] for x in plan["diferencias"]] == ["DIFERENCIA_POR_DEDUPLICACION", "INCONSISTENCIA_REAL"]


def test_migracion_dry_run_no_escribe_y_no_toca_hojas(tmp_path, monkeypatch):
    excel = _excel_temporal(tmp_path); antes = excel.read_bytes()
    plan = {"datos": {}, "cambios": [{"desde_estado": "con_coincidencias", "a_estado": "indeterminado"}],
            "origenes": {"CONVOCATORIA_SIN_VALIDAS": 1}, "transiciones": {"con_coincidencias → indeterminado": 1},
            "diferencias": []}
    monkeypatch.setattr(cargador, "plan_correccion_publicaciones_2004", lambda *a, **k: plan)
    resultado = cargador.corregir_publicaciones_2004(excel=excel, directorio=tmp_path, dry_run=True)
    assert resultado["cambios"] == 1 and excel.read_bytes() == antes


class _ProgresoPrueba:
    def __init__(self, total, contadores, stream):
        self.total, self.contadores, self.actualizaciones, self.cerrado = total, contadores, 0, False
    def actualizar(self): self.actualizaciones += 1
    def cerrar(self): self.cerrado = True


def test_progreso_usa_total_del_limite_y_no_altera_estado(tmp_path):
    catalogo = _catalogo(3); creados = []
    estado, _ = cargador.ejecutar("2004-01-01", "2004-01-01", limite=2, directorio=tmp_path,
        descubrir_fn=_descubrimiento(catalogo),
        procesar_fn=_procesador({x["Publicacion_ID"]: ("NO_CONVOCATORIA", []) for x in catalogo}),
        progreso_factory=lambda *args: creados.append(_ProgresoPrueba(*args)) or creados[-1], stream=StringIO())
    assert creados[0].total == 2 and creados[0].actualizaciones == 2 and creados[0].cerrado
    assert estado["publicaciones_procesadas"] == 2


def test_progreso_reanudacion_y_reintento_usa_solo_errores(tmp_path):
    catalogo = _catalogo(2); fabrica = []
    cargador.ejecutar("2004-01-01", "2004-01-01", directorio=tmp_path,
        descubrir_fn=_descubrimiento(catalogo),
        procesar_fn=_procesador({"BOE-A-2004-1": RuntimeError("x"), "BOE-A-2004-2": ("NO_CONVOCATORIA", [])}),
        progreso_factory=lambda *a: fabrica.append(_ProgresoPrueba(*a)) or fabrica[-1], stream=StringIO())
    salida = StringIO()
    cargador.ejecutar("2004-01-01", "2004-01-01", directorio=tmp_path, reintentar=True,
        descubrir_fn=lambda *_: pytest.fail("no redescubrir"),
        procesar_fn=_procesador({"BOE-A-2004-1": ("NO_CONVOCATORIA", [])}),
        progreso_factory=lambda *a: fabrica.append(_ProgresoPrueba(*a)) or fabrica[-1], stream=salida)
    assert fabrica[-1].total == 1 and "Estado existente:" in salida.getvalue()


def test_progreso_no_tty_eta_segura_e_interrupcion(tmp_path):
    salida = StringIO(); progreso = cargador.ProgresoDocumental(2, {"ERROR": 0, "INDETERMINADO": 0}, salida)
    progreso.actualizar(); progreso.cerrar()
    assert "ETA calculando" in salida.getvalue() and "\x1b" not in salida.getvalue()
    with pytest.raises(KeyboardInterrupt):
        cargador.ejecutar("2004-02-01", "2004-02-01", directorio=tmp_path,
            descubrir_fn=_descubrimiento(_catalogo(1)),
            procesar_fn=_procesador({"BOE-A-2004-1": KeyboardInterrupt()}), stream=salida)
    assert "Procesamiento interrumpido." in salida.getvalue()
