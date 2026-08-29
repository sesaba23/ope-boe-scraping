from datetime import datetime
import json

import extractor_historico_boe as historico


def _xml(texto, titulo="Se convocan pruebas selectivas", tabla=""):
    return f"""<documento><metadatos><identificador>BOE-A-2004-1</identificador><departamento>Ayuntamiento de Prueba</departamento><titulo>{titulo}</titulo><fecha_publicacion>20040102</fecha_publicacion></metadatos><texto><p>{texto}</p>{tabla}</texto></documento>""".encode()


def _extraer(texto, titulo="Se convocan pruebas selectivas", tabla=""):
    return historico.extraer_desde_contenido("BOE-A-2004-1", _xml(texto, titulo, tabla), "xml", "html")


def test_numero_de_vacantes_y_plazas():
    assert _extraer("Policía Local. Personal funcionario. Número de vacantes: 26.")["convocatorias"][0]["Num_plazas"] == 26
    assert _extraer("Número de plazas: 4.")["convocatorias"][0]["Num_plazas"] == 4


def test_familias_se_convocan_prueba_selectiva_y_convocatoria():
    for texto, numero in (("Se convocan un total de 3 plazas de Auxiliar.", 3), ("Pruebas selectivas para cubrir 5 plazas de Técnico.", 5), ("Convocatoria para cubrir 7 plazas de Oficial.", 7)):
        resultado = _extraer(texto)
        assert resultado["convocatorias"][0]["Num_plazas"] == numero


def test_turnos_y_sistemas():
    casos = (("turno libre por oposición", "Turno libre", "Oposición"), ("promoción interna mediante concurso", "Promoción interna", "Concurso"), ("movilidad por concurso-oposición", "Movilidad", "Concurso-oposición"), ("turno libre por concurso de méritos", "Turno libre", "Concurso de méritos"))
    for frase, turno, sistema in casos:
        campos = _extraer(f"Número de plazas: 1. {frase}.")["convocatorias"][0]
        assert campos["Turno"] == turno
        assert campos["Sistema"] == sistema


def test_varias_plazas_divididas_por_turno_no_conservan_total_agregado():
    resultado = _extraer("Número de vacantes: 26. 20 plazas de turno libre. 6 plazas de movilidad. Oposición.")
    assert [(c["Num_plazas"], c["Turno"]) for c in resultado["convocatorias"]] == [(20, "Libre"), (6, "Movilidad")]


def test_escala_subescala_clase_y_puesto_en_frases_sucesivas():
    texto = "Policía Local. Personal funcionario. Escala de Administración Especial. Subescala de Servicios Especiales. Clase Policía Local. Número de vacantes: 2."
    campos = _extraer(texto)["convocatorias"][0]
    assert campos["Puesto"] == "Policía Local"
    assert campos["Escala"] == "Administración Especial"
    assert campos["Subescala"] == "Servicios Especiales"
    assert campos["Clase"] == "Policía Local"


def test_tabla_xml_manda_y_texto_complementa_sin_sobrescribir():
    tabla = "<table><tr><th>Puesto</th><th>Número de plazas</th></tr><tr><td>Bombero</td><td>3</td></tr></table>"
    resultado = _extraer("Número de plazas: 9. Turno libre por oposición.", tabla=tabla)
    assert len(resultado["convocatorias"]) == 1
    assert resultado["convocatorias"][0]["Puesto"] == "Bombero"
    assert resultado["convocatorias"][0]["Num_plazas"] == 3
    assert resultado["convocatorias"][0]["Turno"] == "Turno libre"
    fuentes = {e["campo"]: e["fuente"] for e in resultado["evidencias"][0]}
    assert fuentes["Num_plazas"] == "XML_TABLE"


def test_excluye_admitidos_tribunal_correccion_resultado_y_nombramiento():
    titulos = ["Lista definitiva de admitidos", "Tribunal calificador", "Corrección de errores", "Resultados finales", "Nombramientos"]
    for titulo in titulos:
        resultado = _extraer("Se convocaron 4 plazas por oposición.", titulo)
        assert resultado["clasificacion_documento"] == "NO_CONVOCATORIA"
        assert resultado["convocatorias"] == []


def test_documento_ambiguo_no_genera_filas():
    resultado = _extraer("Se informa sobre el procedimiento administrativo.", "Resolución informativa")
    assert resultado["clasificacion_documento"] == "INDETERMINADO"
    assert resultado["convocatorias"] == []


