"""Regresiones independientes de informes locales para FASE 4."""
import json
from pathlib import Path

import pytest
from resolucion_geografica import resolver_administracion_geografia as resolver

@pytest.mark.parametrize("texto", ["Gran Canaria", "Servicios", "Sierra de San Pedro (Cáceres)", "Osona (Barcelona)", "La Vera (Cáceres)", "Debabarrena (Gipuzkoa)", "Gran Canaria (Las Palmas)"])
def test_falsos_positivos_no_asignan_municipio(texto):
    assert resolver(texto).municipio == ""

@pytest.mark.parametrize("texto,provincia,comunidad", [("X (Gupúzcoa)","Gipuzkoa","País Vasco/Euskadi"),("X (Amería)","Almería","Andalucía"),("X (Gizpuzkoa)","Gipuzkoa","País Vasco/Euskadi"),("X (Zagaroza)","Zaragoza","Aragón"),("X (Mallorca)","Mallorca","Illes Balears"),("X (Menorca)","Menorca","Illes Balears"),("X (Ibiza)","Ibiza/Eivissa","Illes Balears"),("X (Eivissa)","Ibiza/Eivissa","Illes Balears"),("X (Formentera)","Formentera","Illes Balears"),("X (Cuenca 112)","Cuenca","Castilla-La Mancha")])
def test_territorios_aprobados(texto,provincia,comunidad):
    r=resolver(texto); assert (r.provincia,r.comunidad_autonoma,r.confianza)==(provincia,comunidad,"ALTA")

def test_illes_ballears_es_comunidad_no_provincia():
    r=resolver("X (Illes Ballears)"); assert (r.provincia,r.comunidad_autonoma)==("","Illes Balears")

def test_parentesis_institucional_se_conserva_y_proexa_es_local():
    r=resolver("Ayuntamiento de Xàtiva (PROEXA)"); assert r.ambito=="LOCAL" and r.administracion_normalizada.endswith("(PROEXA)")

def test_conflicto_alta_no_se_persiste():
    r=resolver("Ayuntamiento de Soneja (Madrid)"); assert r.confianza=="AMBIGUA"


def test_organismo_autonomo_municipal_extrae_solo_el_municipio_previo():
    r = resolver("Ayuntamiento de Coria-Organismo Autónomo «Residencia Club de Ancianos» (Cáceres)")
    assert (r.municipio, r.codigo_ine, r.provincia, r.comunidad_autonoma, r.evidencia) == (
        "Coria", "10067", "Cáceres", "Extremadura", "AYUNTAMIENTO"
    )
    # Un descriptor parecido no autoriza a convertir una entidad supramunicipal
    # en el municipio que pudiera aparecer en su denominación.
    assert resolver("Mancomunidad de Coria-Organismo Autónomo (Cáceres)").municipio == ""


@pytest.mark.parametrize("texto,municipio,codigo", [
    ("Ayuntamiento de Villanueva de Castellón (Valencia)", "Castelló", "46257"),
    ("Ayuntamiento de Les Llosses (Girona)", "Llosses, Les", "17096"),
    ("Ayuntamiento de San Pedro de Pinatar (Murcia)", "San Pedro del Pinatar", "30036"),
    ("Ayuntamiento de Santa Marta de los Barros (Badajoz)", "Santa Marta", "06121"),
    ("Ayuntamiento de Oropesa y Corchuela (Toledo)", "Oropesa", "45125"),
    ("Ayuntamiento de Castril de la Peña (Granada)", "Castril", "18046"),
    ("Ayuntamiento de Otura (Granada)", "Villa de Otura", "18149"),
])
def test_aliases_municipales_v52_son_explicitos_y_provinciales(texto, municipio, codigo):
    r = resolver(texto)
    assert (r.municipio, r.codigo_ine, r.confianza, r.evidencia) == (municipio, codigo, "ALTA", "AYUNTAMIENTO")


@pytest.mark.parametrize("texto,municipio,codigo", [
    ("Ayuntamiento de Arcos de la Llana (Burgos)", "Arcos", "09023"),
    ("Ayuntamiento de Bidegoian (Gipuzkoa)", "Bidania-Goiatz", "20024"),
    ("Ayuntamiento de Bretó de la Ribera (Zamora)", "Bretó", "49025"),
    ("Ayuntamiento de Markina (Bizkaia)", "Markina-Xemein", "48060"),
    ("Ayuntamiento de Paracuellos de la Vega (Cuenca)", "Paracuellos", "16150"),
    ("Ayuntamiento de Villadecanes (León)", "Toral de los Vados", "24206"),
])
def test_aliases_municipales_v53_conservan_codigo_ine(texto, municipio, codigo):
    r = resolver(texto)
    assert (r.municipio, r.codigo_ine, r.confianza, r.evidencia) == (municipio, codigo, "ALTA", "AYUNTAMIENTO")


