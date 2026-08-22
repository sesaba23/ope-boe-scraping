import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pandas as pd
import pytest
import requests

import coincidencias
import preparar_archivo_datos
import reprocesamiento_legacy
from reprocesamiento_legacy import (
    CAMPOS_CONVOCATORIA,
    BackupInvalidoError,
    ReprocesamientoNoSeguroError,
    aplicar_lote,
    asignar_acciones,
    calcular_integridad_excel,
    comparar_convocatorias,
    crear_backup_verificado,
    ejecutar_dry_run,
    guardar_informe_auditoria,
    preparar_aplicacion,
    seleccionar_publicaciones,
)


def _fila(**cambios):
    fila = {
        "Puesto": "Auxiliar",
        "Fecha_boe": "1 de enero de 2025",
        "Administración": "Ayuntamiento de Prueba",
        "Enlace": "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2025-1",
        "Num_plazas": 2,
        "Turno": "Libre",
        "Sistema": "Oposición",
        "Escala": "General",
        "Subescala": "Auxiliar",
        "Clase": "Administrativa",
        "Publicacion_ID": "BOE-A-2025-1",
        "Version_extractor": "legacy",
        "Fecha_analisis": pd.NA,
    }
    fila.update(cambios)
    return fila


def _publicaciones():
    return pd.DataFrame(
        [
            {
                "Publicacion_ID": "BOE-A-2024-1",
                "Enlace": "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2024-1",
                "Fecha_BOE": "1 de enero de 2024",
                "Version_extractor": "legacy",
            },
            {
                "Publicacion_ID": "BOE-A-2025-1",
                "Enlace": "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2025-1",
                "Fecha_BOE": "1 de enero de 2025",
                "Version_extractor": "legacy",
            },
            {
                "Publicacion_ID": "BOE-A-2025-2",
                "Enlace": "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2025-2",
                "Fecha_BOE": "2 de enero de 2025",
                "Version_extractor": "1",
            },
        ]
    )


def _crear_excel(ruta, publicaciones=None, oposiciones=None):
    with pd.ExcelWriter(ruta) as writer:
        (publicaciones if publicaciones is not None else _publicaciones()).to_excel(
            writer, sheet_name="Publicaciones", index=False
        )
        (oposiciones if oposiciones is not None else pd.DataFrame([_fila()])).to_excel(
            writer, sheet_name="Oposiciones", index=False
        )
        pd.DataFrame({"Código": []}).to_excel(
            writer, sheet_name="Búsquedas", index=False
        )
        pd.DataFrame(
            columns=["Fecha", "Tipo de error", "Enlace Web"]
        ).to_excel(writer, sheet_name="Log-errores", index=False)
        pd.DataFrame(
            {
                "Fecha": ["2025-01-01"],
                "Estado": ["consultado"],
                "Version_extractor": ["1"],
                "Fecha_ultima_consulta": ["2025-01-02 10:00:00"],
                "Numero_publicaciones": [1],
            }
        ).to_excel(writer, sheet_name="Cobertura", index=False)


def _detalle(clasificacion, historicas=None, actuales=None, error=None):
    historicas = historicas if historicas is not None else [_fila()]
    actuales = actuales if actuales is not None else [_fila()]
    comparacion = comparar_convocatorias(historicas, actuales)
    comparacion["clasificacion"] = clasificacion
    detalle = {
        "Publicacion_ID": "BOE-A-2025-1",
        "Fecha_BOE": "1 de enero de 2025",
        "Enlace": _fila()["Enlace"],
        "Version_anterior": "legacy",
        "Version_actual": "1",
        "filas_historicas": len(historicas),
        "filas_nuevas": len(actuales),
        **comparacion,
    }
    if error:
        detalle.update(tipo_error="HTTPError", error=error)
    return detalle


def _resumen(detalles):
    resultado = {clave: 0 for clave in reprocesamiento_legacy.CLASIFICACIONES}
    for detalle in detalles:
        resultado[detalle["clasificacion"]] += 1
    resultado.update(
        {
            "Publicaciones analizadas": len(detalles),
            "filas históricas": sum(d["filas_historicas"] for d in detalles),
            "filas obtenidas actualmente": sum(d["filas_nuevas"] for d in detalles),
            "filas añadidas": sum(len(d["filas_añadidas"]) for d in detalles),
            "filas ausentes": sum(len(d["filas_ausentes"]) for d in detalles),
        }
    )
    return resultado


