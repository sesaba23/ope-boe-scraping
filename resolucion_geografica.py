"""Resolución geográfica conservadora y auditable (catálogo v1).

No realiza consultas de red ni coincidencias aproximadas.  Las islas de
Illes Balears son provincias analíticas por decisión explícita del proyecto.
"""
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
import re

import pandas as pd

from mapa_plazas import _variantes_nombre_catalogo, normalizar_nombre_municipal

VERSION_CATALOGO = "geografia-v1"
AMBITOS = {"ESTATAL", "AUTONOMICO", "LOCAL", "OTRO", "INDETERMINADO"}
PROVINCIAS_ALIAS = {
    "la coruna": "A Coruña", "coruna": "A Coruña", "orense": "Ourense",
    "guipuzcoa": "Gipuzkoa", "guipuzkoa": "Gipuzkoa", "gupuzcoa": "Gipuzkoa",
    "gizpuzkoa": "Gipuzkoa", "vizcaya": "Bizkaia", "alava": "Araba/Álava",
    "alicante": "Alicante/Alacant", "alacant": "Alicante/Alacant",
    "valencia": "Valencia/València", "valencia/valencia": "Valencia/València",
    "castellon": "Castellón/Castelló", "castello": "Castellón/Castelló",
    "gerona": "Girona", "lerida": "Lleida", "islas baleares": "Illes Balears",
    "illes baleares": "Illes Balears", "baleares": "Illes Balears",
    "ameria": "Almería", "zagar(o)za": "Zaragoza", "zagaroza": "Zaragoza",
}
COMUNIDADES = {"castilla la mancha": "Castilla-La Mancha", "illes balears": "Illes Balears",
               "islas baleares": "Illes Balears", "illes baleares": "Illes Balears"}
ISLAS_BALEARES = {"mallorca": ("Mallorca", "Illes Balears"), "menorca": ("Menorca", "Illes Balears"),
                  "ibiza": ("Ibiza/Eivissa", "Illes Balears"), "eivissa": ("Ibiza/Eivissa", "Illes Balears"),
                  "formentera": ("Formentera", "Illes Balears")}
MANUALES = {
    "proexa": ("Xàtiva", "Valencia/València", "Comunitat Valenciana", "LOCAL", "SOCIEDAD_MUNICIPAL"),
    "almunia": ("La Almunia de Doña Godina", "Zaragoza", "Aragón", "", "MUNICIPAL"),
    "gestalba": ("", "Albacete", "Castilla-La Mancha", "LOCAL", "PROVINCIAL"),
    "soneja, castellon": ("Soneja", "Castellón/Castelló", "Comunitat Valenciana", "", "MUNICIPAL"),
}

def clave(valor): return normalizar_nombre_municipal(valor)

@dataclass(frozen=True)
class ResolucionGeografica:
    administracion_original: str = ""; administracion_normalizada: str = ""
    ambito: str = "INDETERMINADO"; tipo_entidad: str = "INDETERMINADO"
    municipio: str = ""; provincia: str = ""; comunidad_autonoma: str = ""; codigo_ine: str = ""
    confianza: str = "NO_ENCONTRADO"; evidencia: str = ""; regla: str = ""; version_catalogo: str = VERSION_CATALOGO
    conflicto: str = ""
    def como_dict(self): return asdict(self)

class CatalogoGeografico:
    def __init__(self, ruta_municipios="datos/municipios_oficial.csv", ruta_alias="datos/alias_municipios.csv"):
        self.municipios = pd.read_csv(ruta_municipios, sep=";", dtype=str).fillna("").to_dict("records")
        aliases = pd.read_csv(ruta_alias, sep=";", dtype=str).fillna("").to_dict("records")
        self.provincias = {}
        self.municipios_por_nombre = defaultdict(list)
        self.codigo = {}
        for fila in self.municipios:
            self.codigo[str(fila["Codigo_INE"]).zfill(5)] = fila
            for v in _variantes_nombre_catalogo(fila["Municipio"]): self.municipios_por_nombre[clave(v)].append(fila)
            for v in (fila["Provincia"], *fila["Provincia"].split("/")): self.provincias[clave(v)] = fila["Provincia"]
        self.provincias.update({clave(k): v for k,v in PROVINCIAS_ALIAS.items()})
        for fila in aliases:
            if fila.get("Confianza") == "ALTA" and str(fila.get("Codigo_INE", "")).zfill(5) in self.codigo:
                self.municipios_por_nombre[clave(fila["Alias"])].append(self.codigo[str(fila["Codigo_INE"]).zfill(5)])

    def provincia(self, texto): return self.provincias.get(clave(texto.strip(" ,.;")))
    def municipio(self, texto, provincia=""):
        candidatos = {(x["Codigo_INE"], x["Municipio"]): x for x in self.municipios_por_nombre.get(clave(texto), [])}
        if provincia: candidatos = {k:v for k,v in candidatos.items() if v["Provincia"] == provincia}
        return next(iter(candidatos.values())) if len(candidatos) == 1 else None

