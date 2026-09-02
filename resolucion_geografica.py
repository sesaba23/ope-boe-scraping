"""Resolución geográfica conservadora y auditable (catálogo v1).

No realiza consultas de red ni coincidencias aproximadas.  Las islas de
Illes Balears son provincias analíticas por decisión explícita del proyecto.
"""
from collections import defaultdict
from dataclasses import asdict, dataclass
from functools import lru_cache
import json
from pathlib import Path
import re

import pandas as pd

from mapa_plazas import _variantes_nombre_catalogo, normalizar_nombre_municipal

VERSION_CATALOGO = "geografia-v1"
RUTA_SEDES_ADMINISTRATIVAS = Path(__file__).resolve().parent / "datos" / "sedes_administrativas.v1.json"
AMBITOS = {"ESTATAL", "AUTONOMICO", "LOCAL", "UNIVERSITARIO", "OTRO", "INDETERMINADO"}
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
CONSEJOS_IBIZA_FORMENTERA = {
    "consejo insular de ibiza y formentera",
    "consejo insular de ibiza formentera",
}
TERRITORIOS_INSULARES = {"menorca": ("Menorca", "Illes Balears"), "mallorca": ("Mallorca", "Illes Balears"),
    "lanzarote": ("Lanzarote", "Canarias"), "gran canaria": ("Gran Canaria", "Canarias"), "tenerife": ("Tenerife", "Canarias")}