def test_comparacion_identica():
    resultado = comparar_convocatorias([_fila()], [_fila()])
    assert resultado["clasificacion"] == "SIN_CAMBIOS"


def test_comparacion_ampliada():
    resultado = comparar_convocatorias(
        [_fila()], [_fila(), _fila(Puesto="Administrativo")]
    )
    assert resultado["clasificacion"] == "AMPLIADA"
    assert len(resultado["filas_añadidas"]) == 1


def test_comparacion_reducida():
    resultado = comparar_convocatorias(
        [_fila(), _fila(Puesto="Administrativo")], [_fila()]
    )
    assert resultado["clasificacion"] == "REDUCIDA"
    assert len(resultado["filas_ausentes"]) == 1


def test_comparacion_modificada_detalla_campos():
    resultado = comparar_convocatorias([_fila()], [_fila(Num_plazas=20)])
    assert resultado["clasificacion"] == "MODIFICADA"
    assert resultado["campos_modificados"][0]["cambios"]["Num_plazas"] == {
        "anterior": 2,
        "nuevo": 20,
    }


def test_historico_con_extraccion_vacia():
    resultado = comparar_convocatorias([_fila()], [])
    assert resultado["clasificacion"] == "SIN_RESULTADOS_NUEVOS"


def test_comparacion_ignora_trazabilidad():
    nueva = _fila(Version_extractor="1", Fecha_analisis="2026-01-01 10:00:00")
    assert comparar_convocatorias([_fila()], [nueva])["clasificacion"] == "SIN_CAMBIOS"
    assert set(CAMPOS_CONVOCATORIA).isdisjoint(
        {"Version_extractor", "Fecha_analisis"}
    )


def test_seleccion_versiones_fechas_limite_e_identificador():
    publicaciones = _publicaciones()
    seleccion = seleccionar_publicaciones(
        publicaciones,
        desde="2025-01-01",
        hasta="2025-12-31",
        publicacion_id="BOE-A-2025-1",
        limite=1,
    )
    assert seleccion["Publicacion_ID"].tolist() == ["BOE-A-2025-1"]
    assert "BOE-A-2025-2" not in seleccion["Publicacion_ID"].tolist()
    assert len(seleccionar_publicaciones(publicaciones, limite=1)) == 1


def test_error_http_se_clasifica_como_error_y_una_fila_solo_descarga_una_vez(
    tmp_path,
):
    ruta = tmp_path / "datos.xlsx"
    _crear_excel(ruta)
    llamadas = []

    def fallo(url, timeout):
        llamadas.append(url)
        raise requests.exceptions.HTTPError("500")

    detalles, resumen = ejecutar_dry_run(
        ruta, publicacion_id="BOE-A-2025-1", obtener=fallo
    )
    assert detalles[0]["clasificacion"] == "ERROR"
    assert resumen["ERROR"] == 1
    assert llamadas == [
        "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2025-1"
    ]
    assert all("index.php" not in url for url in llamadas)


def test_varias_filas_historicas_generan_una_descarga_y_no_consultan_indice(
    monkeypatch, tmp_path
):
    ruta = tmp_path / "datos.xlsx"
    oposiciones = pd.DataFrame([_fila(), _fila(Puesto="Administrativo")])
    _crear_excel(ruta, _publicaciones().iloc[[1]], oposiciones)
    llamadas = []

    class Respuesta:
        content = b'''<div class="documento-tit">Titulo</div>
        <div class="metadatos">1 de enero de 2025</div>
        <div id="textoxslt">Contenido</div>'''

        def raise_for_status(self):
            return None

    def obtener(url, timeout):
        llamadas.append(url)
        assert "index.php" not in url
        return Respuesta()

    monkeypatch.setattr(
        coincidencias,
        "extraer_convocatorias_local",
        lambda *args: [_fila(), _fila(Puesto="Administrativo")],
    )
    detalles, _ = ejecutar_dry_run(ruta, obtener=obtener)
    assert len(llamadas) == 1
    assert detalles[0]["filas_historicas"] == 2
    assert detalles[0]["clasificacion"] == "SIN_CAMBIOS"


