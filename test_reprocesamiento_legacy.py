import hashlib
import json
import os
from pathlib import Path
import sys

import pandas as pd
import pytest
import requests

import coincidencias
import preparar_archivo_datos
import reprocesamiento_legacy
from reprocesamiento_legacy import (
    CAMPOS_CONVOCATORIA,
    calcular_integridad_excel,
    comparar_convocatorias,
    ejecutar_dry_run,
    guardar_informe_auditoria,
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
    assert "escritura" in capsys.readouterr().err


def test_main_dry_run_no_entra_en_flujo_normal(monkeypatch):
    import plazasboe

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