ENTIDADES_TERRITORIALES = {
    "consorcio de transportes de bizkaia": "Bizkaia", "consorcio de turismo de cordoba": "Córdoba",
    "consorcio orquesta de cordoba": "Córdoba", "consorcio institucion ferial de cadiz": "Cádiz",
    "consorcio de turismo y congresos de a coruna": "A Coruña", "consorcio de aguas y residuos de la rioja": "La Rioja",
}
MANCOMUNIDADES_TERRITORIALES = {"suroeste de madrid": "Madrid", "sur de leon": "León", "migjorn de mallorca": "Mallorca", "pla de mallorca": "Mallorca"}
SUFIJO_CONVOCATORIA = re.compile(r"\s+referente\s+a\s+la\s+convocatoria\s+para\s+proveer\s+varias\s+plazas\s*$", re.I)
MANUALES = {
    "proexa": ("Xàtiva", "Valencia/València", "Comunitat Valenciana", "LOCAL", "SOCIEDAD_MUNICIPAL"),
    "almunia": ("La Almunia de Doña Godina", "Zaragoza", "Aragón", "", "MUNICIPAL"),
    "gestalba": ("", "Albacete", "Castilla-La Mancha", "LOCAL", "PROVINCIAL"),
    "soneja, castellon": ("Soneja", "Castellón/Castelló", "Comunitat Valenciana", "", "MUNICIPAL"),
}
# Decisiones manuales de FASE 4. Las claves son denominaciones completas
# normalizadas, no patrones: evitan convertir estas excepciones en heurísticas.
MUNICIPIOS_CERRADOS = {
    "ayuntamiento de valencia)": ("València", "Valencia/València", "Comunitat Valenciana", "Ayuntamiento de València"),
    "ayuntamiento de cubas de la sagra madrid)": ("Cubas de la Sagra", "Madrid", "Comunidad de Madrid", "Ayuntamiento de Cubas de la Sagra"),
    "ayuntamiento de mao mahon": ("Maó", "Menorca", "Illes Balears", None),
    "ayuntamiento de santa eulalia del rio": ("Santa Eulària des Riu", "Ibiza/Eivissa", "Illes Balears", None),
    "ayuntamiento de palma de mallorca patronato municipal de escuelas infantiles": ("Palma", "Mallorca", "Illes Balears", None),
    "ayuntamiento de sant antoni de postmany": ("Sant Antoni de Portmany", "Ibiza/Eivissa", "Illes Balears", None),
    "ayuntamiento de sant antony de portmany": ("Sant Antoni de Portmany", "Ibiza/Eivissa", "Illes Balears", None),
}
ENTIDADES_CERRADAS = {
    # Sedes aprobadas individualmente: no son patrones para otros consejos o
    # consorcios y no alteran el ámbito territorial de competencia.
    "consejo de seguridad nuclear": ("Madrid", "Madrid", "Comunidad de Madrid", "ESTATAL", "ESTATAL", "SEDE_ADMINISTRATIVA_CATALOGADA", None),
    "consorcio de teatro fortuny": ("Reus", "Tarragona", "Cataluña/Catalunya", "LOCAL", "SUPRAMUNICIPAL", "ENTIDAD_TERRITORIAL_CATALOGADA", None),
    "mancomunidad des raiguer": ("Raiguer", "Mallorca", "Illes Balears", "LOCAL", "SUPRAMUNICIPAL", "ENTIDAD_TERRITORIAL_CATALOGADA", None),
    "consorcio de la ciudad romana de pollentia": ("Pollentia", "Mallorca", "Illes Balears", "LOCAL", "SUPRAMUNICIPAL", "ENTIDAD_TERRITORIAL_CATALOGADA", None),
    "consorcio hospitalario provicial de castellon": ("", "Castellón/Castelló", "Comunitat Valenciana", "LOCAL", "SUPRAMUNICIPAL", "PROVINCIA_NOMBRE_ENTIDAD", "Consorcio Hospitalario Provincial de Castellón"),
    "consorcio de transporte metroplitano del area de granada": ("", "Granada", "Andalucía", "LOCAL", "SUPRAMUNICIPAL", "ENTIDAD_TERRITORIAL_CATALOGADA", "Consorcio de Transporte Metropolitano del Área de Granada"),
    "mancomunidad de servicios comsermancha": ("", "Ciudad Real", "Castilla-La Mancha", "LOCAL", "SUPRAMUNICIPAL", "ENTIDAD_TERRITORIAL_CATALOGADA", None),
    "mancomunidad de servicios comsermancha, patronato de integracion social medio ambiental": ("", "Ciudad Real", "Castilla-La Mancha", "LOCAL", "SUPRAMUNICIPAL", "ENTIDAD_TERRITORIAL_CATALOGADA", None),
    "mancomunidad intermunicipal de l'horta sud": ("", "Valencia/València", "Comunitat Valenciana", "LOCAL", "SUPRAMUNICIPAL", "ENTIDAD_TERRITORIAL_CATALOGADA", None),
    "mancomunidad intermunicipal de servicios sociales del este de madrid": ("", "Madrid", "Comunidad de Madrid", "LOCAL", "SUPRAMUNICIPAL", "ENTIDAD_TERRITORIAL_CATALOGADA", None),
    "mancomunidad intermunicipal de servicios sociales del este de madrid missem": ("", "Madrid", "Comunidad de Madrid", "LOCAL", "SUPRAMUNICIPAL", "ENTIDAD_TERRITORIAL_CATALOGADA", None),
    "consorcio de extincion de incendios y salvamento de alicante": ("", "Alicante/Alacant", "Comunitat Valenciana", "LOCAL", "SUPRAMUNICIPAL", "ENTIDAD_TERRITORIAL_CATALOGADA", None),
    "consorcio de transportes de vizcaya": ("", "Bizkaia", "País Vasco/Euskadi", "LOCAL", "SUPRAMUNICIPAL", "ENTIDAD_TERRITORIAL_CATALOGADA", None),
    "mancomunidad de servicios sociales tham de madrid": ("", "Madrid", "Comunidad de Madrid", "LOCAL", "SUPRAMUNICIPAL", "ENTIDAD_TERRITORIAL_CATALOGADA", None),
    "consorcio de transporte metropolitano del area de sevilla": ("", "Sevilla", "Andalucía", "LOCAL", "SUPRAMUNICIPAL", "ENTIDAD_TERRITORIAL_CATALOGADA", None),
    "consorcio de prevencion y extincion de incendios, salvamentos y proteccion civil de zamora": ("", "Zamora", "Castilla y León", "LOCAL", "SUPRAMUNICIPAL", "ENTIDAD_TERRITORIAL_CATALOGADA", None),
    "consorcio de residuos solidos urbanos de granada": ("", "Granada", "Andalucía", "LOCAL", "SUPRAMUNICIPAL", "ENTIDAD_TERRITORIAL_CATALOGADA", None),
    "consorcio de las vias verdes de la region de murcia": ("", "Murcia", "Región de Murcia", "LOCAL", "SUPRAMUNICIPAL", "ENTIDAD_TERRITORIAL_CATALOGADA", None),
    "consorcio hospitalario de burgos": ("", "Burgos", "Castilla y León", "LOCAL", "SUPRAMUNICIPAL", "ENTIDAD_TERRITORIAL_CATALOGADA", None),
    "consorcio hospitalario provincial de castellon, que deja sin efecto la de 7 de abril de 2016": ("", "Castellón/Castelló", "Comunitat Valenciana", "LOCAL", "SUPRAMUNICIPAL", "PROVINCIA_NOMBRE_ENTIDAD", None),
    "consorcio provincial de pontevedra para la prestacion del servicio contra incendios y salvamento": ("", "Pontevedra", "Galicia", "LOCAL", "SUPRAMUNICIPAL", "PROVINCIA_NOMBRE_ENTIDAD", None),
    "consorcio provincial de lugo para la prestacion del servicio contra incendios y salvamento": ("", "Lugo", "Galicia", "LOCAL", "SUPRAMUNICIPAL", "PROVINCIA_NOMBRE_ENTIDAD", None),
    "consorcio de prevencion, extincion de incendios y salvamento de la isla de tenerife": ("", "Tenerife", "Canarias", "LOCAL", "SUPRAMUNICIPAL", "TERRITORIO_INSULAR", None),
}

