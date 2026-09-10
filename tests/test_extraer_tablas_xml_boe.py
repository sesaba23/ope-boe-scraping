from datetime import datetime
import json

import extraer_tablas_xml_boe as tablas


def _xml(contenido):
    return f"<documento><texto>{contenido}</texto></documento>".encode()


def test_encabezados_normales_equivalentes_y_numeros():
    resultado = tablas.parsear_tablas_xml(_xml("<table><tr><th>Puesto</th><th>N.º plazas</th><th>Turno</th></tr><tr><td>Auxiliar</td><td>2</td><td>Libre</td></tr></table>"))[0]
    assert resultado["encabezados"] == ["Puesto", "N.º plazas", "Turno"]
    assert tablas.extraer_resultados_tabla(resultado) == [{"Puesto": "Auxiliar", "Num_plazas": 2, "Escala": None, "Turno": "Libre", "Sistema": None}]


def test_rowspan_colspan_conservan_orden_y_generan_celdas_independientes():
    xml = _xml("<table><tr><th rowspan='2'>Puesto</th><th colspan='2'>Datos</th></tr><tr><td>A</td><td>B</td></tr><tr><td>Auxiliar</td><td>1</td><td>X</td></tr></table>")
    tabla = tablas.parsear_tablas_xml(xml)[0]
    assert tabla["encabezados"] == ["Puesto", "Datos", "Datos"]
    assert tabla["filas"][0] == ["Puesto", "A", "B"]
    assert tabla["filas"][1] == ["Auxiliar", "1", "X"]
    celda = tabla["filas_estructuradas"][1]["celdas"][0]
    assert celda["celda_origen"] == [2, 0]
    assert set(celda) == {"texto", "fila_original", "columna_original", "rowspan", "colspan", "heredada", "celda_origen", "tipo"}


def test_grupo_colspan_y_rowspan_permiten_herencia_solo_estructural():
    xml = _xml("<table><tr><th>Puesto</th><th>Plazas</th></tr><tr><td colspan='2'>Bomberos</td></tr><tr><td></td><td>3</td></tr><tr><td rowspan='2'>Arquitecto</td><td>1</td></tr><tr><td>2</td></tr></table>")
    tabla = tablas.parsear_tablas_xml(xml)[0]
    estructurada = tablas.estructurar_grupos_tabla(tabla)
    assert estructurada["filas_estructuradas"][0]["es_grupo"] is True
    assert estructurada["filas_estructuradas"][1]["grupo_padre"] == "Bomberos"
    assert estructurada["filas_estructuradas"][3]["celdas"][0]["heredada"] is True
    bloques = tablas.extraer_bloques_tabla_estructurados(tabla)
    assert any(b["estructura"]["grupo_padre"] == "Bomberos" for b in bloques)


def test_varias_tablas_filas_incompletas_y_valor_no_convertible():
    xml = _xml("<table><tr><th>Puesto</th><th>Vacantes</th></tr><tr><td>A</td><td>dos</td></tr><tr><td>B</td></tr></table><table><tr><th>Sistema</th></tr><tr><td>Oposición</td></tr></table>")
    resultado = tablas.parsear_tablas_xml(xml)
    assert len(resultado) == 2
    assert tablas.extraer_resultados_tabla(resultado[0])[0]["Num_plazas"] is None
    assert tablas.extraer_resultados_tabla(resultado[0])[1]["Puesto"] == "B"
    assert tablas.extraer_resultados_tabla(resultado[1]) == []


def test_tabla_sin_encabezados_utiles_y_ausencia_de_tablas():
    sin_utilidad = tablas.parsear_tablas_xml(_xml("<table><tr><th>Nombre</th></tr><tr><td>A</td></tr></table>"))
    assert tablas.extraer_resultados_tabla(sin_utilidad[0]) == []
    assert tablas.clasificar_utilidad(sin_utilidad, []) == "TABLA_NO_UTIL"
    assert tablas.parsear_tablas_xml(_xml("<p>Texto</p>")) == []
    assert tablas.clasificar_utilidad([], []) == "SIN_TABLAS"


def test_categoria_contextual_controlada_excluye_tabla_de_tribunal():
    principal = tablas.parsear_tablas_xml(_xml("<table><tr><th>Código</th><th>Categoría/Cuerpo/Escala-Tipo</th></tr><tr><td></td><td>Catedráticos</td></tr><tr><td>X1</td><td>Actividades docentes</td></tr></table>"))[0]
    assert tablas.extraer_resultados_tabla(principal)[0]["Puesto"] == "Catedráticos"
    tribunal = tablas.parsear_tablas_xml(_xml("<table><tr><th>Calidad</th><th>Categoría/Cuerpo/Escala</th></tr><tr><td>Presidente</td><td>Catedrático</td></tr></table>"))[0]
    assert tablas.extraer_resultados_tabla(tribunal) == []


def test_generacion_informe_unicode_y_cero_efectos_productivos(tmp_path):
    excel = tmp_path / "BOE-oposiciones.xlsx"; excel.write_bytes(b"intacto")
    documento = {"Publicacion_ID": "BOE-A-2004-1", "Fecha": "2004-01-01", "url_xml": "x", "numero_tablas": 0, "tablas": [], "resultados_parciales": [], "filas_utiles": 0, "extractor_actual_filas": 0, "clasificacion": "SIN_TABLAS", "campos_no_recuperados": tablas.CAMPOS_RESULTADO}
    rutas = tablas.guardar_informes([documento], tmp_path / "informes", datetime(2026, 8, 23, 12))
    datos = json.loads(rutas[0].read_text(encoding="utf-8"))
    assert datos["documentos"][0]["Publicacion_ID"] == "BOE-A-2004-1"
    assert "Recomendación" in rutas[1].read_text(encoding="utf-8")
    assert excel.read_bytes() == b"intacto"


def test_obtencion_url_xml_reutiliza_api():
    def api(fecha):
        identificador = next(k for k, v in tablas.DOCUMENTOS.items() if v == fecha)
        return {"estado": "OK", "sumario": {"diario": [{"seccion": {"codigo": "2B", "departamento": {"item": {"identificador": identificador, "url_xml": f"xml:{identificador}"}}}}]}}
    docs = tablas.obtener_documentos_api(api)
    assert [d["Publicacion_ID"] for d in docs] == list(tablas.DOCUMENTOS)
    assert all(d["url_xml"].startswith("xml:") for d in docs)
