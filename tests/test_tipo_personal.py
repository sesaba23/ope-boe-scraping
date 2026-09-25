from tipo_personal import clasificar_tipo_personal


def op(puesto, **extra):
    base = {"puesto": puesto, "puesto_normalizado": puesto, "escala": "--", "subescala": "--", "clase": "--"}
    base.update(extra)
    return base


def pub(titulo=""):
    return {"titulo_original": titulo}


def assert_cat(resultado, categoria, confianza=None):
    assert resultado["categoria"] == categoria
    if confianza:
        assert resultado["confianza"] == confianza
    assert resultado["reglas_aplicadas"]
    assert resultado["version"] == "tipo-personal-v1"


def test_universitario_estructurado_y_prioridades():
    resultado = clasificar_tipo_personal(op("Escala Auxiliar Administrativa", ambito="UNIVERSITARIO", escala="Administración General"))
    assert_cat(resultado, "Universitario", "alta")
    assert "Funcionario" in resultado["familias_detectadas"]
    assert_cat(clasificar_tipo_personal(op("Escala de Operadores", tipo_entidad="UNIVERSIDAD", administracion="Universidades")), "Universitario")
    assert_cat(clasificar_tipo_personal(op("Personal laboral fijo", ambito="UNIVERSITARIO")), "Universitario")
    assert_cat(clasificar_tipo_personal(op("Profesor Titular de Universidad")), "Universitario")
    assert_cat(clasificar_tipo_personal(op("Profesor titular de guardería municipal", ambito="LOCAL", tipo_entidad="MUNICIPAL")), "No determinado")
    assert_cat(clasificar_tipo_personal(op("Profesor de patronato municipal de música", ambito="LOCAL", tipo_entidad="MUNICIPAL")), "No determinado")


def test_militar_y_exclusiones_civiles():
    assert_cat(clasificar_tipo_personal(op("Oficiales de los Cuerpos Generales de los Ejércitos")), "Militar", "alta")
    assert_cat(clasificar_tipo_personal(op("Ingenieros Técnicos de Arsenales de la Armada")), "Funcionario")
    assert_cat(clasificar_tipo_personal(op("Policía Local con reserva de una plaza para militares profesionales de tropa y marinería", escala="Administración Especial", subescala="Servicios Especiales", clase="Policía Local")), "Funcionario")
    assert_cat(clasificar_tipo_personal(op("Agente de Movilidad dirigida a militares profesionales", ambito="LOCAL", escala="Administración Especial", subescala="Servicios Especiales")), "Funcionario")
    assert_cat(clasificar_tipo_personal(op("Técnico civil del Ministerio de Defensa", administracion="Ministerio de Defensa")), "No determinado")
    assert_cat(clasificar_tipo_personal(op("Oficial de Administración General")), "No determinado", "baja")


def test_estatutario_conservador():
    assert_cat(clasificar_tipo_personal(op("Personal estatutario fijo de los Servicios de Salud")), "Estatutario", "alta")
    assert_cat(clasificar_tipo_personal(op("Facultativo Especialista en Dermatología")), "No determinado")
    assert_cat(clasificar_tipo_personal(op("Enfermero de hospital", tipo_entidad="AUTONOMICA")), "No determinado")


def test_laboral_y_prioridad_universitaria():
    for puesto in ("Personal laboral fijo", "Personal laboral temporal", "Operario de plantilla de personal laboral", "Contrato laboral grupo profesional"):
        assert_cat(clasificar_tipo_personal(op(puesto)), "Laboral", "alta")
    resultado = clasificar_tipo_personal(op("Personal laboral fijo", tipo_entidad="UNIVERSIDAD", ambito="UNIVERSITARIO"))
    assert_cat(resultado, "Universitario")
    assert "Laboral" in resultado["familias_detectadas"]


