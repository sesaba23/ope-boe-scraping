"""Clasificación detallada read-only de puestos docentes (Fase 7, paso 9B)."""
from __future__ import annotations
import json, re, sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "datos" / "boe.db"
OUT = ROOT / "informes" / "normalizacion_puestos" / "fase7_funcionarios_docentes_paso9b.json"

FAMILIAS = {
 "UNIVERSIDAD": r"\buniversidad\b|catedr[aá]tic|titular(?:es)? de universidad",
 "MAESTROS": r"\bmaestr(?:o|a|os|as)\b",
 "SECUNDARIA": r"enseñanza secundaria|educación secundaria|\bsecundaria\b",
 "FP": r"formación profesional|profesor(?:es)? técnico|profesor(?:es)? especialista",
 "EOI": r"escuela(?:s)? oficial(?:es)? de idiomas|\bEOI\b",
 "ARTISTICAS": r"música|danza|baile|dibujo|pintura|artes plásticas|conservatorio|arte dramático|teatro",
 "DOCENTE_GENERICO": r"\bdocent(?:e|es)\b|profesor(?:a|es|as)?|educador(?:a|es|as)?|monitor(?:a|es|as)?",
}
EXCLUSIONES = {
 "MAESTRO_DE_OBRAS": r"maestro(?:s)? de obras|maestro industrial|maestro jardinero|maestro electricista",
 "APOYO_NO_DOCENTE": r"\bmonitor(?:a|es|as)?\b|\bauxiliar\b|\bt[eé]cnico(?! docente)",
}

def clasificar(texto):
 t = texto or ""
 for nombre, patron in EXCLUSIONES.items():
  if re.search(patron, t, re.I): return ("EXCLUIDA", nombre)
 for nombre, patron in FAMILIAS.items():
  if re.search(patron, t, re.I):
   if nombre == "UNIVERSIDAD":
    canon = "Catedráticos de Universidad" if re.search(r"catedr", t, re.I) else ("Profesores Titulares de Universidad" if re.search(r"titular", t, re.I) else "Funcionarios de Cuerpos Docentes Universitarios")
   else: canon = {"MAESTROS":"Maestros","SECUNDARIA":"Profesores de Enseñanza Secundaria","FP":"Profesores de Formación Profesional","EOI":"Profesores de Escuelas Oficiales de Idiomas","ARTISTICAS":"Docencia artística específica","DOCENTE_GENERICO":"Docencia/profesor genérico"}.get(nombre, nombre)
   seguridad = "SEGURA_TEXTUAL" if nombre in {"UNIVERSIDAD","MAESTROS","SECUNDARIA","FP","EOI"} else ("SEGURA_CONTEXTUAL" if nombre == "ARTISTICAS" else "PROBABLE")
   return (seguridad, nombre, canon)
 return ("DUDOSA", "OTROS", None)

def main():
 con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
 rows = con.execute("SELECT * FROM oposiciones WHERE puesto IS NOT NULL").fetchall(); con.close()
 audit=[]; fam=Counter(); security=Counter(); ambitos=Counter(); entidades=Counter(); variants=defaultdict(Counter); plazas=Counter(); sufijos=Counter()
 for r in rows:
  c=clasificar(r["puesto"])
  if c[1] == "OTROS": continue
  rec={"id":r["oposicion_id"],"puesto":r["puesto"],"puesto_normalizado_actual":r["puesto_normalizado"],"canon_propuesto":c[2] if len(c)>2 else None,"familia":c[1],"clasificacion":c[0],"regla_experimental":c[1].lower(),"evidencia":"texto_puesto","ambito":r["ambito"],"administracion":r["administracion"],"tipo_entidad":r["tipo_entidad"],"escala":r["escala"],"subescala":r["subescala"],"clase":r["clase"],"municipio":r["municipio"],"provincia":r["provincia"],"plazas":r["num_plazas"],"fecha":r["fecha_boe"],"publicacion_id":r["publicacion_id"]}
  try: nplazas = int(r["num_plazas"] or 0)
  except (TypeError, ValueError): nplazas = 0
  rec["plazas"] = nplazas
  audit.append(rec); fam[c[1]]+=1; security[c[0]]+=1; ambitos[r["ambito"] or "NULL"]+=1; entidades[r["tipo_entidad"] or "NULL"]+=1; variants[c[1]][r["puesto"]]+=1; plazas[c[1]]+=nplazas
  for key,pat in (("plantilla",r"\bplantilla\b"),("acceso",r"acceso libre"),("oep",r"\boep\b"),("funcionario",r"personal funcionario"),("concurso",r"concurso[- ]oposici[oó]n|concurso")):
   if re.search(pat,r["puesto"] or "",re.I): sufijos[key]+=1
 propuestas=[]
 for f,n in fam.items(): propuestas.append({"canon":Counter(x["canon_propuesto"] for x in audit if x["familia"]==f).most_common(1)[0][0],"familia":f,"filas":n,"plazas":plazas[f],"confianza":"DUDOSA","tipo_regla":"PROPUESTA_NO_PRODUCTIVA"})
 informe={"resumen":{"filas":len(audit),"plazas":sum(plazas.values()),"filas_cambiarian_seguras":sum(1 for x in audit if x["clasificacion"].startswith("SEGURA")),"plazas_afectadas_seguras":sum(x["plazas"] or 0 for x in audit if x["clasificacion"].startswith("SEGURA"))},"universo":{"denominaciones_distintas":len({x['puesto'] for x in audit})},"familias":dict(fam),"plazas_por_familia":dict(plazas),"ambitos":dict(ambitos),"entidades":dict(entidades),"frecuencias":dict(Counter(x['puesto'] for x in audit)),"variantes_por_familia":{k:dict(v) for k,v in variants.items()},"canones_propuestos":propuestas,"sufijos_administrativos":dict(sufijos),"clasificacion_seguridad":dict(security),"dry_run_experimental":audit,"casos_dudosos":[x for x in audit if x['clasificacion'] in {'PROBABLE','DUDOSA'}],"falsos_positivos":[x for x in audit if x['clasificacion']=='EXCLUIDA'],"precedencia":["EXCLUIDA","UNIVERSIDAD","CUERPOS_DOCENTES","ARTISTICAS","DOCENCIA_LOCAL","GENERICO"],"conclusion":"Auditoría y diseño; no se aplican reglas productivas."}
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(informe,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(informe['resumen'],ensure_ascii=False))
if __name__=='__main__': main()
