"""Motor determinista para resolver administraciones convocantes y sus sedes.

No conoce Excel, red ni estados de procesamiento.  Los catálogos son datos
externos validados y nunca se usa coincidencia aproximada.
"""
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
import re
from urllib.parse import urlparse

import pandas as pd



def _geo():
    """Importación diferida: evita acoplar el motor al ciclo Excel/mapa."""
    from diagnostico_administraciones_historicas import (
        _entidad_y_provincia, _variantes_provincia, cargar_catalogo,
        crear_indice_municipios, resolver_entidad,
    )
    from mapa_plazas import normalizar_nombre_municipal
    return (_entidad_y_provincia, _variantes_provincia, cargar_catalogo,
            crear_indice_municipios, resolver_entidad, normalizar_nombre_municipal)


def _entidad_y_provincia(valor): return _geo()[0](valor)
def _variantes_provincia(valor): return _geo()[1](valor)
def cargar_catalogo(*args, **kwargs): return _geo()[2](*args, **kwargs)
def crear_indice_municipios(*args, **kwargs): return _geo()[3](*args, **kwargs)
def resolver_entidad(*args, **kwargs): return _geo()[4](*args, **kwargs)
def normalizar_nombre_municipal(valor): return _geo()[5](valor)

RUTA_PROVINCIAS = "datos/provincias.csv"
RUTA_SEDES_ADMINISTRACIONES = "datos/sedes_administraciones.csv"
RUTA_ALIAS_MUNICIPIOS = "datos/alias_municipios.csv"
VERSION_RESOLUCION = "1"
GENERICAS = {"", "--", "no disponible", "administración local", "administracion local"}
FIN_ENTIDAD = r"(?=,\s*(?:referente|por\s+la|para\s+la|se\s+convoca|que\s+se)|\.\s*$|$)"
PATRONES = (
    ("AYUNTAMIENTO", r"\bayuntamiento\s+de\s+(?:la\s+)?(?P<entidad>[^\n]{2,140}?)"),
    ("DIPUTACION_PROVINCIAL", r"\bdiputaci[oó]n\s+provincial\s+de\s+(?P<entidad>[^\n]{2,140}?)"),
    ("DIPUTACION", r"\bdiputaci[oó]n\s+de\s+(?P<entidad>[^\n]{2,140}?)"),
    ("UNIVERSIDAD", r"\buniversidad\s+de\s+(?P<entidad>[^\n]{2,140}?)"),
    ("CONSORCIO", r"\bconsorcio\s+(?P<entidad>[^\n]{2,140}?)"),
    ("CABILDO", r"\bcabildo\s+(?P<entidad>[^\n]{2,140}?)"),
    ("CONSEJO_INSULAR", r"\b(?:consejo|consell)\s+insular\s+(?P<entidad>[^\n]{2,140}?)"),
    ("MANCOMUNIDAD", r"\bmancomunidad\s+(?P<entidad>[^\n]{2,140}?)"),
    ("MINISTERIO", r"\bministerio\s+de\s+(?P<entidad>[^\n]{2,140}?)"),
    ("CONSEJERIA", r"\bconsejer[ií]a\s+de\s+(?P<entidad>[^\n]{2,140}?)"),
    ("GOBIERNO", r"\bgobierno\s+de\s+(?P<entidad>[^\n]{2,140}?)"),
    ("JUNTA", r"\bjunta\s+de\s+(?P<entidad>[^\n]{2,140}?)"),
    ("GENERALITAT", r"\bgeneralitat(?:\s+de)?\s+(?P<entidad>[^\n]{2,140}?)"),
    ("COMUNIDAD_AUTONOMA", r"\bcomunidad\s+aut[oó]noma\s+de\s+(?P<entidad>[^\n]{2,140}?)"),
    ("SERVICIO_SALUD", r"\bservicio\s+(?P<entidad>[^\n]{0,120}?\s+de\s+salud)"),
    ("AGENCIA", r"\bagencia\s+(?P<entidad>[^\n]{2,140}?)"),
    ("INSTITUTO", r"\binstituto\s+(?P<entidad>[^\n]{2,140}?)"),
)
PATRONES_COMPILADOS = tuple((f, re.compile(p + FIN_ENTIDAD, re.I)) for f, p in PATRONES)

