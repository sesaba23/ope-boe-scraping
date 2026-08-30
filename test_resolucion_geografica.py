"""Regresiones independientes de informes locales para FASE 4."""
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

def test_diputacion_y_destino_no_cambian_ambito():
    assert resolver("Diputación Foral de Gipuzkoa").provincia=="Gipuzkoa"
    r=resolver("Ministerio de Justicia","Fiscalía Provincial de Girona"); assert (r.ambito,r.provincia)==("ESTATAL","Girona")

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
