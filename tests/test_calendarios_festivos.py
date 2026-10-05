import base_datos
from types import SimpleNamespace

from calendarios_festivos import (
    descargar_y_guardar_calendario,
    extraer_candidatos_sumario,
    festivos_para_anio,
    guardar_calendario,
    parsear_documento,
)


def _sumario(titulo, identificador="BOE-A-2026-1"):
    return {
        "estado": "OK",
        "sumario": {"diario": [{"seccion": [{"codigo": "1", "departamento": [{
            "nombre": "Presidencia",
            "item": [{"identificador": identificador, "titulo": titulo,
                      "url_html": "https://www.boe.es/diario_boe/txt.php?id=" + identificador}],
        }]}]}]},
    }


def test_detecta_calendario_en_seccion_distinta_de_oposiciones():
    candidatos = extraer_candidatos_sumario(
        _sumario("Resolución de 17 de octubre de 2025, por la que se publican las fiestas laborales para 2026.")
    )
    assert candidatos[0]["tipo"] == "FIESTAS_LABORALES"
    assert candidatos[0]["anio"] == 2026


def test_pipeline_expone_calendario_sin_ampliar_publicaciones_2b():
    import plazasboe

    respuesta = _sumario(
        "Resolución por la que se publican las fiestas laborales para 2026.",
        "BOE-A-2026-2",
    )
    resultado = plazasboe._descubrir_indice_api_con_fallback(
        "2025/10/17", "indice", consultar_api=lambda _: respuesta,
        consultar_html=lambda _: (_ for _ in ()).throw(AssertionError("no fallback")),
    )
    assert resultado["enlaces"] == []
    assert resultado["calendarios"][0]["anio"] == 2026


def test_parsea_fechas_nacionales_y_autonomicas():
    dias = parsear_documento(
        "<html><body><p>Enero</p><p>Día 1: Fiesta en todo el territorio nacional.</p>"
        "<p>Marzo</p><p>Día 19: inhábil en Galicia y Comunidad de Madrid.</p></body></html>",
        anio=2027, tipo="DIAS_INHABILES_AGE",
    )
    assert {d["fecha"] for d in dias if d["ambito"] == "NACIONAL"} == {"2027-01-01"}
    assert {d["comunidad_autonoma"] for d in dias if d["ambito"] == "AUTONOMICO"} == {
        "Galicia", "Comunidad de Madrid"
    }


def test_parsea_tabla_de_fiestas_por_columnas_autonomicas():
    dias = parsear_documento(
        """<table><tr><th>Fecha de las fiestas</th><th>Andalucía</th>
        <th>Castilla-La Mancha</th><th>Com. Madrid</th></tr>
        <tr><td>Enero</td><td></td><td></td><td></td></tr>
        <tr><td>1 Año Nuevo.</td><td>*</td><td>*</td><td>*</td></tr>
        <tr><td>6 Epifanía del Señor.</td><td>**</td><td>**</td><td>**</td></tr>
        <tr><td>Junio</td><td></td><td></td><td></td></tr>
        <tr><td>4 Corpus Christi.</td><td></td><td>***</td><td></td></tr>
        <tr><td>Marzo</td><td></td><td></td><td></td></tr>
        <tr><td>19 San José.</td><td></td><td></td><td>**</td></tr></table>""",
        anio=2026, tipo="FIESTAS_LABORALES",
    )
    assert {d["fecha"] for d in dias if d["ambito"] == "NACIONAL"} == {"2026-01-01", "2026-01-06"}
    assert {d["fecha"] for d in dias if d["comunidad_autonoma"] == "Castilla-La Mancha"} == {"2026-06-04"}
    assert {d["fecha"] for d in dias if d["comunidad_autonoma"] == "Comunidad de Madrid"} == {"2026-03-19"}


def test_persistencia_reutiliza_calendario_y_filtra_festivos(tmp_path):
    ruta = tmp_path / "boe.db"
    conexion = base_datos.conectar(ruta)
    base_datos.crear_esquema(conexion)
    conexion.commit(); conexion.close()
    candidato = {
        "anio": 2027, "tipo": "FIESTAS_LABORALES", "publicacion_id": "BOE-A-2026-1",
        "url_html": "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-1",
    }
    contenido = "<p>Enero</p><p>Día 6: Fiesta en todo el territorio nacional.</p>"
    resumen = guardar_calendario(ruta, candidato, contenido)
    assert resumen["estado"] == "PARSEADO"
    assert festivos_para_anio(ruta, 2027) == {"2027-01-06"}

    llamada = []
    omitido = descargar_y_guardar_calendario(
        ruta, candidato, obtener=lambda *args, **kwargs: llamada.append(args) or None
    )
    assert omitido["omitido"] is True
    assert llamada == []


def test_descubrimiento_anual_persiste_y_no_repite_ventana(tmp_path):
    from calendarios_festivos import descubrir_calendarios

    ruta = tmp_path / "boe.db"
    conexion = base_datos.conectar(ruta)
    base_datos.crear_esquema(conexion)
    conexion.commit(); conexion.close()
    candidatos = []
    for indice, tipo in enumerate((
        "fiestas laborales", "días inhábiles para la Administración General del Estado",
        "días inhábiles de las comunidades autónomas",
    ), 1):
        identificador = f"BOE-A-2025-{indice}"
        candidatos.append({
            "identificador": identificador, "titulo": f"Resolución: {tipo} 2026",
            "url_html": f"https://www.boe.es/diario_boe/txt.php?id={identificador}",
        })
    llamadas_sumario = []

    def sumario(fecha, timeout=20):
        llamadas_sumario.append(fecha)
        return {"estado": "OK", "sumario": {"diario": [{"seccion": [{
            "departamento": [{"nombre": "Estado", "item": candidatos}]
        }]}]}}

    def documento(url, **kwargs):
        return SimpleNamespace(
            content="<p>1 de enero: inhábil en todo el territorio nacional.</p>".encode(),
            raise_for_status=lambda: None,
        )

    primero = descubrir_calendarios(
        ruta, [2026], obtener_sumario=sumario, obtener_documento=documento, pausa=0,
    )
    assert len(primero["calendarios"]) == 3
    assert llamadas_sumario
    numero_llamadas = len(llamadas_sumario)
    segundo = descubrir_calendarios(
        ruta, [2026], obtener_sumario=sumario, obtener_documento=documento, pausa=0,
    )
    assert len(llamadas_sumario) == numero_llamadas
    assert segundo["consultas"] == 0