@dataclass(frozen=True)
class ResolucionAdministracion:
    administracion: str = ""; familia: str = ""; estado: str = "NO_RESUELTA"
    confianza: str = "NO_RESUELTA"; metodo: str = "sin_patron_seguro"; fuente: str = "TITULO_BOE"

@dataclass(frozen=True)
class ResolucionSede:
    municipio: str = ""; provincia: str = ""; codigo_ine: str = ""
    estado: str = "NO_RESUELTA"; confianza: str = "NO_RESUELTA"; metodo: str = ""

def es_generica(valor): return str(valor or "").strip().casefold() in GENERICAS

def _normalizar_administracion(familia, entidad):
    entidad = " ".join(entidad.strip(" ,;:-").split())
    prefijos = {"AYUNTAMIENTO":"Ayuntamiento de", "DIPUTACION_PROVINCIAL":"Diputación Provincial de", "DIPUTACION":"Diputación de", "UNIVERSIDAD":"Universidad de", "MINISTERIO":"Ministerio de", "CONSEJERIA":"Consejería de", "GOBIERNO":"Gobierno de", "JUNTA":"Junta de", "COMUNIDAD_AUTONOMA":"Comunidad Autónoma de"}
    if familia in prefijos: return f"{prefijos[familia]} {entidad}"
    if familia == "GENERALITAT": return f"Generalitat {entidad}".strip()
    return f"{familia.replace('_', ' ').title()} {entidad}".strip()

def resolver_administracion(titulo, departamento=""):
    """Resuelve solo una entidad explícita del título; departamento es contexto."""
    if not isinstance(titulo, str) or not titulo.strip():
        return ResolucionAdministracion(metodo="sin_titulo")
    candidatos = []
    for familia, patron in PATRONES_COMPILADOS:
        for m in patron.finditer(titulo):
            candidato = _normalizar_administracion(familia, m.group("entidad"))
            if candidato: candidatos.append((candidato, familia, patron.pattern))
    unicos = {(x[0], x[1]): x for x in candidatos}
    if len(unicos) == 1:
        administracion, familia, regla = next(iter(unicos.values()))
        return ResolucionAdministracion(administracion, familia, "RESUELTA", "ALTA", regla)
    if len(unicos) > 1:
        return ResolucionAdministracion(familia="AMBIGUA", estado="AMBIGUA", confianza="AMBIGUA", metodo="multiples_patrones")
    return ResolucionAdministracion(metodo="sin_patron_seguro")

def _clave_administracion_sede(administracion, familia):
    texto = re.sub(r"\s*\([^()]+\)\s*$", "", str(administracion)).strip()
    if familia in {"CABILDO", "CONSEJO_INSULAR"}: texto = texto.split(",", 1)[0].strip()
    return normalizar_nombre_municipal(texto)

def cargar_capitales_provinciales(ruta=RUTA_PROVINCIAS):
    datos = pd.read_csv(ruta, sep=";", dtype=str).fillna("")
    obligatorias = {"Provincia", "Provincia_normalizada", "Capital", "Municipio_catalogo"}
    if not obligatorias.issubset(datos.columns): raise ValueError("provincias.csv no contiene el esquema requerido")
    indice = defaultdict(list)
    for fila in datos.to_dict(orient="records"):
        for variante in _variantes_provincia(fila["Provincia"]) | _variantes_provincia(fila["Provincia_normalizada"]): indice[variante].append(fila)
    return indice

def cargar_sedes_administraciones(ruta=RUTA_SEDES_ADMINISTRACIONES):
    datos = pd.read_csv(ruta, sep=";", dtype=str).fillna("")
    obligatorias = {"Administracion", "Familia", "Municipio", "Provincia", "Fuente", "Confianza"}
    if not obligatorias.issubset(datos.columns): raise ValueError("sedes_administraciones.csv no contiene el esquema requerido")
    indice = {}
    for fila in datos.to_dict(orient="records"):
        fuente = urlparse(fila["Fuente"])
        if fila["Confianza"] not in {"ALTA", "MEDIA"} or fuente.scheme != "https" or not fuente.netloc: raise ValueError("Cada sede requiere confianza ALTA/MEDIA y URL institucional HTTPS")
        clave = (_clave_administracion_sede(fila["Administracion"], fila["Familia"]), fila["Familia"])
        if clave in indice: raise ValueError("sedes_administraciones.csv contiene una sede normalizada duplicada")
        indice[clave] = fila
    return indice