_CATALOGO = None
def catalogo():
    global _CATALOGO
    if _CATALOGO is None: _CATALOGO = CatalogoGeografico()
    return _CATALOGO

def _ultimo_parentesis(texto):
    valores = re.findall(r"\(([^()]*)\)", texto or "")
    return valores[-1].strip() if valores else ""

def _ambito_tipo(admin):
    a=clave(admin)
    if a == "administracion local": return "INDETERMINADO", "INDETERMINADO"
    if a == "universidades": return "INDETERMINADO", "INDETERMINADO"
    if a.startswith("universidad de "): return "OTRO", "UNIVERSIDAD"
    if re.match(r"^(ministerio|consejo de estado|consejo general del poder judicial|tribunal supremo|agencia estatal)",a): return "ESTATAL","ESTATAL"
    if re.match(r"^(junta de|generalitat|gobierno vasco|principado de asturias|comunidad autonoma)",a): return "AUTONOMICO","AUTONOMICA"
    if re.match(r"^(ayuntamiento|ajuntament|concello|udala)\b",a): return "LOCAL","MUNICIPAL"
    if re.match(r"^(diputacion|diputacio|deputacion)\b",a): return "LOCAL","PROVINCIAL"
    if re.match(r"^(cabildo|consell|consejo insular)\b",a): return "LOCAL","INSULAR"
    if re.match(r"^(mancomunidad|consorcio|entidad local)\b",a): return "LOCAL","SUPRAMUNICIPAL"
    return "INDETERMINADO","INDETERMINADO"

def _limpiar(admin, territorial):
    valor=" ".join((admin or "").split()); valor=re.sub(r"\s+([,.;:])",r"\1",valor)
    if territorial: valor=re.sub(r"\s*\([^()]*\)\s*$","",valor).strip(" ,.;")
    return valor