def test_ciutadella_acepta_contexto_insular_compatible_sin_relajar_conflictos():
    r = resolver("Ayuntamiento de Ciutadella (Menorca)")
    assert (r.municipio, r.codigo_ine, r.provincia, r.comunidad_autonoma, r.confianza, r.evidencia) == (
        "Ciutadella de Menorca", "07015", "Illes Balears", "Illes Balears", "ALTA", "AYUNTAMIENTO"
    )
    assert resolver("Ayuntamiento de Ciutadella (Mallorca)").evidencia == "CONFLICTO"


@pytest.mark.parametrize("administracion,fecha,codigo", [
    ("Ayuntamiento de Cerdedo (Pontevedra)", "2015-06-01", "36011"),
    ("Ayuntamiento de Cotobade (Pontevedra)", "2015-06-01", "36012"),
])
def test_municipios_historicos_solo_resuelven_en_su_intervalo(administracion, fecha, codigo):
    r = resolver(administracion, fecha_boe=fecha)
    assert (r.municipio, r.codigo_ine, r.codigo_historico, r.evidencia) == (
        "Cerdedo" if codigo == "36011" else "Cotobade", "", codigo, "MUNICIPIO_HISTORICO"
    )


def test_cerdedo_historico_no_se_proyecta_fuera_de_vigencia_ni_sin_fecha():
    for fecha in ("2020-01-01", ""):
        r = resolver("Ayuntamiento de Cerdedo (Pontevedra)", fecha_boe=fecha)
        assert r.codigo_historico == "" and r.codigo_ine == ""
    assert resolver("Ayuntamiento de Cerdedo (A Coruña)", fecha_boe="2015-01-01").codigo_historico == ""


def test_cerdedo_cotobade_posterior_sigue_siendo_municipio_vigente():
    r = resolver("Ayuntamiento de Cerdedo-Cotobade (Pontevedra)", fecha_boe="2020-01-01")
    assert (r.municipio, r.codigo_ine, r.codigo_historico) == ("Cerdedo-Cotobade", "36902", "")

def test_diputacion_y_destino_no_cambian_ambito():
    assert resolver("Diputación Foral de Gipuzkoa").provincia=="Gipuzkoa"
    r=resolver("Ministerio de Justicia","Fiscalía Provincial de Girona")
    assert (r.ambito,r.municipio,r.provincia,r.comunidad_autonoma,r.evidencia)==(
        "ESTATAL","Madrid","Madrid","Comunidad de Madrid","SEDE_ADMINISTRATIVA_CATALOGADA")


def test_sede_administrativa_es_exacta_y_no_captura_nombres_parecidos():
    r = resolver("Tribunal Constitucional")
    assert (r.municipio, r.codigo_ine, r.provincia, r.comunidad_autonoma, r.ambito, r.confianza, r.evidencia) == (
        "Madrid", "28079", "Madrid", "Comunidad de Madrid", "ESTATAL", "ALTA", "SEDE_ADMINISTRATIVA_CATALOGADA")
    assert resolver("Tribunal Constitucional Provincial").municipio == ""


def test_ministerio_del_interior_tiene_sede_documentada_no_heuristica():
    r = resolver("Ministerio del Interior", "Fiscalía Provincial de Sevilla")
    assert (r.municipio, r.codigo_ine, r.provincia, r.comunidad_autonoma, r.ambito, r.evidencia) == (
        "Madrid", "28079", "Madrid", "Comunidad de Madrid", "ESTATAL", "SEDE_ADMINISTRATIVA_CATALOGADA")
    assert resolver("Ministerio del Interior Inventado").municipio == ""


def test_ministerio_hacienda_es_alias_exacto_de_la_sede_canonica():
    r = resolver("Ministerio de Hacienda", "Fiscalía Provincial de Sevilla")
    assert (r.municipio, r.codigo_ine, r.provincia, r.comunidad_autonoma, r.evidencia) == (
        "Madrid", "28079", "Madrid", "Comunidad de Madrid", "SEDE_ADMINISTRATIVA_CATALOGADA")
    assert resolver("Ministerio de Hacienda Inventado").municipio == ""


