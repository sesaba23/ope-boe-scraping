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