def test_dry_run_no_modifica_excel_ni_llama_guardar(monkeypatch, tmp_path):
    ruta = tmp_path / "datos.xlsx"
    _crear_excel(ruta, _publicaciones().iloc[[1]])
    antes = (hashlib.sha256(ruta.read_bytes()).hexdigest(), ruta.stat().st_size, ruta.stat().st_mtime_ns)

    class Respuesta:
        content = b'''<div class="documento-tit">Titulo</div>
        <div class="metadatos">1 de enero de 2025</div>
        <div id="textoxslt">Contenido</div>'''

        def raise_for_status(self):
            return None

    monkeypatch.setattr(coincidencias, "extraer_convocatorias_local", lambda *args: [_fila()])
    monkeypatch.setattr(
        preparar_archivo_datos,
        "guardar_excel",
        lambda *args: pytest.fail("guardar_excel no debe ejecutarse"),
    )
    ejecutar_dry_run(ruta, obtener=lambda *args, **kwargs: Respuesta())
    despues = (hashlib.sha256(ruta.read_bytes()).hexdigest(), ruta.stat().st_size, ruta.stat().st_mtime_ns)
    assert despues == antes


def test_main_legacy_sin_dry_run_es_rechazado(monkeypatch, capsys):
    import plazasboe

    monkeypatch.setattr(sys, "argv", ["plazasboe.py", "--reprocesar-legacy"])
    monkeypatch.setattr(
        preparar_archivo_datos,
        "guardar_excel",
        lambda *args: pytest.fail("guardar_excel no debe ejecutarse"),
    )
    with pytest.raises(SystemExit) as salida:
        plazasboe.main()
    assert salida.value.code == 2
    assert "--dry-run o --aplicar" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argumentos,mensaje",
    [
        (["--reprocesar-legacy", "--aplicar"], "--aplicar exige --limite"),
        (
            ["--reprocesar-legacy", "--aplicar", "--limite", "26"],
            "máximo --limite 25",
        ),
        (
            ["--reprocesar-legacy", "--dry-run", "--aplicar", "--limite", "1"],
            "not allowed",
        ),
    ],
)
def test_argumentos_de_aplicacion_inseguros_se_rechazan(
    monkeypatch, capsys, argumentos, mensaje
):
    import plazasboe

    monkeypatch.setattr(sys, "argv", ["plazasboe.py", *argumentos])
    with pytest.raises(SystemExit) as salida:
        plazasboe.main()
    assert salida.value.code == 2
    assert mensaje in capsys.readouterr().err


def test_main_dry_run_no_entra_en_flujo_normal(monkeypatch):
    import plazasboe

    monkeypatch.setattr(
        plazasboe,
        "obtener_sumario_api",
        lambda *args, **kwargs: pytest.fail(
            "El reprocesamiento legacy no debe consultar la API"
        ),
    )

    monkeypatch.setattr(
        reprocesamiento_legacy,
        "ejecutar_dry_run",
        lambda **kwargs: ([], {clave: 0 for clave in [
            "Publicaciones analizadas",
            *reprocesamiento_legacy.CLASIFICACIONES,
            "filas históricas",
            "filas obtenidas actualmente",
            "filas añadidas",
            "filas ausentes",
        ]}),
    )
    monkeypatch.setattr(
        preparar_archivo_datos,
        "preparar_excel_y_dataframes",
        lambda: pytest.fail("No debe entrar en el scraper"),
    )
    monkeypatch.setattr(
        preparar_archivo_datos,
        "guardar_excel",
        lambda *args: pytest.fail("guardar_excel no debe ejecutarse"),
    )
    monkeypatch.setattr(
        reprocesamiento_legacy,
        "calcular_integridad_excel",
        lambda: {"sha256": "x", "tamano": 1, "mtime_ns": 2},
    )
    monkeypatch.setattr(
        reprocesamiento_legacy,
        "guardar_informe_auditoria",
        lambda *args: "informe.json",
    )
    monkeypatch.setattr(
        sys, "argv", ["plazasboe.py", "--reprocesar-legacy", "--dry-run"]
    )
    plazasboe.main()