def test_catalogo_ministerial_es_exacto_y_resuelve_solo_nombres_explicitos():
    catalogo = json.loads((Path(__file__).parent / "datos" / "sedes_administrativas.v1.json").read_text())
    nombres = [fila["administracion"] for fila in catalogo["sedes"]
               if fila["familia_administrativa"] == "MINISTERIO"]
    nombres += [fila["denominacion"] for fila in catalogo["alias_sedes"]
                if fila["denominacion"].startswith("Ministerio")]
    for administracion in nombres:
        r = resolver(administracion, "Técnico en Sevilla")
        assert (r.municipio, r.codigo_ine, r.provincia, r.comunidad_autonoma, r.confianza, r.evidencia) == (
            "Madrid", "28079", "Madrid", "Comunidad de Madrid", "ALTA", "SEDE_ADMINISTRATIVA_CATALOGADA")
    for administracion in ("Ministerio Inventado", "Ministerio de Pesca Inventado", "Ministerio de Hacienda Ficticio"):
        assert resolver(administracion).municipio == ""


@pytest.mark.parametrize("administracion", [
    "Ministerio de Fomento",
    "Ministerio de Empleo y Seguridad Social",
    "Ministerio de Sanidad, Servicios Sociales e Igualdad",
    "Ministerio de Sanidad y Consumo",
    "Ministerio de Ciencia e Innovación",
    "Ministerio de Defensa",
    "Ministerio de Educación y Ciencia",
    "Ministerio de Ciencia y Tecnología",
    "Ministerio de Trabajo y Asuntos Sociales",
    "Ministerio de Administraciones Públicas",
])
def test_sedes_ministeriales_catalogadas_son_exactas(administracion):
    r = resolver(administracion, "Fiscalía Provincial de Sevilla")
    assert (r.municipio, r.codigo_ine, r.provincia, r.comunidad_autonoma, r.evidencia) == (
        "Madrid", "28079", "Madrid", "Comunidad de Madrid", "SEDE_ADMINISTRATIVA_CATALOGADA")
    assert resolver(f"{administracion} Inventado").municipio == ""


def test_comunidad_autonoma_exacta_no_infiere_sede():
    r = resolver("Comunidad Autónoma de Galicia")
    assert (r.municipio, r.provincia, r.comunidad_autonoma, r.ambito, r.evidencia) == (
        "", "", "Galicia", "AUTONOMICO", "COMUNIDAD_ADMINISTRACION_EXACTA")

def test_idempotencia():
    r=resolver("Ayuntamiento de Soneja (Soneja, Castellón)"); assert resolver(r.administracion_original).como_dict()==r.como_dict()

@pytest.mark.parametrize("texto", ["Universidades", "Universidad de Salamanca", "Universitat de València", "Universidade de Vigo"])
def test_universidades_tienen_ambito_propio(texto):
    r=resolver(texto); assert (r.ambito,r.tipo_entidad)==("UNIVERSITARIO","UNIVERSIDAD")

def test_educacion_no_equivale_a_universidad():
    assert resolver("Ministerio de Ciencia, Innovación y Universidades").ambito == "ESTATAL"

@pytest.mark.parametrize("texto", [
    "Consejo Insular de Ibiza y Formentera (Illes Balears)",
    "Consejo Insular de Ibiza-Formentera (Illes Balears)",
])
def test_consejo_ibiza_formentera_es_territorio_analitico(texto):
    r=resolver(texto)
    assert (r.provincia,r.comunidad_autonoma,r.municipio,r.ambito,r.tipo_entidad,r.confianza,r.evidencia) == (
        "Ibiza-Formentera", "Illes Balears", "", "LOCAL", "INSULAR", "ALTA", "TERRITORIO_INSULAR")

def test_ibiza_y_formentera_incidental_no_activa_la_regla():
    assert resolver("Consorcio de Ibiza y Formentera").provincia == ""