def test_funcionario_alto_medio_y_limites():
    assert_cat(clasificar_tipo_personal(op("Funcionario de carrera")), "Funcionario", "alta")
    assert_cat(clasificar_tipo_personal(op("Cuerpo de Ingenieros Industriales del Estado")), "Funcionario", "media")
    assert_cat(clasificar_tipo_personal(op("Técnico de Administración General")), "Funcionario", "media")
    assert_cat(clasificar_tipo_personal(op("Policía Local", escala="Administración Especial", subescala="Servicios Especiales")), "Funcionario", "media")
    assert_cat(clasificar_tipo_personal(op("Auxiliar Administrativo")), "No determinado")
    assert_cat(clasificar_tipo_personal(op("Trabajador Social")), "No determinado")
    assert_cat(clasificar_tipo_personal(op("Escala Administrativa", ambito="UNIVERSITARIO", tipo_entidad="UNIVERSIDAD")), "Universitario")


def test_otros_y_fallback_no_determinado():
    assert_cat(clasificar_tipo_personal(op("Director de Coro de personal eventual")), "Otros", "media")
    for puesto in ("Ordenanza", "Maestro Industrial", "Peón de Jardinería", ""):
        assert_cat(clasificar_tipo_personal(op(puesto)), "No determinado", "baja")


def test_pdi_requiere_contexto_universitario():
    assert_cat(clasificar_tipo_personal(op("Personal docente e investigador", ambito="UNIVERSITARIO")), "Universitario")
    assert_cat(clasificar_tipo_personal(op("Monitora PDI", ambito="LOCAL", tipo_entidad="MUNICIPAL")), "No determinado")


def test_determinismo_idempotencia_y_no_mutacion():
    registro = op("Personal laboral fijo", ambito="LOCAL")
    antes = dict(registro)
    primero = clasificar_tipo_personal(registro)
    segundo = clasificar_tipo_personal(registro)
    assert primero == segundo
    assert registro == antes


def test_universidad_popular_y_ministerio_no_son_universidad():
    caso = op("Profesor de Artesanía de la plantilla de personal laboral fijo", administracion="Ayuntamiento de Albacete, Patronato de la Universidad Popular Municipal", ambito="LOCAL")
    resultado = clasificar_tipo_personal(caso)
    assert_cat(resultado, "Laboral", "alta")
    assert "Universitario" not in resultado["familias_detectadas"]
    assert_cat(clasificar_tipo_personal(op("EX11", administracion="Ministerio de Universidades")), "No determinado")
    assert_cat(clasificar_tipo_personal(op("Auxiliar Administrativo", administracion="Ayuntamiento de Valencia, Universidad Popular", escala="Administración General", subescala="Auxiliar")), "Funcionario")


def test_cuerpos_civiles_de_arsenales_y_convocatoria_mixta():
    for puesto in (
        "Ingenieros Técnicos de Arsenales de la Armada",
        "Maestros de Arsenales de la Armada",
        "Oficiales de Arsenales de la Armada",
    ):
        resultado = clasificar_tipo_personal(op(puesto, administracion="Ministerio de Defensa"))
        assert_cat(resultado, "Funcionario", "alta")
        assert resultado["reglas_aplicadas"] == ["cuerpo_civil_arsenales"]
        assert "Militar" not in resultado["familias_detectadas"]
    assert_cat(clasificar_tipo_personal(op("Oficiales de los Cuerpos Generales de los Ejércitos")), "Militar")
    assert_cat(clasificar_tipo_personal(op("Fuerzas Armadas y Escala Superior de Oficiales de la Guardia Civil")), "No determinado")


def test_convenio_negado_no_crea_conflicto_laboral_y_regimen_laboral_si():
    caso = op("Responsable de Seguridad no sujeto al Convenio Colectivo Único de la Administración General del Estado")
    resultado = clasificar_tipo_personal(caso)
    assert_cat(resultado, "No determinado", "baja")
    assert "Laboral" not in resultado["familias_detectadas"]
    assert_cat(clasificar_tipo_personal(op("Técnico Superior", escala="Básica", clase="Técnicos Superiores y régimen laboral")), "Laboral", "alta")


def test_prioridad_laboral_frente_a_estructura_funcionarial():
    resultado = clasificar_tipo_personal(op("Operario de plantilla de personal laboral fijo", escala="Administración Especial", subescala="Servicios Especiales"))
    assert_cat(resultado, "Laboral", "alta")
    assert resultado["familias_detectadas"] == ["Laboral", "Funcionario"]