def test_informe_json_contiene_esquema_detalles_unicode_y_clave_funcional(tmp_path):
    añadida = _fila(Puesto="Técnico/a de gestión pública")
    detalles = [_detalle("AMPLIADA", [_fila()], [_fila(), añadida])]
    integridad = {"sha256": "abc", "tamano": 123, "mtime_ns": 456}

    ruta = guardar_informe_auditoria(
        detalles,
        _resumen(detalles),
        {"desde": "2025-01-01", "puesto": "gestión"},
        integridad,
        integridad,
        directorio=tmp_path,
    )
    datos = json.loads(ruta.read_text(encoding="utf-8"))

    assert datos["modo"] == "dry-run"
    assert datos["version_extractor"] == "1"
    assert datos["total_publicaciones"] == 1
    assert datos["AMPLIADA"] == 1
    assert datos["excel_modificado"] is False
    assert datos["filtros_utilizados"]["puesto"] == "gestión"
    publicacion = datos["publicaciones"][0]
    assert publicacion["Publicacion_ID"] == "BOE-A-2025-1"
    assert publicacion["Version_anterior"] == "legacy"
    assert publicacion["Version_actual"] == "1"
    assert publicacion["filas_anadidas"][0]["Puesto"] == "Técnico/a de gestión pública"
    for coleccion in ("filas_historicas", "filas_actuales", "filas_anadidas"):
        assert all(set(fila) == set(CAMPOS_CONVOCATORIA) for fila in publicacion[coleccion])
    assert "Técnico/a de gestión pública" in ruta.read_text(encoding="utf-8")
    assert "Técnico/a de gesti\\u00f3n" not in ruta.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "clasificacion,historicas,actuales",
    [
        ("SIN_CAMBIOS", [_fila()], [_fila()]),
        ("AMPLIADA", [_fila()], [_fila(), _fila(Puesto="Otro")]),
        ("REDUCIDA", [_fila(), _fila(Puesto="Otro")], [_fila()]),
        ("MODIFICADA", [_fila()], [_fila(Num_plazas=20)]),
        ("SIN_RESULTADOS_NUEVOS", [_fila()], []),
    ],
)
def test_informe_conserva_todas_las_clasificaciones_y_diferencias(
    tmp_path, clasificacion, historicas, actuales
):
    detalle = _detalle(clasificacion, historicas, actuales)
    integridad = {"sha256": "abc", "tamano": 1, "mtime_ns": 2}
    ruta = guardar_informe_auditoria(
        [detalle], _resumen([detalle]), {}, integridad, integridad, tmp_path
    )
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    guardado = datos["publicaciones"][0]

    assert datos[clasificacion] == 1
    assert guardado["clasificacion"] == clasificacion
    assert guardado["filas_historicas"] == detalle["filas_historicas_funcionales"]
    assert guardado["filas_actuales"] == detalle["filas_nuevas_funcionales"]
    assert guardado["filas_anadidas"] == detalle["filas_añadidas"]
    assert guardado["filas_ausentes"] == detalle["filas_ausentes"]
    assert guardado["campos_modificados"] == detalle["campos_modificados"]


def test_informe_error_guarda_tipo_y_mensaje_sin_traceback(tmp_path):
    detalle = _detalle("ERROR", [_fila()], [], "500 del servidor")
    integridad = {"sha256": "abc", "tamano": 1, "mtime_ns": 2}
    ruta = guardar_informe_auditoria(
        [detalle], _resumen([detalle]), {}, integridad, integridad, tmp_path
    )
    guardado = json.loads(ruta.read_text(encoding="utf-8"))["publicaciones"][0]

    assert guardado["tipo_error"] == "HTTPError"
    assert guardado["mensaje"] == "500 del servidor"
    assert "traceback" not in guardado


def test_informe_usa_replace_atomico_y_nombres_unicos(monkeypatch, tmp_path):
    detalle = _detalle("SIN_CAMBIOS")
    integridad = {"sha256": "abc", "tamano": 1, "mtime_ns": 2}
    reemplazos = []
    replace_original = reprocesamiento_legacy.os.replace

    def replace_registrado(origen, destino):
        reemplazos.append((origen, destino))
        replace_original(origen, destino)

    monkeypatch.setattr(reprocesamiento_legacy.os, "replace", replace_registrado)
    momento = reprocesamiento_legacy.datetime(2026, 8, 22, 12, 30, 45)
    primera = guardar_informe_auditoria(
        [detalle], _resumen([detalle]), {}, integridad, integridad, tmp_path, momento
    )
    segunda = guardar_informe_auditoria(
        [detalle], _resumen([detalle]), {}, integridad, integridad, tmp_path, momento
    )

    assert primera.name == "reprocesamiento_legacy_20260822_123045.json"
    assert segunda.name == "reprocesamiento_legacy_20260822_123045_1.json"
    assert primera != segunda
    assert len(reemplazos) == 2
    assert all(Path(origen).suffix == ".tmp" for origen, _ in reemplazos)
    assert not list(tmp_path.glob("*.tmp"))