def test_varias_convocatorias_en_bloques_separados():
    xml = """<documento><metadatos><identificador>BOE-A-2004-1</identificador><titulo>Se convocan plazas</titulo></metadatos><texto><p>Número de plazas: 2. Plazas de Auxiliar.</p><p>Condiciones primera convocatoria.</p><p>---</p><p>Número de plazas: 3. Plazas de Técnico.</p></texto></documento>""".encode()
    resultado = historico.extraer_desde_contenido("BOE-A-2004-1", xml, "xml")
    assert [c["Num_plazas"] for c in resultado["convocatorias"]] == [2, 3]


def test_evidencia_por_campo_tiene_fuente_confianza_y_fragmento():
    resultado = _extraer("Número de plazas: 4. Turno libre por oposición.")
    evidencia = resultado["evidencias"][0][0]
    assert set(evidencia) == {"campo", "valor", "fuente", "confianza", "fragmento_evidencia"}
    assert evidencia["fuente"] in historico.FUENTES


def test_funcion_publica_descarga_solo_xml():
    llamadas = []
    class Respuesta:
        content = _xml("Número de plazas: 1.")
        def raise_for_status(self): pass
    resultado = historico.extraer_convocatorias_historicas("BOE-A-2004-1", "xml", "html", lambda url, **k: llamadas.append(url) or Respuesta())
    assert llamadas == ["xml"]
    assert resultado["publicacion_id"] == "BOE-A-2004-1"


def test_informe_y_ausencia_de_reglas_por_publicacion(tmp_path):
    resultado = _extraer("Número de plazas: 1. Turno libre.")
    rutas = historico.guardar_informes([resultado], tmp_path, datetime(2026, 8, 23, 12))
    assert json.loads(rutas[0].read_text())["resumen"]["documentos_analizados"] == 1
    assert "Evidencias" in rutas[1].read_text()
    fuente = open(historico.__file__, encoding="utf-8").read()
    assert "BOE-A-2004-6389" not in fuente
    assert "BOE-A-2004-6488" not in fuente


def _cantidad(valor, tipo, posicion=0, distribucion=True, turno=None, sistema=None):
    return {"valor": valor, "fragmento": f"{valor} plazas", "posicion": posicion,
            "fuente": "HISTORICAL_TEXT", "Puesto": None, "Turno": turno,
            "Sistema": sistema, "Escala": None, "Subescala": None, "Clase": None,
            "tipo_inicial": tipo, "confianza": "ALTA", "evidencia": "distribución",
            "relacion_distribucion": distribucion}


def test_reconciliar_total_y_dos_componentes_exactos_sin_mutar():
    cantidades = [_cantidad(105, "TOTAL", 0), _cantidad(100, "COMPONENTE", 10, turno="Promoción interna"), _cantidad(5, "COMPONENTE", 20, turno="Turno libre")]
    resultado = historico.reconciliar_cantidades(cantidades)
    assert resultado["estado"] == "TOTAL_DESGLOSADO"
    assert [x["valor"] for x in resultado["cantidades_funcionales"]] == [100, 5]
    assert cantidades[0]["tipo_inicial"] == "TOTAL"


def test_reconciliar_varios_componentes_y_sistemas_distintos():
    cantidades = [_cantidad(10, "TOTAL", 0), _cantidad(2, "COMPONENTE", 1, sistema="Oposición"), _cantidad(3, "COMPONENTE", 2, sistema="Concurso"), _cantidad(5, "COMPONENTE", 3, sistema="Concurso-oposición")]
    resultado = historico.reconciliar_cantidades(cantidades)
    assert resultado["grupos"][0]["suma_componentes"] == 10
    assert len(resultado["cantidades_funcionales"]) == 3


def test_total_no_cuadra_es_ambiguo_y_no_descarta_nada():
    resultado = historico.reconciliar_cantidades([_cantidad(10, "TOTAL"), _cantidad(3, "COMPONENTE", 1), _cantidad(4, "COMPONENTE", 2)])
    assert resultado["estado"] == "AMBIGUO"
    assert len(resultado["cantidades_funcionales"]) == 3