def clave(valor): return normalizar_nombre_municipal(valor)


@lru_cache(maxsize=4)
def cargar_sedes_administrativas(ruta=RUTA_SEDES_ADMINISTRATIVAS):
    """Carga sólo coincidencias exactas del catálogo versionado de sedes."""
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    sedes = {}
    for sede in datos["sedes"]:
        clave_sede = clave(sede["administracion"])
        if clave_sede in sedes:
            raise ValueError(f"Sede administrativa duplicada: {sede['administracion']}")
        sedes[clave_sede] = sede
    return sedes


@lru_cache(maxsize=4)
def cargar_alias_sedes_administrativas(ruta=RUTA_SEDES_ADMINISTRATIVAS):
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    sedes = cargar_sedes_administrativas(ruta)
    aliases = {}
    for alias in datos.get("alias_sedes", []):
        clave_alias = clave(alias["denominacion"])
        destino = sedes.get(clave(alias["sede"]))
        if clave_alias in aliases or destino is None:
            raise ValueError(f"Alias de sede inválido: {alias['denominacion']}")
        aliases[clave_alias] = destino
    return aliases


AMBITOS_SEDES_INSTITUCIONALES = {
    "ministerio de justicia": ("ESTATAL", "ESTATAL"),
    "consejo general del poder judicial": ("ESTATAL", "ESTATAL"),
    "consejo de estado": ("ESTATAL", "ESTATAL"),
    "consejo de seguridad nuclear": ("ESTATAL", "ESTATAL"),
    "tribunal constitucional": ("ESTATAL", "ESTATAL"),
    "tribunal de cuentas": ("ESTATAL", "ESTATAL"),
    "cortes generales": ("ESTATAL", "ESTATAL"),
    "comision nacional de los mercados y la competencia": ("ESTATAL", "ESTATAL"),
    "agencia espanola de proteccion de datos": ("ESTATAL", "ESTATAL"),
}
COMUNIDADES_ADMINISTRACION_EXACTA = {
    "comunidad autonoma de andalucia": "Andalucía",
    "comunidad autonoma de aragon": "Aragón",
    "comunidad autonoma del principado de asturias": "Principado de Asturias",
    "comunidad autonoma de canarias": "Canarias",
    "comunidad autonoma de cantabria": "Cantabria",
    "comunidad autonoma de castilla la mancha": "Castilla-La Mancha",
    "comunidad autonoma de cataluna": "Cataluña/Catalunya",
    "comunidad autonoma de extremadura": "Extremadura",
    "comunidad autonoma de galicia": "Galicia",
    "comunidad autonoma de la rioja": "La Rioja",
    "comunidad autonoma de las illes balears": "Illes Balears",
    "comunidad autonoma de la region de murcia": "Región de Murcia",
    "comunidad autonoma del pais vasco": "País Vasco/Euskadi",
    "comunidad de madrid": "Comunidad de Madrid",
    "comunidad foral de navarra": "Comunidad Foral de Navarra",
}

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
        raiz = Path(__file__).resolve().parent
        if not Path(ruta_municipios).is_file(): ruta_municipios = raiz / ruta_municipios
        if not Path(ruta_alias).is_file(): ruta_alias = raiz / ruta_alias
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
    if a == "universidades": return "UNIVERSITARIO", "UNIVERSIDAD"
    if re.match(r"^(universidad|universitat|universidade)\b", a): return "UNIVERSITARIO", "UNIVERSIDAD"
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
    admin_sin_parentesis=re.sub(r"\s*\([^()]*\)\s*$", "", admin).strip()
    clave_admin=clave(admin_sin_parentesis)
    # Excepciones aprobadas, deliberadamente anteriores a los fallbacks.
    if clave_admin in MUNICIPIOS_CERRADOS:
        nombre,provincia,comunidad,normalizada=MUNICIPIOS_CERRADOS[clave_admin]
        fila=c.municipio(nombre)
        if not fila: raise RuntimeError(f"Municipio cerrado ausente del catálogo: {nombre}")
        municipio,codigo=fila["Municipio"],fila["Codigo_INE"]
        ambito,tipo="LOCAL","MUNICIPAL"; confianza="ALTA"; evidencia="MUNICIPIO_AYUNTAMIENTO"; regla="municipio_cerrado"
        return ResolucionGeografica(admin,normalizada or _limpiar(admin, True),ambito,tipo,municipio,provincia,comunidad,codigo,confianza,evidencia,regla,VERSION_CATALOGO)
    if clave_admin in ENTIDADES_CERRADAS:
        municipio,provincia,comunidad,ambito,tipo,evidencia,normalizada=ENTIDADES_CERRADAS[clave_admin]
        return ResolucionGeografica(admin,normalizada or _limpiar(admin, True),ambito,tipo,municipio,provincia,comunidad,"","ALTA",evidencia,"entidad_cerrada",VERSION_CATALOGO)
    if clave_admin in CONSEJOS_IBIZA_FORMENTERA:
        provincia,comunidad="Ibiza-Formentera","Illes Balears"
        ambito,tipo="LOCAL","INSULAR"; confianza="ALTA"; evidencia="TERRITORIO_INSULAR"; regla="consejo_ibiza_formentera"; territorial=True
    # Decisiones de catálogo manual, restringidas al paréntesis exacto.
    elif k in MANUALES:
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
    # Una comunidad identificada literalmente permite completar sólo su nivel
    # autonómico; no presupone la capital ni una sede institucional.
    if clave_admin in COMUNIDADES_ADMINISTRACION_EXACTA:
        comunidad = COMUNIDADES_ADMINISTRACION_EXACTA[clave_admin]
        ambito, tipo = "AUTONOMICO", "AUTONOMICA"
        confianza, evidencia, regla = "ALTA", "COMUNIDAD_ADMINISTRACION_EXACTA", "comunidad_administracion_exacta"
    # Ayuntamiento exacto. El contexto provincial, si existe, desambigua.
    patron=re.match(r"^(?:ayuntamiento|ajuntament|concello)\s+(?:de(?:l| la)?|d['’])\s+(.+?)(?:\s*\(|\s*,|$)",admin,re.I)
    if patron:
        nombre=patron.group(1).strip()
        # Algunos anuncios nombran un organismo dependiente inmediatamente
        # después del ayuntamiento. Se extrae sólo el municipio que precede a
        # un descriptor institucional explícito; no aplica a entidades de
        # ámbito supramunicipal ni a topónimos libres.
        nombre = re.sub(
            r"\s*(?:[-—]|,)\s*(?:organismo\s+aut[oó]nomo|patronato|instituto|gerencia|agencia|fundaci[oó]n|servicio)\b.*$",
            "", nombre, flags=re.I,
        )
        nombre = re.sub(
            r"\s+(?:organismo\s+aut[oó]nomo|patronato|instituto|gerencia|agencia|fundaci[oó]n|servicio)\s+municipal\b.*$",
            "", nombre, flags=re.I,
        )
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
    # Una sede institucional exacta tiene prioridad sobre cualquier destino
    # citado en el puesto. Las sedes TERRITORIAL se conservan para auditoría,
    # pero las reglas territoriales explícitas continúan siendo su fuente.
    sede = (cargar_sedes_administrativas().get(clave_admin)
            or cargar_alias_sedes_administrativas().get(clave_admin))
    if (not territorial and not municipio and not provincia and sede
            and sede["tipo_sede"] == "INSTITUCIONAL"):
        fila = c.codigo.get(str(sede["municipio_codigo_ine"]).zfill(5))
        if not fila:
            raise RuntimeError(f"Municipio INE inexistente en sede: {sede['municipio_codigo_ine']}")
        ambito, tipo = AMBITOS_SEDES_INSTITUCIONALES.get(clave_admin, (ambito, tipo))
        return ResolucionGeografica(
            admin, _limpiar(admin, False), ambito, tipo, fila["Municipio"], fila["Provincia"],
            fila["Comunidad"], fila["Codigo_INE"], "ALTA", "SEDE_ADMINISTRATIVA_CATALOGADA",
            "sede_administrativa_catalogada", VERSION_CATALOGO,
        )
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
    # Reglas territoriales cerradas: sólo si ninguna evidencia anterior aportó provincia.
    if not provincia:
        limpio = SUFIJO_CONVOCATORIA.sub("", admin_sin_parentesis).strip()
        ayuntamiento=re.match(r"^(?:ayuntamiento|ajuntament|concello)\s+de\s+(.+)$", limpio, re.I)
        if ayuntamiento:
            candidato=c.municipio(ayuntamiento.group(1).strip())
            if candidato:
                municipio,provincia,comunidad,codigo=candidato["Municipio"],candidato["Provincia"],candidato["Comunidad"],candidato["Codigo_INE"]
                confianza="ALTA"; evidencia="MUNICIPIO_AYUNTAMIENTO"; regla="ayuntamiento_sufijo_convocatoria"
        # Provincia de X, incluida la variante "de la Provincia de X".
        encontrados = {c.provincia(x) for x in re.findall(r"\bprovincia\s+de\s+([^,;.()]+)", limpio, re.I)} - {None}
        # Consorcio Provincial ... de X: se valida únicamente el último tramo.
        if not encontrados and re.match(r"^consorcio\s+provincial\b", limpio, re.I):
            final=re.split(r"\s+de\s+", limpio, flags=re.I)[-1]
            encontrados = {c.provincia(final)} - {None}
        if len(encontrados) == 1:
            provincia=next(iter(encontrados)); confianza="ALTA"; evidencia="PROVINCIA_NOMBRE_ENTIDAD"; regla="provincia_nombre_entidad"
        elif len(encontrados) > 1:
            return ResolucionGeografica(admin,_limpiar(admin,territorial),ambito,tipo,confianza="AMBIGUA",evidencia="CONFLICTO",regla="conflicto_provincia_nombre",conflicto="provincias_multiples")
        k_limpio=clave(limpio)
        if not provincia and k_limpio in ENTIDADES_TERRITORIALES:
            provincia=ENTIDADES_TERRITORIALES[k_limpio]; confianza="ALTA"; evidencia="ENTIDAD_TERRITORIAL_CATALOGADA"; regla="entidad_territorial_catalogada"
        if not provincia and limpio.casefold().startswith("mancomunidad"):
            for territorio, canon in MANCOMUNIDADES_TERRITORIALES.items():
                if clave(limpio).endswith(territorio):
                    provincia=canon; comunidad="Illes Balears" if canon == "Mallorca" else ""; confianza="ALTA"; evidencia="MANCOMUNIDAD_TERRITORIO"; regla="mancomunidad_territorio"; break
        if not provincia and re.match(r"^(cabildo|consejo|consell|mancomunidad)\b", limpio, re.I):
            for isla,(canon,ca) in TERRITORIOS_INSULARES.items():
                if re.search(rf"\b{re.escape(isla)}\b", clave(limpio)):
                    provincia,comunidad=canon,ca; confianza="ALTA"; evidencia="TERRITORIO_INSULAR"; regla="territorio_insular"; break
        if clave(admin_sin_parentesis) == "consorcio rector del centro universitario uned melilla":
            municipio=provincia=comunidad="Melilla"; confianza="ALTA"; evidencia="ENTIDAD_TERRITORIAL_CATALOGADA"; regla="uned_melilla"
        if limpio != admin_sin_parentesis and municipio:
            territorial=True
            admin = limpio + (f" ({par})" if par and not territorial else "")
    if provincia and not comunidad:
        filas=[x for x in c.municipios if x["Provincia"] == provincia]
        if filas: comunidad=filas[0]["Comunidad"]
    return ResolucionGeografica(admin,_limpiar(admin,territorial),ambito,tipo,municipio,provincia,comunidad,codigo,confianza,evidencia,regla,VERSION_CATALOGO)