def resolver_administracion_geografia(administracion, puesto="", *, _catalogo=None):
    """Resuelve sólo evidencias exactas; no persiste ni modifica sus argumentos."""
    c=_catalogo or catalogo(); admin=str(administracion or "").strip(); par=_ultimo_parentesis(admin); k=clave(par)
    ambito,tipo=_ambito_tipo(admin); municipio=provincia=comunidad=codigo=""; evidencia=regla=""; confianza="NO_ENCONTRADO"; territorial=False
    # Decisiones de catálogo manual, restringidas al paréntesis exacto.
    if k in MANUALES:
        municipio,provincia,comunidad,a,t=MANUALES[k]; ambito=a or ambito; tipo=t; confianza="ALTA"; evidencia="REGLA_MANUAL"; regla=f"manual:{k}"; territorial=k=="soneja, castellon"
    elif k == "las palmas de gran canaria":
        municipio,provincia,comunidad="Las Palmas de Gran Canaria","Las Palmas","Canarias"; confianza="ALTA"; evidencia="REGLA_MANUAL"; regla="municipio_manual"; territorial=True
    elif k == "castellon de la plana":
        municipio,provincia,comunidad="Castelló de la Plana/Castellón de la Plana","Castellón/Castelló","Comunitat Valenciana"; confianza="ALTA"; evidencia="REGLA_MANUAL"; regla="municipio_manual"; territorial=True
    elif k == "cuenca 112":
        provincia,comunidad="Cuenca","Castilla-La Mancha"; confianza="ALTA"; evidencia="REGLA_MANUAL"; regla="contaminante_manual"; territorial=True
    elif k in ISLAS_BALEARES:
        provincia,comunidad=ISLAS_BALEARES[k]; confianza="ALTA"; evidencia="ISLA_PARENTESIS"; regla="isla_balear"; territorial=True
    elif k in COMUNIDADES:
        comunidad=COMUNIDADES[k]; confianza="ALTA"; evidencia="COMUNIDAD_PARENTESIS"; regla="comunidad_explicita"; territorial=True
    elif k in {"gupuzcoa","gizpuzkoa","ameria","zagaroza"}:
        provincia=c.provincia(par); confianza="ALTA"; evidencia="REGLA_MANUAL"; regla=f"errata_provincia:{k}"; territorial=True
    elif k in {"illes ballears","llles balears"}:
        comunidad="Illes Balears"; confianza="ALTA"; evidencia="REGLA_MANUAL"; regla=f"errata_comunidad:{k}"; territorial=True
    else:
        # En entidades insulares el paréntesis puede ser un municipio cuyo
        # nombre coincide con provincia (Santa Cruz de Tenerife).
        m_parentesis = c.municipio(par) if re.match(r"^cabildo\s+insular\s+de\s+tenerife\b", clave(admin)) else None
        if m_parentesis:
            municipio,provincia,comunidad,codigo=m_parentesis["Municipio"],m_parentesis["Provincia"],m_parentesis["Comunidad"],m_parentesis["Codigo_INE"]
            confianza="ALTA"; evidencia="MUNICIPIO_PARENTESIS"; regla="municipio_parentesis"; territorial=True
            p = None
        else: p=c.provincia(par)
        if p:
            provincia=p; confianza="ALTA"; evidencia="PROVINCIA_PARENTESIS" if clave(par)==clave(p) else "ALIAS_PROVINCIA"; regla="provincia_parentesis"; territorial=True
        else:
            m=c.municipio(par)
            if m:
                municipio,provincia,comunidad,codigo=m["Municipio"],m["Provincia"],m["Comunidad"],m["Codigo_INE"]; confianza="ALTA"; evidencia="MUNICIPIO_PARENTESIS"; regla="municipio_parentesis"; territorial=True
    # Ayuntamiento exacto. El contexto provincial, si existe, desambigua.
    patron=re.match(r"^(?:ayuntamiento|ajuntament|concello)\s+(?:de(?:l| la)?|d['’])\s+(.+?)(?:\s*\(|\s*,|$)",admin,re.I)
    if patron:
        nombre=patron.group(1).strip()
        if re.match(r"^(?:ayuntamiento|ajuntament|concello)\s+de\s+la\s+", admin, re.I): nombre="La "+nombre
        elif re.match(r"^(?:ayuntamiento|ajuntament|concello)\s+del\s+", admin, re.I): nombre="El "+nombre
        m=c.municipio(nombre, provincia)
        if m:
            if provincia and provincia != m["Provincia"]:
                return ResolucionGeografica(admin,_limpiar(admin,territorial),ambito,tipo,confianza="AMBIGUA",evidencia="CONFLICTO",regla="conflicto_municipio_provincia",conflicto="municipio/provincia")
            municipio,provincia,comunidad,codigo=m["Municipio"],m["Provincia"],m["Comunidad"],m["Codigo_INE"]; confianza="ALTA"; evidencia="AYUNTAMIENTO"; regla="municipio_exacto"
        elif provincia and c.municipio(nombre):
            return ResolucionGeografica(admin,_limpiar(admin,territorial),ambito,tipo,confianza="AMBIGUA",evidencia="CONFLICTO",regla="conflicto_municipio_provincia",conflicto="municipio/provincia")
    if not municipio and not provincia:
        m=c.municipio(admin)
        if m:
            municipio,provincia,comunidad,codigo=m["Municipio"],m["Provincia"],m["Comunidad"],m["Codigo_INE"]
            confianza="ALTA"; evidencia="MUNICIPIO_EXACTO"; regla="municipio_exacto_unico"
    # Instituciones territoriales: sólo el segmento final validado contra provincia.
    if not provincia:
        patron_entidad = re.match(r"^(?:diputaci[oó]n(?:\s+(?:provincial|foral))?|diputaci[oó]|deputaci[oó]n)\s+de\s+(.+?)\s*$", admin, re.I)
        if patron_entidad and c.provincia(patron_entidad.group(1)):
            provincia=c.provincia(patron_entidad.group(1)); confianza="ALTA"; evidencia="DIPUTACION"; regla="provincia_entidad_exacta"; ambito="LOCAL"; tipo="PROVINCIAL"
    # Destino provincial cerrado: no altera ámbito.
    destinos={c.provincia(x) for x in re.findall(r"(?:Fiscal[ií]a Provincial|Tribunal Superior de Justicia) de\s+([^,;.()]+)",puesto or "",re.I)}-{None}
    if len(destinos)==1:
        destino=next(iter(destinos))
        if provincia and provincia != destino:
            return ResolucionGeografica(admin,_limpiar(admin,territorial),ambito,tipo,confianza="AMBIGUA",evidencia="CONFLICTO",regla="conflicto_destino_provincia",conflicto="destino/provincia")
        provincia=destino; confianza="ALTA"; evidencia="DESTINO_PUESTO"; regla="destino_provincial"
    if provincia and not comunidad:
        filas=[x for x in c.municipios if x["Provincia"] == provincia]
        if filas: comunidad=filas[0]["Comunidad"]
    return ResolucionGeografica(admin,_limpiar(admin,territorial),ambito,tipo,municipio,provincia,comunidad,codigo,confianza,evidencia,regla,VERSION_CATALOGO)