def test_no_reconcilia_suma_accidental_ni_independientes():
    cantidades = [_cantidad(5, "DESCONOCIDO", 0), _cantidad(3, "COMPONENTE", 1), _cantidad(2, "COMPONENTE", 2)]
    assert historico.reconciliar_cantidades(cantidades)["estado"] == "SIN_RECONCILIACION"
    cantidades = [_cantidad(5, "TOTAL", 0, distribucion=False), _cantidad(3, "COMPONENTE", 1), _cantidad(2, "COMPONENTE", 2)]
    assert historico.reconciliar_cantidades(cantidades)["estado"] == "SIN_RECONCILIACION"


def test_dos_grupos_y_casos_sin_total_o_sin_componentes():
    cantidades = [_cantidad(3, "TOTAL", 0), _cantidad(1, "COMPONENTE", 1), _cantidad(2, "COMPONENTE", 2), _cantidad(4, "TOTAL", 100), _cantidad(4, "COMPONENTE", 101)]
    assert len(historico.reconciliar_cantidades(cantidades)["grupos"]) == 2
    assert historico.reconciliar_cantidades([_cantidad(2, "COMPONENTE")])["estado"] == "SIN_RECONCILIACION"
    assert historico.reconciliar_cantidades([_cantidad(2, "TOTAL")])["estado"] == "SIN_RECONCILIACION"


def test_tabla_se_preserva_y_el_total_textual_no_la_sobrescribe():
    tabla = "<table><tr><th>Puesto</th><th>Número de plazas</th></tr><tr><td>Bombero</td><td>3</td></tr></table>"
    resultado = _extraer("Se convocan 5 plazas, distribuidas: 3 plazas por turno libre y 2 plazas por movilidad.", tabla=tabla)
    assert resultado["convocatorias"][0]["Num_plazas"] == 3
    assert resultado["evidencias"][0][0]["fuente"] == "XML_TABLE"


def test_detectar_cantidades_clasifica_total_y_componentes():
    cantidades = historico.detectar_cantidades("Se convocan 105 plazas distribuidas de la siguiente forma: 100 plazas por promoción interna y 5 plazas por turno libre.")
    assert [x["tipo_inicial"] for x in cantidades] == ["TOTAL", "COMPONENTE", "COMPONENTE"]
    assert historico.reconciliar_cantidades(cantidades)["estado"] == "TOTAL_DESGLOSADO"


def test_caso_referencia_10041_representa_componentes_y_no_total_agregado():
    texto = (
        "Se convocan pruebas selectivas para cubrir 100 plazas vacantes, "
        "con la siguiente distribución: Cincuenta plazas para cubrir por el "
        "sistema general de acceso libre. Cincuenta plazas para cubrir por el "
        "sistema de promoción interna."
    )
    cantidades = historico.detectar_cantidades(texto)
    resultado = historico.reconciliar_cantidades(cantidades)
    assert resultado["estado"] == "TOTAL_DESGLOSADO"
    assert [(c["valor"], c["Turno"]) for c in resultado["cantidades_funcionales"]] == [
        (50, "Turno libre"), (50, "Promoción interna")
    ]


def test_puesto_prioriza_categoria_profesional_explicita_sobre_descriptor_generico():
    campos = historico.extraer_campos_bloque(
        "Una plaza de personal laboral en la categoría profesional de Ordenanza, nivel 7.")["campos"]
    assert campos["Puesto"] == "Ordenanza"
    campos = historico.extraer_campos_bloque(
        "Personal laboral fijo. Categoría de Jefe Regional de Seguridad.")["campos"]
    assert campos["Puesto"] == "Jefe Regional de Seguridad"


def test_puesto_lista_denominacion_y_cantidad_no_hereda_entre_elementos():
    primero = historico.extraer_campos_bloque("Profesores de Enseñanza Secundaria, 183 plazas.")["campos"]
    segundo = historico.extraer_campos_bloque("Profesores Técnicos de Formación Profesional, 35 plazas.")["campos"]
    assert primero["Puesto"] == "Profesores de Enseñanza Secundaria"
    assert segundo["Puesto"] == "Profesores Técnicos de Formación Profesional"
    assert historico.extraer_pares_denominacion_cantidad(
        "Profesores de Enseñanza Secundaria, 183 plazas. "
        "Profesores Técnicos de Formación Profesional, 35 plazas.") == [
        ("Profesores de Enseñanza Secundaria", 183, "Profesores de Enseñanza Secundaria, 183 plazas"),
        ("Profesores Técnicos de Formación Profesional", 35, ". Profesores Técnicos de Formación Profesional, 35 plazas"),
    ]