@pytest.mark.parametrize("texto,provincia", [
    ("Consorcio para Servicio de Extinción en la Provincia de Cuenca", "Cuenca"),
    ("Consorcio de la Provincia de Valencia", "Valencia/València"),
    ("Consorcio Provincial contra Incendios y Salvamento de Huelva", "Huelva"),
    ("Consorcio Provincial de Medio Ambiente de Albacete", "Albacete"),
    ("Consorcio Provincial de Bomberos de Zamora", "Zamora"),
    ("Consorcio de Transportes de Bizkaia", "Bizkaia"),
    ("Consorcio de Turismo de Córdoba", "Córdoba"),
])
def test_entidades_territoriales_aprobadas(texto, provincia):
    r=resolver(texto); assert (r.provincia,r.confianza) == (provincia,"ALTA")


def test_sedes_aprobadas_son_reglas_exactas_y_no_patrones():
    csn = resolver("Consejo de Seguridad Nuclear")
    assert (csn.ambito, csn.tipo_entidad, csn.municipio, csn.provincia, csn.comunidad_autonoma,
            csn.confianza, csn.evidencia) == (
        "ESTATAL", "ESTATAL", "Madrid", "Madrid", "Comunidad de Madrid", "ALTA",
        "SEDE_ADMINISTRATIVA_CATALOGADA",
    )
    fortuny = resolver("Consorcio de Teatro Fortuny")
    assert (fortuny.ambito, fortuny.tipo_entidad, fortuny.municipio, fortuny.provincia,
            fortuny.comunidad_autonoma, fortuny.confianza, fortuny.evidencia) == (
        "LOCAL", "SUPRAMUNICIPAL", "Reus", "Tarragona", "Cataluña/Catalunya", "ALTA",
        "ENTIDAD_TERRITORIAL_CATALOGADA",
    )
    assert resolver("Consejo de Seguridad Radiológica").municipio == ""
    assert resolver("Consorcio de Teatro Municipal").municipio == ""

@pytest.mark.parametrize("texto,provincia,comunidad", [("Cabildo Insular de Lanzarote","Lanzarote","Canarias"),("Consejo Insular de Aguas de Gran Canaria","Gran Canaria","Canarias"),("Mancomunidad Migjorn de Mallorca","Mallorca","Illes Balears")])
def test_territorios_insulares_aprobados(texto,provincia,comunidad):
    r=resolver(texto); assert (r.provincia,r.comunidad_autonoma)==(provincia,comunidad)

def test_uned_melilla_catalogada():
    r=resolver("Consorcio Rector del Centro Universitario UNED Melilla (Ciudad de Melilla)")
    assert (r.provincia,r.municipio,r.comunidad_autonoma,r.ambito,r.confianza)==("Melilla","Melilla","Melilla","LOCAL","ALTA")

@pytest.mark.parametrize("texto,municipio,provincia,comunidad,evidencia", [
    ("Ayuntamiento de Valéncia)", "València", "Valencia/València", "Comunitat Valenciana", "MUNICIPIO_AYUNTAMIENTO"),
    ("Ayuntamiento de Cubas de la Sagra Madrid)", "Cubas de la Sagra", "Madrid", "Comunidad de Madrid", "MUNICIPIO_AYUNTAMIENTO"),
    ("Ayuntamiento de Maó-Mahón (Illes Balears)", "Maó", "Menorca", "Illes Balears", "MUNICIPIO_AYUNTAMIENTO"),
    ("Ayuntamiento de Santa Eulalia del Río (Illes Balears)", "Santa Eulària des Riu", "Ibiza/Eivissa", "Illes Balears", "MUNICIPIO_AYUNTAMIENTO"),
    ("Ayuntamiento de Palma de Mallorca-Patronato Municipal de Escuelas Infantiles (Illes Balears)", "Palma", "Mallorca", "Illes Balears", "MUNICIPIO_AYUNTAMIENTO"),
    ("Ayuntamiento de Sant Antoni de Postmany (Illes Balears)", "Sant Antoni de Portmany", "Ibiza/Eivissa", "Illes Balears", "MUNICIPIO_AYUNTAMIENTO"),
    ("Ayuntamiento de Sant Antony de Portmany (Illes Balears)", "Sant Antoni de Portmany", "Ibiza/Eivissa", "Illes Balears", "MUNICIPIO_AYUNTAMIENTO"),
])
def test_decisiones_municipales_cerradas(texto,municipio,provincia,comunidad,evidencia):
    r=resolver(texto)
    assert (r.municipio,r.provincia,r.comunidad_autonoma,r.ambito,r.tipo_entidad,r.confianza,r.evidencia)==(municipio,provincia,comunidad,"LOCAL","MUNICIPAL","ALTA",evidencia)

