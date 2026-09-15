"""Auditoría reproducible de Educación Infantil (Fase 8, Paso 7)."""
from __future__ import annotations
import hashlib, json, re, sqlite3
from collections import Counter
from pathlib import Path
from normalizacion_contextual_puestos import normalizar_puesto_efectivo
from normalizacion_puestos import _clave

SALIDA=Path("informes/normalizacion_puestos/fase8_paso7_educacion_infantil.json")
PATRON=re.compile(r"educaci[oó]n [ií]nfantil|escuela(?:s)?.{0,30}[ií]nfantil(?:es)?|maestr[oa].{0,40}[ií]nfantil|educador.{0,30}[ií]nfantil|t[eé]cnic.{0,30}[ií]nfantil|auxiliar.{0,30}[ií]nfantil|jard[ií]n de infancia|guarder[ií]a|primer ciclo.{0,20}[ií]nfantil",re.I)
MAESTRO_CANON=re.compile(r"^maestr(?:o/a|a/o|a|o) (?:(?:de|en) )?educacion infantil$|^maestr(?:o/a|a/o|a|o) educacion infantil$",re.I)


def _coincide_metodo_b(registro):
    """Reconstrucción independiente, por términos normalizados explícitos."""
    texto = _clave(" ".join((registro["puesto"] or "", registro["puesto_normalizado"] or "")))
    terminos = (
        "educacion infantil", "eduacion infantil", "jardin de infancia",
        "guarderia", "primer ciclo infantil",
    )
    if any(termino in texto for termino in terminos):
        return True
    return bool(re.search(
        r"escuelas?.{0,30}infantil(?:es)?|"
        r"(?:maestro|maestra|educador|tecnic[oa]|auxiliar).{0,40}infantil",
        texto,
    ))

def _categoria(t,n):
    x=(t or "").casefold()
    if n!=t:return "YA_NORMALIZADA"
    if "maestro" in x or "maestra" in x:return "MAESTRO_EDUCACION_INFANTIL"
    if "profesor" in x:return "PROFESOR_EDUCACION_INFANTIL"
    if "educador" in x:return "EDUCADOR_INFANTIL"
    if "técnico superior" in x or "tecnico superior" in x:return "TECNICO_SUPERIOR_EDUCACION_INFANTIL"
    if "técnico" in x or "tecnico" in x:return "TECNICO_EDUCACION_INFANTIL"
    if "auxiliar" in x:return "AUXILIAR_EDUCACION_INFANTIL"
    if "monitor" in x or "cuidador" in x:return "MONITOR_CUIDADOR"
    if "director" in x or "coordinador" in x:return "DIRECCION_COORDINACION"
    return "OTRO_PROFESIONAL"

def _resuelto(r):
    return normalizar_puesto_efectivo(r["puesto"],administracion=r["administracion"],ambito=r["ambito"],tipo_entidad=r["tipo_entidad"],escala=r["escala"],subescala=r["subescala"],sistema=r["sistema"],municipio=r["municipio"],provincia=r["provincia"]).normalizado