def cargar_alias_municipios(ruta=RUTA_ALIAS_MUNICIPIOS, catalogo=None):
    if not Path(ruta).exists(): return {}
    datos = pd.read_csv(ruta, sep=";", dtype=str).fillna("")
    obligatorias = {"Alias", "Provincia", "Municipio_oficial", "Codigo_INE", "Fuente", "Confianza"}
    if not obligatorias.issubset(datos.columns): raise ValueError("alias_municipios.csv no contiene el esquema requerido")
    catalogo = catalogo if catalogo is not None else cargar_catalogo()
    por_codigo = {str(x["Codigo_INE"]).zfill(5): x for x in catalogo.to_dict(orient="records")}; indice = defaultdict(list)
    for fila in datos.to_dict(orient="records"):
        fuente, codigo = urlparse(fila["Fuente"]), str(fila["Codigo_INE"]).zfill(5); oficial = por_codigo.get(codigo)
        if fila["Confianza"] != "ALTA" or fuente.scheme != "https" or not fuente.netloc: raise ValueError("Cada alias requiere confianza ALTA y URL oficial HTTPS")
        if not oficial or fila["Municipio_oficial"] != oficial["Población"]: raise ValueError("Cada alias debe referir un Codigo_INE y municipio oficial válidos")
        if fila["Provincia"] and not (_variantes_provincia(fila["Provincia"]) & _variantes_provincia(oficial["Provincia"])): raise ValueError("La provincia del alias no coincide con municipios_oficial.csv")
        indice[normalizar_nombre_municipal(fila["Alias"])].append({**fila, "_oficial": oficial})
    return indice