def test_titulo_mixto_no_atribuye_regimen_laboral_a_cada_plaza():
    titulo = (
        "Ingreso en el Cuerpo Facultativo de Conservadores de Museos, y cambio "
        "de régimen jurídico del personal laboral fijo incluido en el anexo II "
        "del IV Convenio Único para el personal laboral de la Administración "
        "General del Estado"
    )
    resultado = clasificar_tipo_personal(op("Cuerpo Facultativo de Conservadores de Museos"), pub(titulo))
    assert_cat(resultado, "No determinado")
    assert "Laboral" not in resultado["familias_detectadas"]
    assert "Funcionario" not in resultado["familias_detectadas"]


def test_titulo_laboral_sin_evidencia_de_fila_no_basta():
    resultado = clasificar_tipo_personal(
        op("Médico de Sanidad Marítima (personal fuera de convenio)"),
        pub("Convocatoria como personal laboral fijo fuera de convenio"),
    )
    assert_cat(resultado, "No determinado")


def test_fundacion_con_escala_no_prueba_regimen_funcionarial():
    caso = op(
        "Encargado de Instalaciones de la Fundación Municipal de Deportes",
        escala="Administración Especial",
    )
    resultado = clasificar_tipo_personal(caso)
    assert_cat(resultado, "No determinado")
    assert "Funcionario" not in resultado["familias_detectadas"]
    assert_cat(clasificar_tipo_personal(op(
        "Encargado de Instalaciones de la Fundación Municipal de Deportes de la plantilla de personal laboral fijo",
        escala="Administración Especial",
    )), "Laboral", "alta")
    funcionario = clasificar_tipo_personal(op(
        "Funcionario de carrera de la Fundación Municipal de Deportes",
        escala="Administración Especial",
    ))
    assert_cat(funcionario, "Funcionario", "alta")
    assert "Funcionario" in funcionario["familias_detectadas"]


def test_subgrupo_profesional_no_es_grupo_profesional_laboral():
    caso = op(
        "Auxiliar Administrativo/a del subgrupo profesional C2",
        escala="Administración General", subescala="Auxiliar",
    )
    resultado = clasificar_tipo_personal(caso)
    assert_cat(resultado, "Funcionario", "media")
    assert "Laboral" not in resultado["familias_detectadas"]
    assert_cat(clasificar_tipo_personal(op("Peón/a especialista y grupo profesional AP")), "Laboral", "alta")


def test_escala_laboral_no_se_interpreta_como_funcionarial():
    for puesto, subescala in (
        ("Oficial/a Gobernante/a", "Obrera"),
        ("Oficial de Brigada de Obras", "Oficios"),
    ):
        resultado = clasificar_tipo_personal(op(puesto, escala="Laboral", subescala=subescala))
        assert_cat(resultado, "Laboral", "alta")
        assert "Laboral" in resultado["familias_detectadas"]


def test_grupo_profesional_en_subescala_no_prueba_regimen_laboral():
    resultado = clasificar_tipo_personal(op(
        "Operador/a de Informática", escala="Administración Especial",
        subescala="Técnico Auxiliar y grupo profesional C1",
    ))
    assert_cat(resultado, "Funcionario", "media")
    assert "Laboral" not in resultado["familias_detectadas"]
    assert_cat(clasificar_tipo_personal(op(
        "Peón/a especialista y grupo profesional AP", escala="Administración General",
    )), "Laboral", "alta")


def test_policia_local_como_destino_de_plaza_de_mantenimiento():
    resultado = clasificar_tipo_personal(op(
        "Auxiliar Mantenimiento (Policía Local) perteneciente al Grupo C",
        administracion="Ayuntamiento de Jerez de los Caballeros",
    ))
    assert_cat(resultado, "No determinado")
    assert "Funcionario" not in resultado["familias_detectadas"]
    assert_cat(clasificar_tipo_personal(op("Agente de la Policía Local")), "Funcionario", "media")


def test_auxiliar_de_policia_local_no_prueba_regimen():
    for puesto in (
        "Auxiliar policía local", "Auxiliar de Policía Local",
        "Auxiliar de la Policía Local", "Auxiliares de la Policía Local",
    ):
        assert_cat(clasificar_tipo_personal(op(puesto)), "No determinado")
    assert_cat(clasificar_tipo_personal(op("Agente de Policía Local")), "Funcionario", "media")