def test_integridad_excel_y_anomalia_quedan_registradas(tmp_path):
    ruta_excel = tmp_path / "datos.xlsx"
    _crear_excel(ruta_excel, _publicaciones().iloc[[1]])
    antes = calcular_integridad_excel(ruta_excel)
    despues = dict(antes, tamano=antes["tamano"] + 1)
    detalle = _detalle("SIN_CAMBIOS")

    ruta = guardar_informe_auditoria(
        [detalle], _resumen([detalle]), {}, antes, despues, tmp_path / "logs"
    )
    datos = json.loads(ruta.read_text(encoding="utf-8"))

    assert datos["excel_sha256_antes"] == antes["sha256"]
    assert datos["excel_tamano_despues"] == despues["tamano"]
    assert datos["excel_modificado"] is True
    assert "anomalia_integridad" in datos


def test_resumen_de_consola_conserva_totales(capsys):
    detalle = _detalle("SIN_CAMBIOS")
    reprocesamiento_legacy.imprimir_informe([detalle], _resumen([detalle]))

    salida = capsys.readouterr().out
    assert "filas históricas: 1" in salida
    assert "filas obtenidas actualmente: 1" in salida
    assert "filas añadidas: 0" in salida
    assert "filas ausentes: 0" in salida


def test_resumen_dry_run_se_identifica_como_simulacion(capsys):
    detalle = _detalle("SIN_CAMBIOS")

    reprocesamiento_legacy.imprimir_informe(
        [detalle], _resumen([detalle]), modo="dry-run"
    )

    salida = capsys.readouterr().out
    assert "Resumen del reprocesamiento legacy (simulación)" in salida
    assert "APLICADO" not in salida
    assert "Escritura completada correctamente" not in salida


def test_resumen_aplicado_muestra_metricas_y_verificacion(capsys):
    detalle = _detalle("AMPLIADA", [_fila()], [_fila(), _fila(Puesto="Otro")])
    datos_escritura = {
        "backup": "backups/copia.xlsx",
        "publicaciones_actualizadas": 1,
        "filas_anadidas_realmente": 1,
        "filas_actualizadas_trazabilidad": 1,
    }

    reprocesamiento_legacy.imprimir_informe(
        [detalle],
        _resumen([detalle]),
        modo="aplicar",
        datos_escritura=datos_escritura,
    )

    salida = capsys.readouterr().out
    assert "Resumen del reprocesamiento legacy (APLICADO)" in salida
    assert "Backup creado: backups/copia.xlsx" in salida
    assert "Publicaciones actualizadas: 1" in salida
    assert "Filas añadidas realmente: 1" in salida
    assert "Filas con trazabilidad actualizada: 1" in salida
    assert "Escritura completada correctamente." in salida
    assert "Verificación posterior: correcta." in salida


def _hojas_aplicacion():
    return {
        "Oposiciones": pd.DataFrame([_fila()]),
        "Publicaciones": _publicaciones().iloc[[1]].copy(),
        "Búsquedas": pd.DataFrame({"Código": ["codigo-original"]}),
        "Cobertura": pd.DataFrame(
            {
                "Fecha": ["2025-01-01"],
                "Estado": ["consultado"],
                "Version_extractor": ["1"],
                "Fecha_ultima_consulta": ["2025-01-02 10:00:00"],
                "Numero_publicaciones": [1],
            }
        ),
        "Log-errores": pd.DataFrame(
            columns=["Fecha", "Tipo de error", "Enlace Web"]
        ),
    }