class ResolutorAdministraciones:
    def __init__(self, ruta_provincias=RUTA_PROVINCIAS, ruta_sedes=RUTA_SEDES_ADMINISTRACIONES, ruta_alias=RUTA_ALIAS_MUNICIPIOS):
        self.catalogo = cargar_catalogo(); self.indice = crear_indice_municipios(self.catalogo)
        self.capitales = cargar_capitales_provinciales(ruta_provincias); self.sedes = cargar_sedes_administraciones(ruta_sedes)
        self.alias = cargar_alias_municipios(ruta_alias, self.catalogo)
    def _municipio(self, entidad):
        municipio, provincia, metodo, confianza = resolver_entidad(entidad, self.indice)
        if confianza == "ALTA": return municipio, provincia, metodo, confianza
        if confianza == "AMBIGUA": return "", "", metodo, confianza
        candidatos = [entidad]; base = entidad.strip()
        if not re.match(r"^(La|El|Los|Las)\s+", base, re.I): candidatos += [f"La {base}", f"El {base}", f"Los {base}", f"Las {base}"]
        validos = [x for x in [(n, *resolver_entidad(n, self.indice)) for n in candidatos] if x[4] == "ALTA"]
        if len(validos) == 1:
            nombre, municipio, provincia, metodo, confianza = validos[0]; return municipio, provincia, f"VARIANTE_ARTICULO_{metodo}" if nombre != entidad else metodo, confianza
        nombre, provincia_indicada = _entidad_y_provincia(entidad); candidatos_alias = self.alias.get(normalizar_nombre_municipal(nombre), [])
        if provincia_indicada:
            provincias = _variantes_provincia(provincia_indicada); candidatos_alias = [x for x in candidatos_alias if _variantes_provincia(x["Provincia"]) & provincias]
        if len(candidatos_alias) == 1:
            alias = candidatos_alias[0]; oficial = alias["_oficial"]; return oficial["Población"], oficial["Provincia"], f"CATALOGO_ALIAS_MUNICIPIOS_{alias['Codigo_INE']}", "ALTA"
        return "", "", "CATALOGO_MUNICIPIOS_SIN_COINCIDENCIA", "NO_RESUELTA"
    def resolver_sede(self, administracion, familia):
        entidad = re.sub(r"^(Ayuntamiento|Diputación Provincial|Diputación) de\s+", "", administracion, flags=re.I)
        if familia in {"AYUNTAMIENTO", "DIPUTACION", "DIPUTACION_PROVINCIAL"} and "," in entidad: entidad = entidad.split(",", 1)[0].strip()
        if familia in {"DIPUTACION", "DIPUTACION_PROVINCIAL"}:
            entidad = re.split(r"\s+referente\s+a\s+la\s+convocatoria\b", entidad, maxsplit=1, flags=re.I)[0]; entidad = re.split(r"-(?=[A-ZÁÉÍÓÚÜÑ])", entidad, maxsplit=1)[0].strip()
        if familia == "AYUNTAMIENTO": municipio, provincia, metodo, confianza = self._municipio(entidad); metodo = f"{familia}_{metodo}"
        elif familia in {"DIPUTACION", "DIPUTACION_PROVINCIAL"}:
            candidatas = self.capitales.get(normalizar_nombre_municipal(entidad.split("(", 1)[0].strip()), [])
            if len(candidatas) == 1:
                capital = candidatas[0]; municipio, provincia, metodo, confianza = self._municipio(f"{capital['Municipio_catalogo']} ({capital['Provincia']})")
                if confianza == "ALTA": metodo = f"CATALOGO_CAPITALES_PROVINCIA_{metodo}"
                else: municipio, provincia, metodo, confianza = "", "", "CATALOGO_CAPITALES_MUNICIPIO_NO_VALIDADO", "NO_RESUELTA"
            else: municipio, provincia, metodo, confianza = "", "", "CATALOGO_CAPITALES_PROVINCIA_SIN_COINCIDENCIA", "NO_RESUELTA"
            if confianza != "ALTA": municipio, provincia, metodo, confianza = self._municipio(entidad); metodo = f"CATALOGO_CAPITALES_FALLBACK_{metodo}"
            metodo = f"{familia}_{metodo}"
        else:
            sede = self.sedes.get((_clave_administracion_sede(administracion, familia), familia))
            if not sede or sede.get("Confianza") != "ALTA": municipio, provincia, metodo, confianza = "", "", "SEDE_NO_DEDUCIDA_SIN_CATALOGO", "NO_RESUELTA"
            else:
                municipio, provincia, metodo, confianza = self._municipio(f"{sede['Municipio']} ({sede['Provincia']})")
                metodo = f"CATALOGO_SEDES_VALIDADO_{metodo}" if confianza == "ALTA" else "CATALOGO_SEDES_MUNICIPIO_NO_VALIDADO"
                if confianza != "ALTA": municipio, provincia = "", ""
        codigo = ""
        if confianza == "ALTA":
            filas = self.indice.get(normalizar_nombre_municipal(municipio), []); candidatos = [x for x in filas if _variantes_provincia(x["Provincia"]) & _variantes_provincia(provincia)]
            if len(candidatos) == 1: codigo = str(candidatos[0].get("Codigo_INE", "")).zfill(5)
        return ResolucionSede(municipio, provincia, codigo, "RESUELTA" if confianza == "ALTA" else "NO_RESUELTA", confianza, metodo)

def resolver_sede(administracion, familia, resolutor=None): return (resolutor or ResolutorAdministraciones()).resolver_sede(administracion, familia)

def enriquecer_convocatorias(convocatorias, metadatos_publicacion, resolutor=None):
    resolutor = resolutor or ResolutorAdministraciones(); meta = metadatos_publicacion or {}
    admin = resolver_administracion(meta.get("titulo", ""), meta.get("departamento", "")); resultado = []
    for convocatoria in convocatorias or []:
        fila = dict(convocatoria); actual = fila.get("Administración") or fila.get("Administracion") or ""
        final = admin.administracion if es_generica(actual) and admin.confianza == "ALTA" else actual
        if final and final != actual: fila["Administración"] = final
        familia = admin.familia if final == admin.administracion else ""
        sede = resolutor.resolver_sede(final, familia) if final and familia else ResolucionSede(estado="NO_APLICABLE", metodo="administracion_especifica_sin_familia")
        if sede.confianza == "ALTA":
            if not fila.get("Municipio"): fila["Municipio"] = sede.municipio
            if not fila.get("Provincia"): fila["Provincia"] = sede.provincia
        resultado.append(fila)
    return resultado, admin