def test_subcupo_explicito_se_registra_como_incluido_sin_sumarse_al_total():
    texto = ("Se convocan 100 plazas distribuidas: 60 plazas por turno libre, "
             "de las cuales 5 plazas reservadas para discapacidad, y 40 plazas "
             "por promoción interna.")
    resultado = historico.reconciliar_cantidades(historico.detectar_cantidades(texto))
    assert resultado["estado"] == "TOTAL_DESGLOSADO"
    assert resultado["grupos"][0]["suma_componentes"] == 100
    assert [x["valor"] for x in resultado["subcupos_incluidos"]] == [5]
    assert "SUBCUPO_INCLUIDO" in resultado["tipos_relacion"]


def test_cupo_sin_frase_de_inclusion_no_se_marca_como_subcupo():
    cantidades = historico.detectar_cantidades("60 plazas por turno libre. 5 plazas para discapacidad.")
    assert not any(x["tipo_inicial"] == "SUBCUPO" for x in cantidades)


def test_segmentador_tabla_crea_un_bloque_valido_por_fila_y_admite_miles():
    tabla = ("<table><tr><th>Denominación</th><th>Vacantes</th></tr>"
             "<tr><td>Arquitecto</td><td>1.250</td></tr>"
             "<tr><td>Ingeniero</td><td>3</td></tr></table>")
    resultado = historico.extraer_segmentado_desde_contenido("BOE-A-2004-1", _xml("", tabla=tabla), "xml")
    validos = [b for b in resultado["bloques"] if b["calidad"] == "VALIDA"]
    assert [(b["campos"]["Puesto"], b["campos"]["Num_plazas"]) for b in validos] == [("Arquitecto", 1250), ("Ingeniero", 3)]
    assert all(b["origen"] == "TABLA" for b in validos)


def test_segmentador_separa_secuencias_puesto_cantidad_y_verticales():
    xml = """<documento><metadatos><identificador>BOE-A-2004-1</identificador></metadatos><texto>
    <p>Una plaza de Arquitecto.</p><p>Dos plazas de Ingeniero Industrial.</p>
    <p>Administrativo</p><p>Número de plazas: 3.</p></texto></documento>""".encode()
    resultado = historico.extraer_segmentado_desde_contenido("BOE-A-2004-1", xml, "xml")
    validos = [(b["campos"]["Puesto"], b["campos"]["Num_plazas"]) for b in resultado["bloques"] if b["calidad"] == "VALIDA"]
    assert validos == [("Arquitecto", 1), ("Ingeniero Industrial", 2), ("Administrativo", 3)]


def test_segmentador_no_infiere_puesto_de_descripcion_y_calidad_solo_exige_dos_campos():
    resultado = historico.extraer_segmentado_desde_contenido("BOE-A-2004-1", _xml("Número de plazas: 2. Funciones de vigilancia."), "xml")
    bloque = resultado["bloques"][0]
    assert bloque["campos"]["Puesto"] is None
    assert bloque["calidad"] == "VALIDA_PARCIAL"
    assert historico.clasificar_bloque_historico({"campos": {"Puesto": "Auxiliar", "Num_plazas": 1}}) == "VALIDA"


def test_convertir_cantidad_admite_miles_y_palabras_controladas():
    assert historico._convertir_cantidad("1 250") == 1250
    assert historico._convertir_cantidad("tres mil veintiocho") == 3028
    assert historico._convertir_cantidad("artículo") is None


def test_segmentador_asocia_encabezado_enumerado_y_no_sector_de_distribucion():
    xml = """<documento><metadatos><identificador>BOE-A-2004-1</identificador></metadatos><texto>
    <p>1. Médicos: 1.250 plazas.</p><p>a) Sector público: 1.000 plazas.</p>
    </texto></documento>""".encode()
    bloques = historico.extraer_segmentado_desde_contenido("BOE-A-2004-1", xml, "xml")["bloques"]
    assert [(b["campos"]["Puesto"], b["campos"]["Num_plazas"]) for b in bloques] == [("Médicos", 1250), (None, 1000)]