def test_lote_sin_cambios_actualiza_unicamente_trazabilidad():
    hojas = _hojas_aplicacion()
    original = hojas["Oposiciones"].copy(deep=True)
    detalle = _detalle("SIN_CAMBIOS")

    preparados, metricas = preparar_aplicacion(
        [detalle], hojas, reprocesamiento_legacy.datetime(2026, 8, 22, 15, 0, 0)
    )

    assert detalle["accion"] == "ACTUALIZAR_TRAZABILIDAD"
    assert len(preparados["Oposiciones"]) == 1
    for campo in CAMPOS_CONVOCATORIA:
        assert preparados["Oposiciones"].loc[0, campo] == original.loc[0, campo]
    assert preparados["Oposiciones"].loc[0, "Version_extractor"] == "1"
    assert preparados["Oposiciones"].loc[0, "Fecha_analisis"] == "2026-08-22 15:00:00"
    assert metricas == {
        "filas_anadidas_realmente": 0,
        "filas_actualizadas_trazabilidad": 1,
        "publicaciones_actualizadas": 1,
        "fecha_analisis": "2026-08-22 15:00:00",
    }
    publicacion = preparados["Publicaciones"].iloc[0]
    assert str(publicacion["Version_extractor"]) == "1"
    assert publicacion["Fecha_ultimo_analisis"] == "2026-08-22 15:00:00"
    assert publicacion["Estado_analisis"] == "con_coincidencias"
    assert publicacion["Coincidencias"] == 1


def test_lote_ampliado_conserva_historico_geolocaliza_y_no_duplica(monkeypatch):
    hojas = _hojas_aplicacion()
    añadida = _fila(
        Puesto="Administrativo",
        Administración="Ayuntamiento de Prueba geográfica",
    )
    detalle = _detalle("AMPLIADA", [_fila()], [_fila(), añadida])
    llamadas = []

    def enriquecer(df):
        llamadas.append(df.copy())
        resultado = df.copy()
        resultado["Municipio"] = "Prueba"
        resultado["Provincia"] = "Provincia"
        resultado["Latitud"] = 1.0
        resultado["Longitud"] = 2.0
        resultado["Habitantes"] = 3
        return resultado

    monkeypatch.setattr(
        reprocesamiento_legacy, "enriquecer_filas_sin_coordenadas", enriquecer
    )
    preparados, metricas = preparar_aplicacion([detalle], hojas)

    assert detalle["accion"] == "AÑADIR_Y_ACTUALIZAR"
    assert len(preparados["Oposiciones"]) == 2
    assert preparados["Oposiciones"].iloc[0]["Puesto"] == "Auxiliar"
    nueva = preparados["Oposiciones"].iloc[1]
    assert nueva["Puesto"] == "Administrativo"
    assert nueva["Municipio"] == "Prueba"
    assert nueva["Version_extractor"] == "1"
    assert nueva["Fecha_analisis"] == preparados["Oposiciones"].iloc[0]["Fecha_analisis"]
    assert metricas["filas_anadidas_realmente"] == 1
    assert len(llamadas) == 1
    assert not preparados["Oposiciones"].duplicated(CAMPOS_CONVOCATORIA).any()


def test_geolocalizacion_fallida_no_aborta(monkeypatch):
    añadida = _fila(Puesto="Administrativo")
    detalle = _detalle("AMPLIADA", [_fila()], [_fila(), añadida])
    monkeypatch.setattr(
        reprocesamiento_legacy,
        "enriquecer_filas_sin_coordenadas",
        lambda df: df,
    )

    preparados, _ = preparar_aplicacion([detalle], _hojas_aplicacion())

    assert len(preparados["Oposiciones"]) == 2
    assert pd.isna(preparados["Oposiciones"].iloc[1].get("Latitud", pd.NA))