def extraer_administraciones_titulo(titulo):
    """Adaptador estable para el enriquecedor histórico."""
    r = resolver_administracion(titulo); return {"administracion_detectada":r.administracion,"familia":r.familia,"fuente":r.fuente,"confianza":r.confianza,"regla_utilizada":r.metodo}

def resolver_sedes(propuestas, stream=None, **rutas):
    resolutor = ResolutorAdministraciones(**{k:v for k,v in rutas.items() if k in {"ruta_provincias","ruta_sedes","ruta_alias"}}); unicas = {(x["administracion_detectada"],x["familia"]):x for x in propuestas if x["confianza"] == "ALTA"}; sedes = {}
    for (administracion, familia), ejemplo in unicas.items():
        r = resolutor.resolver_sede(administracion, familia); sedes[(administracion,familia)] = {"Administracion":administracion,"familia":familia,"Municipio":r.municipio,"Provincia":r.provincia,"metodo_resolucion":r.metodo,"confianza":r.confianza,"ejemplo_titulo":ejemplo.get("titulo","")}
    enriquecidas=[]; no_resueltas=Counter(); por_metodo=Counter(); filas_por_metodo=Counter(); causas=Counter()
    for p in propuestas:
        s=sedes.get((p["administracion_detectada"],p["familia"]),{}); x={**p,**{k:s.get(k,"") for k in ("Municipio","Provincia","metodo_resolucion")},"confianza_sede":s.get("confianza","NO_RESUELTA")}; enriquecidas.append(x)
        if x["confianza_sede"] != "ALTA":
            no_resueltas[(x["administracion_detectada"] or "SIN_ADMINISTRACION",x["familia"] or "SIN_FAMILIA")]+=x["filas_oposiciones"]
            causa="AMBIGUA" if not x["administracion_detectada"] and x["familia"]=="AMBIGUA" else "SIN_ADMINISTRACION" if not x["administracion_detectada"] else "CAPITAL_PROVINCIAL_NO_VALIDADA" if "CATALOGO_CAPITALES" in x["metodo_resolucion"] else "MUNICIPIO_NO_RESUELTO" if x["familia"]=="AYUNTAMIENTO" else "REQUIERE_SEDE_ADMINISTRATIVA"; causas[causa]+=x["filas_oposiciones"]; continue
        clave="capital_provincial" if "CATALOGO_CAPITALES" in x["metodo_resolucion"] else "catalogo_sedes" if "CATALOGO_SEDES" in x["metodo_resolucion"] else "municipio"; por_metodo[clave]+=1; filas_por_metodo[clave]+=x["filas_oposiciones"]
    return {"propuestas":enriquecidas,"sedes":list(sedes.values()),"no_resueltas":[{"Administracion":a,"familia":f,"filas_oposiciones":n} for (a,f),n in no_resueltas.most_common(100)],"resumen":{"administraciones_concretas_analizadas":len(unicas),"sedes_resueltas":sum(x["confianza"]=="ALTA" for x in sedes.values()),"filas_completamente_geolocalizables":sum(x["filas_oposiciones"] for x in enriquecidas if x["confianza_sede"]=="ALTA"),"administraciones_sin_sede":sum(x["confianza"]!="ALTA" for x in sedes.values()),"filas_sin_sede":sum(no_resueltas.values()),"sedes_resueltas_por_municipio":por_metodo["municipio"],"sedes_resueltas_por_capital_provincial":por_metodo["capital_provincial"],"sedes_resueltas_por_catalogo_sedes":por_metodo["catalogo_sedes"],"filas_resueltas_por_municipio":filas_por_metodo["municipio"],"filas_resueltas_por_capital_provincial":filas_por_metodo["capital_provincial"],"filas_resueltas_por_catalogo_sedes":filas_por_metodo["catalogo_sedes"],"filas_sin_sede_por_causa":dict(causas)}}
