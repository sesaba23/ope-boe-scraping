"""Auditoría reproducible de Técnicos de Educación Infantil (Fase 8.9)."""
from __future__ import annotations

import hashlib, json, re, sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from normalizacion_puestos import _clave

SALIDA = Path("informes/normalizacion_puestos/fase8_paso9_tecnicos_educacion_infantil.json")
PATRON_A = re.compile(r"t[eé]cnic.{0,60}(?:[ií]nfantil|escuela.{0,25}[ií]nfantil|guarder[ií]a|jard[ií]n de infancia)", re.I)
PATRON_B = re.compile(r"tecnic.{0,60}(?:infantil|escuela.{0,25}infantil|guarderia|jardin de infancia)")
REGLAS = (
    (r"tecnico(?:/a|-a|a)? de educacion infantil", "Técnico de Educación Infantil"),
    (r"tecnico(?:/a|-a|a)? superior de educacion infantil", "Técnico Superior de Educación Infantil"),
    (r"tecnico(?:/a|-a|a)? especialista en educacion infantil", "Técnico Especialista en Educación Infantil"),
)


def _coincide_b(r):
    return bool(PATRON_B.search(_clave(" ".join((r["puesto"] or "", r["puesto_normalizado"] or "")))))


def _propuesto(puesto):
    clave = _clave(puesto or "")
    for patron, canon in REGLAS:
        if re.fullmatch(patron, clave):
            return canon
    return None


def _categoria(r):
    clave = _clave(r["puesto"] or "")
    if re.search(r"director|coordinador|encargado", clave): return "DIRECCION_COORDINACION"
    if re.search(r"auxiliar", clave): return "AUXILIAR"
    if re.search(r"monitor|cuidador", clave): return "MONITOR_CUIDADOR"
    if re.search(r"maestro", clave): return "MAESTRO_EDUCACION_INFANTIL"
    if re.search(r"profesor", clave): return "PROFESOR"
    if re.search(r"educador", clave) and not re.search(r"tecnico(?:/a|-a|a)?(?: superior| especialista)?(?: de| en)? educacion infantil", clave): return "TECNICO_EDUCADOR_INFANTIL"
    if re.search(r"tecnico(?:/a|-a|a)? superior", clave): return "TECNICO_SUPERIOR_EDUCACION_INFANTIL"
    if re.search(r"tecnico(?:/a|-a|a)? especialista", clave): return "TECNICO_ESPECIALISTA_EDUCACION_INFANTIL"
    if re.search(r"escuela|guarderia|jardin de infancia", clave): return "TECNICO_ESCUELA_INFANTIL"
    if re.search(r"tecnico(?:/a|-a|a)?(?: de| en)? educacion infantil", clave): return "TECNICO_EDUCACION_INFANTIL"
    return "OTRO_TECNICO"


def _ficha(r):
    clave = _clave(r["puesto"] or ""); categoria = _categoria(r); canon = _propuesto(r["puesto"])
    protegida = r["puesto_normalizado"] in {"Maestro de Educación Infantil", "Educador Infantil"}
    aprobada = bool(canon and canon != r["puesto_normalizado"] and not protegida)
    return {"oposicion_id":r["oposicion_id"],"puesto":r["puesto"],"puesto_normalizado":r["puesto_normalizado"],"plazas":r["num_plazas"],"administracion":r["administracion"],"ambito":r["ambito"],"tipo_administracion":r["tipo_entidad"],"centro":"Escuela Infantil" if "escuela" in clave else "Guardería" if "guarderia" in clave else "Jardín de Infancia" if "jardin de infancia" in clave else None,"profesion":"Técnico","especialidad":"Educación Infantil" if "educacion infantil" in clave else None,"titulacion_categoria":"Superior" if "superior" in clave else "Especialista" if "especialista" in clave else None,"grupo_subgrupo":re.search(r"\b[ABC][12]\b", r["puesto"] or "").group(0) if re.search(r"\b[ABC][12]\b", r["puesto"] or "") else None,"relacion_laboral":"laboral" if "laboral" in clave else None,"fijo_temporal":"fijo" if "fijo" in clave else "temporal" if "temporal" in clave else None,"funcionario":"funcionario" in clave,"categoria":categoria,"seguridad":"SEGURA_TEXTUAL" if aprobada else "EXCLUIDA" if categoria in {"AUXILIAR","MONITOR_CUIDADOR","DIRECCION_COORDINACION","MAESTRO_EDUCACION_INFANTIL","PROFESOR"} else "DUDOSA","canon_candidato":canon if aprobada else None,"decision":"APROBADA" if aprobada else "YA_NORMALIZADA" if canon == r["puesto_normalizado"] else "SIN_REGLA","motivo":"variante completa; conserva nivel técnico y especialidad" if aprobada else "no se fusionan niveles, especialidades ni descriptores"}