def test_lote_mixto_comparte_fecha_por_publicacion():
    hojas = _hojas_aplicacion()
    segunda = _fila(
        Publicacion_ID="BOE-A-2025-3",
        Enlace="https://www.boe.es/diario_boe/txt.php?id=BOE-A-2025-3",
        Puesto="Técnico",
    )
    hojas["Oposiciones"] = pd.concat(
        [hojas["Oposiciones"], pd.DataFrame([segunda])], ignore_index=True
    )
    hojas["Publicaciones"] = pd.concat(
        [
            hojas["Publicaciones"],
            pd.DataFrame(
                [
                    {
                        "Publicacion_ID": "BOE-A-2025-3",
                        "Enlace": segunda["Enlace"],
                        "Fecha_BOE": segunda["Fecha_boe"],
                        "Version_extractor": "legacy",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    añadida = dict(segunda, Puesto="Arquitecto")
    detalles = [
        _detalle("SIN_CAMBIOS"),
        {
            **_detalle("AMPLIADA", [segunda], [segunda, añadida]),
            "Publicacion_ID": "BOE-A-2025-3",
            "Enlace": segunda["Enlace"],
        },
    ]

    preparados, metricas = preparar_aplicacion(
        detalles, hojas, reprocesamiento_legacy.datetime(2026, 8, 22, 16, 0, 0)
    )

    assert metricas["publicaciones_actualizadas"] == 2
    for publicacion_id in ("BOE-A-2025-1", "BOE-A-2025-3"):
        fechas = preparados["Oposiciones"].loc[
            preparados["Oposiciones"]["Publicacion_ID"] == publicacion_id,
            "Fecha_analisis",
        ]
        assert fechas.nunique() == 1
        assert fechas.iloc[0] == "2026-08-22 16:00:00"


@pytest.mark.parametrize(
    "clasificacion",
    ["REDUCIDA", "MODIFICADA", "SIN_RESULTADOS_NUEVOS", "ERROR"],
)
def test_clasificacion_no_segura_impide_preparar_cualquier_escritura(clasificacion):
    detalle = _detalle(
        clasificacion,
        [_fila()],
        [] if clasificacion in {"SIN_RESULTADOS_NUEVOS", "ERROR"} else [_fila(Num_plazas=3)],
        "error" if clasificacion == "ERROR" else None,
    )

    assert asignar_acciones([detalle]) is False
    assert detalle["accion"] == "NO_ESCRIBIR"
    with pytest.raises(ReprocesamientoNoSeguroError):
        preparar_aplicacion([detalle], _hojas_aplicacion())


def test_backup_verificado_es_identico_y_tiene_nombre_unico(tmp_path):
    original = tmp_path / "BOE-oposiciones.xlsx"
    _crear_excel(original, _publicaciones().iloc[[1]])
    momento = reprocesamiento_legacy.datetime(2026, 8, 22, 17, 0, 0)

    backup, integridad = crear_backup_verificado(
        original, tmp_path / "backups", momento
    )

    assert backup.name == "BOE-oposiciones_20260822_170000.xlsx"
    assert backup.read_bytes() == original.read_bytes()
    assert integridad["sha256"] == calcular_integridad_excel(original)["sha256"]


def test_backup_invalido_aborta_antes_de_aplicar(monkeypatch, tmp_path):
    original = tmp_path / "BOE-oposiciones.xlsx"
    _crear_excel(original, _publicaciones().iloc[[1]])

    def copia_corrupta(origen, destino):
        Path(destino).write_bytes(b"corrupto")

    monkeypatch.setattr(reprocesamiento_legacy.shutil, "copy2", copia_corrupta)
    with pytest.raises(BackupInvalidoError):
        crear_backup_verificado(original, tmp_path / "backups")
    assert pd.read_excel(original, sheet_name="Oposiciones").iloc[0]["Puesto"] == "Auxiliar"


def test_aplicar_lote_usa_un_solo_guardado_y_preserva_busquedas_cobertura(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    ruta = tmp_path / "BOE-oposiciones.xlsx"
    _crear_excel(ruta, _publicaciones().iloc[[1]])
    antes = pd.read_excel(ruta, sheet_name=None)
    llamadas = []
    guardar_real = preparar_archivo_datos.guardar_excel

    def guardar_contado(*args):
        llamadas.append(args)
        guardar_real(*args)

    monkeypatch.setattr(preparar_archivo_datos, "guardar_excel", guardar_contado)
    metricas = aplicar_lote([_detalle("SIN_CAMBIOS")])
    despues = pd.read_excel(ruta, sheet_name=None)

    assert metricas["publicaciones_actualizadas"] == 1
    assert len(llamadas) == 1
    pd.testing.assert_frame_equal(despues["Búsquedas"], antes["Búsquedas"])
    pd.testing.assert_frame_equal(despues["Cobertura"], antes["Cobertura"])
    assert len(despues["Oposiciones"]) == len(antes["Oposiciones"])
    assert seleccionar_publicaciones(despues["Publicaciones"]).empty


def test_fallo_antes_de_replace_conserva_original_y_backup(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    ruta = tmp_path / "BOE-oposiciones.xlsx"
    _crear_excel(ruta, _publicaciones().iloc[[1]])
    original = ruta.read_bytes()
    backup, _ = crear_backup_verificado(ruta, tmp_path / "backups")
    monkeypatch.setattr(
        preparar_archivo_datos,
        "formatear_hoja_oposiciones",
        lambda *args: (_ for _ in ()).throw(RuntimeError("fallo previo a replace")),
    )

    with pytest.raises(RuntimeError, match="fallo previo a replace"):
        aplicar_lote([_detalle("SIN_CAMBIOS")])

    assert ruta.read_bytes() == original
    assert backup.exists()


def test_json_de_aplicacion_refleja_acciones_y_resultado(tmp_path):
    detalle = _detalle("AMPLIADA", [_fila()], [_fila(), _fila(Puesto="Otro")])
    assert asignar_acciones([detalle]) is True
    integridad = {"sha256": "a", "tamano": 1, "mtime_ns": 2}
    datos_escritura = {
        "escritura_autorizada": True,
        "backup": "backup.xlsx",
        "backup_sha256": "a",
        "filas_anadidas_realmente": 1,
        "filas_actualizadas_trazabilidad": 1,
        "publicaciones_actualizadas": 1,
        "escritura_completada": True,
    }

    ruta = guardar_informe_auditoria(
        [detalle],
        _resumen([detalle]),
        {},
        integridad,
        dict(integridad, sha256="b"),
        tmp_path,
        modo="aplicar",
        datos_escritura=datos_escritura,
    )
    datos = json.loads(ruta.read_text(encoding="utf-8"))

    assert datos["modo"] == "aplicar"
    assert datos["escritura_completada"] is True
    assert datos["publicaciones"][0]["accion"] == "AÑADIR_Y_ACTUALIZAR"


def test_lote_inseguro_genera_json_y_no_crea_backup_ni_escribe(tmp_path, capsys):
    import plazasboe

    detalle = _detalle("REDUCIDA", [_fila(), _fila(Puesto="Otro")], [_fila()])
    opciones = SimpleNamespace(
        desde=None, hasta=None, publicacion=None, limite=1
    )
    integridad = {"sha256": "a", "tamano": 1, "mtime_ns": 2}
    llamadas = {"backup": 0, "aplicar": 0}

    def guardar(*args, **kwargs):
        kwargs["directorio"] = tmp_path
        return guardar_informe_auditoria(*args, **kwargs)

    with pytest.raises(SystemExit) as salida:
        plazasboe._ejecutar_aplicacion_legacy(
            opciones,
            lambda: integridad,
            lambda **kwargs: ([detalle], _resumen([detalle])),
            guardar,
            asignar_acciones,
            lambda: llamadas.__setitem__("backup", llamadas["backup"] + 1),
            lambda detalles: llamadas.__setitem__("aplicar", llamadas["aplicar"] + 1),
        )

    assert salida.value.code == 1
    assert llamadas == {"backup": 0, "aplicar": 0}
    datos = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert datos["escritura_autorizada"] is False
    assert datos["escritura_completada"] is False
    assert datos["publicaciones"][0]["accion"] == "NO_ESCRIBIR"
    assert "ESCRITURA NO REALIZADA" in capsys.readouterr().out


def test_fallo_de_backup_actualiza_json_y_no_inicia_escritura(tmp_path, capsys):
    import plazasboe

    detalle = _detalle("SIN_CAMBIOS")
    opciones = SimpleNamespace(
        desde=None, hasta=None, publicacion=None, limite=1
    )
    integridad = {"sha256": "a", "tamano": 1, "mtime_ns": 2}
    aplicaciones = []

    def guardar(*args, **kwargs):
        kwargs["directorio"] = tmp_path
        return guardar_informe_auditoria(*args, **kwargs)

    with pytest.raises(BackupInvalidoError):
        plazasboe._ejecutar_aplicacion_legacy(
            opciones,
            lambda: integridad,
            lambda **kwargs: ([detalle], _resumen([detalle])),
            guardar,
            asignar_acciones,
            lambda: (_ for _ in ()).throw(BackupInvalidoError("backup inválido")),
            lambda detalles: aplicaciones.append(detalles),
        )

    assert aplicaciones == []
    datos = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert datos["escritura_autorizada"] is True
    assert datos["escritura_completada"] is False
    assert datos["error_escritura"] == "backup inválido"
    assert "ESCRITURA NO REALIZADA" in capsys.readouterr().out