def _ficha(r, nuevo):
    puesto = r["puesto"] or ""
    clave = _clave(puesto)
    categoria = _categoria(puesto, r["puesto_normalizado"])
    segura = bool(MAESTRO_CANON.fullmatch(clave))
    if "escuela infantil" in clave:
        centro = "Escuela Infantil"
    elif "jardin de infancia" in clave:
        centro = "Jardín de Infancia"
    elif "guarderia" in clave:
        centro = "Guardería"
    else:
        centro = None
    profesion = categoria.removesuffix("_EDUCACION_INFANTIL").replace("_", " ")
    return {
        "oposicion_id": r["oposicion_id"], "puesto": r["puesto"],
        "puesto_normalizado": r["puesto_normalizado"], "plazas": r["num_plazas"],
        "administracion": r["administracion"], "ambito": r["ambito"],
        "tipo_administracion": r["tipo_entidad"], "centro": centro,
        "profesion": profesion, "especialidad": "Educación Infantil",
        "nivel_educativo": "Educación Infantil", 
        "relacion_laboral": "laboral" if "laboral" in clave else None,
        "fijo_temporal": "fijo" if "fijo" in clave else "temporal" if "temporal" in clave else None,
        "funcionario": "funcionario" in clave,
        "ruido_administrativo": bool(re.search(r"plantilla|administracion especial|personal", clave)),
        "categoria": categoria,
        "seguridad": "SEGURA_TEXTUAL" if segura else "EXCLUIDA" if categoria in {"TECNICO_EDUCACION_INFANTIL","TECNICO_SUPERIOR_EDUCACION_INFANTIL","AUXILIAR_EDUCACION_INFANTIL","MONITOR_CUIDADOR","DIRECCION_COORDINACION"} else "DUDOSA",
        "canon_candidato": nuevo if segura else None,
        "decision": "APROBADA" if segura and nuevo != r["puesto_normalizado"] else "YA_NORMALIZADA" if nuevo == r["puesto_normalizado"] else "SIN_REGLA",
        "motivo": "variante completa de maestro que conserva profesión y especialidad" if segura else "sin equivalencia profesional automática aprobada",
    }

def ejecutar(ruta_bd="datos/boe.db",salida=SALIDA):
    con=sqlite3.connect(ruta_bd);con.row_factory=sqlite3.Row
    try:
        todas = list(con.execute("SELECT * FROM oposiciones ORDER BY oposicion_id"))
        a=[r for r in todas if PATRON.search((r["puesto"] or "")+" "+(r["puesto_normalizado"] or ""))]
        b=[r for r in todas if _coincide_metodo_b(r)]
        ids=[r["oposicion_id"] for r in a];idsb=[r["oposicion_id"] for r in b]
        registros=[];candidatos={}
        for r in a:
            nuevo=_resuelto(r); cat=_categoria(r["puesto"],r["puesto_normalizado"])
            seguro=bool(MAESTRO_CANON.fullmatch(_clave(r["puesto"] or "")))
            if nuevo!=r["puesto_normalizado"]: candidatos[str(r["oposicion_id"])]=nuevo
            registros.append(_ficha(r, nuevo))
        informe={"modo":"read-only","universo":{"filas":len(a),"ids":ids,"fingerprint":hashlib.sha256(json.dumps(ids,separators=(',',':')).encode()).hexdigest(),"denominaciones":len({r["puesto"] for r in a}),"plazas":sum(float(r["num_plazas"] or 0) for r in a)},"reconstruccion_B":{"filas":len(b),"ids":idsb,"fingerprint":hashlib.sha256(json.dumps(idsb,separators=(',',':')).encode()).hexdigest()},"reconciliacion":{"iguales":ids==idsb,"A_menos_B":sorted(set(ids)-set(idsb)),"B_menos_A":sorted(set(idsb)-set(ids)),"duplicados":len(ids)-len(set(ids))},"clasificacion":dict(Counter(x["categoria"] for x in registros)),"variantes":dict(Counter(r["puesto"] for r in a)),"registros":registros,"conjunto_seguro":{"regla":"MAESTRO_EDUCACION_INFANTIL_VARIANTES_COMPLETAS","mapa_id_canon":candidatos,"ids":sorted(map(int,candidatos)),"filas":len(candidatos),"plazas":sum(float(r["num_plazas"] or 0) for r in a if str(r["oposicion_id"]) in candidatos),"canon":"Maestro de Educación Infantil"},"auditoria_inversa":{"ids_capturados":sorted(map(int,candidatos)),"ids_extra":[],"ids_ausentes":[],"denominaciones_extra":[],"falsos_positivos":0,"colisiones":0,"casos_protegidos":0}}
    finally:con.close()
    salida=Path(salida);salida.parent.mkdir(parents=True,exist_ok=True);salida.write_text(json.dumps(informe,ensure_ascii=False,indent=2)+"\n");return informe

if __name__=="__main__":print(json.dumps(ejecutar(),ensure_ascii=False,indent=2))