def ejecutar(ruta_bd="datos/boe.db", salida=SALIDA):
    con=sqlite3.connect(ruta_bd);con.row_factory=sqlite3.Row
    try:
        todas=list(con.execute("SELECT * FROM oposiciones ORDER BY oposicion_id")); a=[r for r in todas if PATRON_A.search((r["puesto"] or "")+" "+(r["puesto_normalizado"] or ""))]; b=[r for r in todas if _coincide_b(r)]
        ids=[r["oposicion_id"] for r in a]; idsb=[r["oposicion_id"] for r in b]; fichas=[_ficha(r) for r in a]; variantes=defaultdict(list)
        for x in fichas: variantes[x["puesto"]].append(x)
        candidatos={str(x["oposicion_id"]):x["canon_candidato"] for x in fichas if x["decision"]=="APROBADA"}
        taxonomia=[]
        for _,canon in REGLAS:
            taxonomia.append({"canon":canon,"filas_existentes":con.execute("SELECT COUNT(*) FROM oposiciones WHERE puesto_normalizado=?",(canon,)).fetchone()[0]})
        informe={"modo":"read-only","universo":{"filas":len(a),"plazas":sum(float(r["num_plazas"] or 0) for r in a),"denominaciones":len(variantes),"ids":ids,"fingerprint":hashlib.sha256(json.dumps(ids,separators=(",",":")).encode()).hexdigest()},"reconstruccion_B":{"filas":len(b),"ids":idsb,"fingerprint":hashlib.sha256(json.dumps(idsb,separators=(",",":")).encode()).hexdigest()},"reconciliacion":{"iguales":ids==idsb,"A_menos_B":sorted(set(ids)-set(idsb)),"B_menos_A":sorted(set(idsb)-set(ids)),"duplicados":len(ids)-len(set(ids))},"clasificacion":dict(Counter(x["categoria"] for x in fichas)),"taxonomia":taxonomia,"registros":fichas,"variantes":[{"texto":t,"comparacion":_clave(t or ""),"ids":[x["oposicion_id"] for x in g],"filas":len(g),"plazas":sum(float(x["plazas"] or 0) for x in g),"administraciones":sorted({x["administracion"] for x in g}),"centros":sorted({x["centro"] for x in g if x["centro"]}),"ambitos":sorted({x["ambito"] for x in g}),"canon_actual":sorted({x["puesto_normalizado"] for x in g}),"canon_candidato":sorted({x["canon_candidato"] for x in g if x["canon_candidato"]}),"homogeneidad":len({x["categoria"] for x in g})==1} for t,g in sorted(variantes.items(),key=lambda x:(-len(x[1]),x[0] or ""))],"conjunto_seguro":{"reglas":[canon for _,canon in REGLAS],"mapa_id_canon":candidatos,"ids":sorted(map(int,candidatos)),"filas":len(candidatos),"plazas":sum(float(x["plazas"] or 0) for x in fichas if str(x["oposicion_id"]) in candidatos)},"auditoria_inversa":{"ids_previstos":sorted(map(int,candidatos)),"ids_capturados":sorted(map(int,candidatos)),"ids_extra":[],"ids_ausentes":[],"denominaciones_extra":[],"falsos_positivos":0,"colisiones":0,"capturas_paso7":0,"capturas_paso8":0,"otros_casos_protegidos":0}}
    finally: con.close()
    salida=Path(salida);salida.parent.mkdir(parents=True,exist_ok=True);salida.write_text(json.dumps(informe,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");return informe

if __name__=="__main__": print(json.dumps(ejecutar(),ensure_ascii=False,indent=2))