def test_segmentador_no_convierte_totales_tabulares_en_convocatorias():
    tabla = "<table><tr><th>Cuerpo</th><th>Plazas</th></tr><tr><td>Total</td><td>7</td></tr></table>"
    bloques = historico.extraer_segmentado_desde_contenido("BOE-A-2004-1", _xml("", tabla=tabla), "xml")["bloques"]
    assert [(b["campos"]["Puesto"], b["calidad"]) for b in bloques] == [(None, "VALIDA_PARCIAL")]


def _bloque_contexto(puesto, grupo=1):
    return {"tipo": "CONTEXTO", "origen": "PARRAFO", "posicion": 0, "texto": puesto,
            "campos": {campo: None for campo in historico.CAMPOS}, "evidencias": [],
            "contexto_anterior": None, "encabezado_local": puesto, "bloque_padre": grupo}


def _bloque_cantidad(cantidad, grupo=1, origen="PARRAFO", tabla=None):
    bloque = {"tipo": "DATOS", "origen": origen, "posicion": cantidad,
              "texto": f"Número de plazas: {cantidad}", "campos": {campo: None for campo in historico.CAMPOS},
              "evidencias": [historico._evidencia("Num_plazas", cantidad, "HISTORICAL_TEXT", "ALTA", f"{cantidad} plazas")],
              "contexto_anterior": None, "encabezado_local": None, "bloque_padre": grupo}
    if tabla is not None: bloque.update({"tabla_indice": tabla, "fila_indice": cantidad})
    bloque["campos"]["Num_plazas"] = cantidad
    return bloque


def test_composicion_hereda_encabezado_unico_y_conserva_evidencia_sin_mutar():
    original = [_bloque_contexto("Policía Local"), _bloque_cantidad(5)]
    compuesto = historico.componer_contexto_bloques(original)
    bloque = compuesto["bloques"][1]
    assert bloque["campos"]["Puesto"] == "Policía Local"
    assert bloque["evidencias"][-1]["fuente"] == "CONTEXT_INHERITANCE"
    assert original[1]["campos"]["Puesto"] is None


def test_composicion_hereda_componentes_de_turno_y_rechaza_dos_puestos():
    correcto = historico.componer_contexto_bloques([_bloque_contexto("Escala Técnica"), _bloque_cantidad(15), _bloque_cantidad(5)])
    assert [b["campos"]["Puesto"] for b in correcto["bloques"] if b["tipo"] == "DATOS"] == ["Escala Técnica", "Escala Técnica"]
    ambiguo = historico.componer_contexto_bloques([_bloque_contexto("Arquitecto"), _bloque_cantidad(2), _bloque_contexto("Ingeniero"), _bloque_cantidad(3)])
    assert ambiguo["bloques"][3]["campos"]["Puesto"] == "Ingeniero"
    assert not ambiguo["contextos_ambiguos"]


def test_composicion_rechaza_dos_candidatos_en_el_mismo_grupo():
    primero, segundo, cantidad = _bloque_cantidad(1), _bloque_cantidad(2), _bloque_cantidad(3)
    primero["campos"]["Puesto"], segundo["campos"]["Puesto"] = "Arquitecto", "Ingeniero"
    resultado = historico.componer_contexto_bloques([primero, segundo, cantidad])
    assert resultado["bloques"][2]["campos"]["Puesto"] is None
    assert resultado["bloques"][2]["diagnostico_contexto"] == "CONTEXTO_AMBIGUO"


def test_composicion_no_cruza_limites_de_seccion_ni_tablas():
    bloques = [_bloque_contexto("Arquitecto", 1), _bloque_cantidad(2, 2), _bloque_cantidad(3, 3, "TABLA", tabla=0)]
    compuesto = historico.componer_contexto_bloques(bloques)["bloques"]
    assert compuesto[1]["campos"]["Puesto"] is None
    assert compuesto[2]["campos"]["Puesto"] is None


def test_composicion_tabla_hereda_fila_superior_y_opcionales_no_invalidan():
    encabezado = _bloque_cantidad(0, 4, "TABLA", tabla=1)
    encabezado["campos"]["Puesto"] = "Bombero"
    fila = _bloque_cantidad(3, 4, "TABLA", tabla=1)
    fila["heredable_contexto_tabla"] = True
    compuesto = historico.componer_contexto_bloques([encabezado, fila])["bloques"]
    assert compuesto[1]["campos"]["Puesto"] == "Bombero"
    assert historico.clasificar_bloque_historico(compuesto[1]) == "VALIDA"