@pytest.mark.parametrize("texto,municipio,provincia,comunidad,evidencia", [
    ("Mancomunidad des Raiguer (Illes Balears)", "Raiguer", "Mallorca", "Illes Balears", "ENTIDAD_TERRITORIAL_CATALOGADA"),
    ("Consorcio de la Ciudad Romana de Pollentia (Illes Balears)", "Pollentia", "Mallorca", "Illes Balears", "ENTIDAD_TERRITORIAL_CATALOGADA"),
    ("Consorcio Hospitalario Provicial de Castellón", "", "Castellón/Castelló", "Comunitat Valenciana", "PROVINCIA_NOMBRE_ENTIDAD"),
    ("Consorcio de Transporte Metroplitano del Área de Granada", "", "Granada", "Andalucía", "ENTIDAD_TERRITORIAL_CATALOGADA"),
    ("Mancomunidad de Servicios Sociales THAM de Madrid", "", "Madrid", "Comunidad de Madrid", "ENTIDAD_TERRITORIAL_CATALOGADA"),
    ("Consorcio Hospitalario de Burgos", "", "Burgos", "Castilla y León", "ENTIDAD_TERRITORIAL_CATALOGADA"),
    ("Consorcio de Prevención, Extinción de Incendios y Salvamento de la Isla de Tenerife", "", "Tenerife", "Canarias", "TERRITORIO_INSULAR"),
    ("Mancomunidad de Servicios Comsermancha, Patronato de Integración Social Medio Ambiental (Castilla-La Mancha)", "", "Ciudad Real", "Castilla-La Mancha", "ENTIDAD_TERRITORIAL_CATALOGADA"),
    ("Mancomunidad Intermunicipal de Servicios Sociales del Este de Madrid-Missem", "", "Madrid", "Comunidad de Madrid", "ENTIDAD_TERRITORIAL_CATALOGADA"),
    ("Consorcio de extinción de incendios y salvamento de Alicante", "", "Alicante/Alacant", "Comunitat Valenciana", "ENTIDAD_TERRITORIAL_CATALOGADA"),
    ("Consorcio de Transportes de Vizcaya", "", "Bizkaia", "País Vasco/Euskadi", "ENTIDAD_TERRITORIAL_CATALOGADA"),
    ("Consorcio de Transporte Metropolitano del Área de Sevilla", "", "Sevilla", "Andalucía", "ENTIDAD_TERRITORIAL_CATALOGADA"),
    ("Consorcio de Prevención y Extinción de Incendios, Salvamentos y Protección Civil de Zamora", "", "Zamora", "Castilla y León", "ENTIDAD_TERRITORIAL_CATALOGADA"),
    ("Consorcio de Residuos Sólidos Urbanos de Granada", "", "Granada", "Andalucía", "ENTIDAD_TERRITORIAL_CATALOGADA"),
    ("Consorcio de las Vías Verdes de la Región de Murcia", "", "Murcia", "Región de Murcia", "ENTIDAD_TERRITORIAL_CATALOGADA"),
    ("Consorcio Provincial de Pontevedra para la Prestación del Servicio contra Incendios y Salvamento", "", "Pontevedra", "Galicia", "PROVINCIA_NOMBRE_ENTIDAD"),
    ("Consorcio Provincial de Lugo para la prestación del Servicio contra Incendios y Salvamento", "", "Lugo", "Galicia", "PROVINCIA_NOMBRE_ENTIDAD"),
    ("Consorcio Hospitalario Provincial de Castellón, que deja sin efecto la de 7 de abril de 2016", "", "Castellón/Castelló", "Comunitat Valenciana", "PROVINCIA_NOMBRE_ENTIDAD"),
])
def test_decisiones_entidades_cerradas(texto,municipio,provincia,comunidad,evidencia):
    r=resolver(texto)
    assert (r.municipio,r.provincia,r.comunidad_autonoma,r.ambito,r.tipo_entidad,r.confianza,r.evidencia)==(municipio,provincia,comunidad,"LOCAL","SUPRAMUNICIPAL","ALTA",evidencia)

@pytest.mark.parametrize("texto", [
    "Consorcio cualquiera Provicial de Sevilla", "Consorcio Metroplitano de Madrid",
    "Consorcio Hospitalario de Granada", "Consorcio de Madrid", "Ayuntamiento de Ejemplo)",
    "Mancomunidad de Illes Balears",
])
def test_decisiones_cerradas_no_capturan_textos_parecidos(texto):
    assert resolver(texto).provincia == ""