def test_fila_que_mezcla_plazas_funcionarias_y_laborales():
    for puesto in (
        "Peón de la Brigada Municipal (personal laboral) y otra de Auxiliar Administrativo (funcionario de carrera)",
        "funcionario de carrera mediante promoción interna del personal laboral fijo",
    ):
        resultado = clasificar_tipo_personal(op(puesto, escala="Administración General"))
        assert_cat(resultado, "No determinado", "baja")
        assert resultado["reglas_aplicadas"] == ["colectivos_mezclados_en_fila"]
    assert_cat(clasificar_tipo_personal(op("Auxiliar Administrativo (funcionario de carrera)")), "Funcionario")


def test_funcionarizacion_no_atribuye_regimen_de_origen_ni_destino():
    resultado = clasificar_tipo_personal(op(
        "laboral de Celador y Velador a Auxiliares educadores",
        escala="Administración Especial",
        subescala="o categoría laboral de Celador y Velador a Auxiliares educadores",
    ))
    assert_cat(resultado, "No determinado", "baja")
    assert resultado["reglas_aplicadas"] == ["regimen_de_origen_y_destino"]


def test_dos_plazas_de_regimen_distinto_extraidas_en_una_fila():
    resultado = clasificar_tipo_personal(op(
        "Auxiliar de Administración en régimen laboral y una plaza de Técnico de Administración General",
    ))
    assert_cat(resultado, "No determinado", "baja")
    assert resultado["reglas_aplicadas"] == ["colectivos_mezclados_en_fila"]


def test_habilitacion_nacional_incidental_en_terapeuta_no_prueba_funcionario():
    resultado = clasificar_tipo_personal(op(
        "Terapeuta Ocupacional de Atención Temprana y Habilitación Nacional "
        "de la plantilla de personal labora",
        administracion="Mancomunidad de Municipios de la Serena",
    ))
    assert_cat(resultado, "No determinado", "baja")
    assert "Funcionario" not in resultado["familias_detectadas"]


def test_escala_con_nombre_de_puesto_y_grupo_no_prueba_funcionario():
    resultado = clasificar_tipo_personal(op(
        "Auxiliar Administrativo/a", escala="Auxiliar Administrativo", clase="grupo C",
    ))
    assert_cat(resultado, "No determinado", "baja")
    assert_cat(clasificar_tipo_personal(op(
        "Subinspector", escala="Técnica", clase="Policía Local",
    )), "Funcionario", "media")


def test_administracion_general_o_especial_aislada_no_prueba_regimen():
    for puesto in (
        "Administrativo de Administración General",
        "Auxiliar de Administración General",
        "Personal de Apoyo a la Administración General",
        "Técnico Administración Especial (Pedagogo)",
    ):
        resultado = clasificar_tipo_personal(op(puesto))
        assert_cat(resultado, "No determinado", "baja")
        assert resultado["grupos_evidencia"] == []

    resultado = clasificar_tipo_personal(op(
        "Auxiliar Administrativo", escala="Administración General", subescala="Auxiliar",
    ))
    assert_cat(resultado, "Funcionario", "media")
    assert resultado["grupos_evidencia"] == ["estructura_funcionarial"]


def test_estructura_arrastrada_incompatible_con_peon_no_prueba_funcionario():
    resultado = clasificar_tipo_personal(op(
        "Dos plazas de Peón", subescala="Técnica", clase="Superior",
    ))
    assert_cat(resultado, "No determinado", "baja")
    assert resultado["reglas_aplicadas"] == ["estructura_incompatible_con_puesto"]


def test_reglas_estructurales_correlacionadas_forman_un_solo_grupo_de_evidencia():
    resultado = clasificar_tipo_personal(op(
        "Técnico de Gestión", escala="Administración Especial",
        subescala="Técnica", clase="Superior",
    ))
    assert_cat(resultado, "Funcionario", "media")
    assert len(resultado["reglas_aplicadas"]) == 3
    assert resultado["grupos_evidencia"] == ["estructura_funcionarial"]
