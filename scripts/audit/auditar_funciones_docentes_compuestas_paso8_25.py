"""Auditoría reproducible y de sólo lectura de funciones docentes compuestas."""
from __future__ import annotations
import argparse, csv, hashlib, json, re, sqlite3, subprocess, sys, unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from normalizacion_puestos import normalizar_puesto
from normalizacion_contextual_puestos import normalizar_puesto_efectivo
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as auditar_global

DB = ROOT / "datos/boe.db"
PASO20 = ROOT / "informes/normalizacion_puestos/fase8_paso20_maestros.json"
OUT = ROOT / "informes/normalizacion_puestos/fase8_paso25_funciones_docentes_compuestas.json"
CSV_OUT = ROOT / "informes/normalizacion_puestos/fase8_paso25_funciones_docentes_compuestas_detalle.csv"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for b in iter(lambda: fh.read(1024 * 1024), b""): h.update(b)
    return h.hexdigest()


def estado(path=DB):
    path = Path(path); st = path.stat(); con = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        tables = {x[0] for x in con.execute("select name from sqlite_master where type='table'")}
        meta = dict(con.execute("select clave,valor from metadata"))
        count = lambda t: con.execute(f"select count(*) from [{t}]").fetchone()[0] if t in tables else None
        return {"sha256": sha(path), "tamano": st.st_size, "mtime_ns": st.st_mtime_ns, "schema_version": meta.get("schema_version"), "data_version": meta.get("data_version"), "oposiciones": count("oposiciones"), "plazas": con.execute("select coalesce(sum(num_plazas),0) from oposiciones").fetchone()[0], "publicaciones": count("publicaciones"), "busquedas": count("busquedas"), "cobertura": count("cobertura"), "integrity_check": con.execute("pragma integrity_check").fetchone()[0], "foreign_key_check": [list(x) for x in con.execute("pragma foreign_key_check")], "wal_existe": path.with_name(path.name+"-wal").exists(), "shm_existe": path.with_name(path.name+"-shm").exists()}
    finally: con.close()


def git_state():
    def run(*a): return subprocess.check_output(["git", *a], cwd=ROOT, text=True)
    return {"rama": run("branch", "--show-current"), "head": run("rev-parse", "HEAD"), "origin_main": run("rev-parse", "origin/main"), "status_short": run("status", "--short"), "diff_stat": run("diff", "--stat")}


def key(text):
    text = unicodedata.normalize("NFKD", text or "")
    return re.sub(r"\s+", " ", "".join(c for c in text if not unicodedata.combining(c)).casefold()).strip()


def cargar_paso20():
    d = json.loads(PASO20.read_text(encoding="utf-8")); m = d["microfamilias"]["funciones_docentes_compuestas"]
    rows = {r["oposicion_id"]: r for r in d["registros"] if r.get("microfamilia") == "funciones_docentes_compuestas"}
    ids = sorted(m["ids"])
    if len(ids) != 51 or m["plazas"] != 82 or sorted(rows) != ids: raise RuntimeError("PASO 20 no reconstruye 51 filas / 82 plazas")
    return d, rows, ids


def corpus(con):
    return [dict(r) for r in con.execute("""select o.oposicion_id,o.num_plazas as plazas,o.puesto,o.puesto_normalizado,
      o.administracion,o.administracion_normalizada,o.ambito,o.tipo_entidad,o.fecha_boe,o.municipio,o.provincia,
      o.escala,o.subescala,o.clase,o.sistema,o.turno,o.publicacion_id,p.titulo_original
      from oposiciones o left join publicaciones p on p.publicacion_id=o.publicacion_id""")]


def semantic(text):
    k = key(text); additional=[]
    if re.search(r"director|director/a|responsable|coordinador|jefe|encargad|secretari|tutor", k): additional.append("responsabilidad_jerarquica")
    if re.search(r"educador|tecnico|auxiliar|monitor|traductor|profesor|omic|personal de apoyo", k): additional.append("segunda_profesion_o_funcion")
    if re.search(r"guarderia|escuela|centro|aula|banda|municipal", k): additional.append("centro_o_servicio")
    if re.search(r"plantilla|laboral|jornada|tiempo parcial|fijo", k): additional.append("relacion_laboral")
    specialties=[]
    for name, pat in (("Infantil",r"infantil|guarderia"),("Música",r"musica|banda"),("Pedagogía Terapéutica",r"pedagogia terapeutica"),("Lengua Extranjera/Inglés",r"lengua extranjera|ingles"),("Educación Especial",r"educacion especial"),("Educación Primaria",r"primaria"),("Informática",r"informatica"),("EPA",r"epa")):
        if re.search(pat,k): specialties.append(name)
    if "adultos" in k or "epa" in k: sub="adultos_compuesto"
    elif "banda" in k or "musica" in k: sub="musica_compuesto"
    elif "guarderia" in k or "escuela infantil" in k: sub="centro_infantil_compuesto"
    elif "primaria" in k or specialties: sub="especialidad_docente_compuesta"
    elif "educador" in k: sub="maestro_educador"
    elif "tecnico" in k: sub="maestro_tecnico"
    else: sub="otras_funciones_compuestas"
    return sub, additional, specialties


def ficha(row, original, all_rows):
    sub, additional, specialties = semantic(row["puesto"]); k=key(row["puesto"])
    matches=[x for x in all_rows if x["puesto"]==row["puesto"]]
    # Every observed composite adds professional/centre/contractual information.
    if "adultos" in k or "epa" in k: cls="D"; reason="microfamilia adulta y/o relación laboral/segunda función; no reducir al primer término"
    else: cls="D"; reason="función adicional, especialidad, centro o responsabilidad materialmente significativa"
    return {"id":row["oposicion_id"],"puesto":row["puesto"],"puesto_normalizado":row["puesto_normalizado"],"salida_textual":normalizar_puesto(row["puesto"]),"salida_efectiva":normalizar_puesto_efectivo(row["puesto"],administracion=row["administracion"],ambito=row["ambito"],tipo_entidad=row["tipo_entidad"],escala=row["escala"],subescala=row["subescala"],sistema=row["sistema"],municipio=row["municipio"],provincia=row["provincia"]).normalizado,"plazas":row["plazas"],"ano":(row["fecha_boe"] or "")[:4],"fecha_boe":row["fecha_boe"],"administracion":row["administracion"],"provincia":row["provincia"],"escala":row["escala"],"subescala":row["subescala"],"clase":row["clase"],"publicacion_id":row["publicacion_id"],"titulo_publicacion":row["titulo_original"],"clasificacion_paso20":original.get("seguridad"),"subfamilia":sub,"categoria_docente":"Maestro/Profesor/Técnico/Educador según texto","funcion_adicional":additional,"especialidades":specialties,"relacion_laboral":bool(re.search(r"plantilla|laboral|jornada|tiempo parcial|fijo",key(row["puesto"]))),"centro_servicio":bool(re.search(r"guarderia|escuela|centro|aula|banda|municipal",key(row["puesto"]))),"repeticiones_exactas":{"filas":len(matches),"plazas":sum(float(x["plazas"] or 0) for x in matches),"ids":sorted(x["oposicion_id"] for x in matches),"anos":sorted({(x["fecha_boe"] or "")[:4] for x in matches}),"administraciones":sorted({x["administracion"] or "" for x in matches}),"canones_persistidos":sorted({x["puesto_normalizado"] or "" for x in matches})},"clasificacion_paso25":cls,"motivo_clasificacion":reason}


def auditar(ruta_bd=DB):
    before=estado(ruta_bd); norm_before=sha(ROOT/"normalizacion_puestos.py"); d, originals, ids20=cargar_paso20()
    con=sqlite3.connect(f"file:{Path(ruta_bd).resolve()}?mode=ro",uri=True); con.row_factory=sqlite3.Row
    try: rows=corpus(con)
    finally: con.close()
    by={r["oposicion_id"]:r for r in rows}
    if any(i not in by for i in ids20): raise RuntimeError("Faltan IDs del PASO 20 en SQLite actual")
    fichas=[ficha(by[i],originals[i],rows) for i in ids20]
    names={}
    for f in fichas:
        names[f["puesto"]]={"denominacion":f["puesto"],**f["repeticiones_exactas"],"canon_recalculado":f["salida_textual"],"subfamilia":f["subfamilia"],"clasificacion_final":f["clasificacion_paso25"]}
    denoms=sorted(names.values(),key=lambda x:(-x["filas"],-x["plazas"],x["denominacion"]))
    classes=Counter(f["clasificacion_paso25"] for f in fichas)
    subfamilies={}
    for f in fichas:
        g=subfamilies.setdefault(f["subfamilia"],{"filas":0,"plazas":0,"ids":[]}); g["filas"]+=1; g["plazas"]+=f["plazas"]; g["ids"].append(f["id"])
    gate=auditar_global(ruta_bd); after=estado(ruta_bd); norm_after=sha(ROOT/"normalizacion_puestos.py")
    if before!=after: raise RuntimeError("SQLite cambió durante la auditoría")
    return {"version":"fase8-paso25-v1","generado_utc":datetime.now(timezone.utc).isoformat(),"modo":"read-only","git":git_state(),"baseline":before,"reconciliacion_paso20":{"ids_paso20":ids20,"ids_paso25":sorted(f["id"] for f in fichas),"interseccion":sorted(set(ids20)&{f["id"] for f in fichas}),"solo_paso20":sorted(set(ids20)-{f["id"] for f in fichas}),"solo_paso25":sorted({f["id"] for f in fichas}-set(ids20))},"universo":{"filas":len(fichas),"plazas":sum(f["plazas"] for f in fichas),"denominaciones":len(denoms)},"registros":fichas,"denominaciones":denoms,"subfamilias":subfamilies,"funciones_adicionales":sorted({a for f in fichas for a in f["funcion_adicional"]}),"clasificacion":{"por_clase":dict(classes),"filas":len(fichas),"plazas":sum(f["plazas"] for f in fichas)},"conjuntos_a":[],"simulaciones_a":[{"conjunto":"ninguno","regla":None,"esperados":[],"obtenidos":[],"faltantes":[],"inesperados":[],"usa_fuzzy":False,"usa_ids_como_criterio":False,"motivo":"No existe conjunto A: todas las funciones adicionales son sustantivas"}],"colisiones":{"infantil_adultos_musica_taller_administrativos":"No se propone regla; no hay captura accidental","grupos_b_cerrados":"No se reabren ni absorben"},"puerta_global_paso19":{"total_discrepancias":gate["total_discrepancias"],"total_plazas_discrepantes":gate["total_plazas_discrepantes"],"cambios_reales_recalculables":gate["cambios_reales_recalculables"]["filas"],"discrepancias_contextuales_no_recalculables":gate["discrepancias_contextuales_no_recalculables"]["filas"],"discrepancias_no_clasificables_automaticamente":gate["discrepancias_no_clasificables_automaticamente"]["filas"]},"normalizador_sha256_inicial":norm_before,"normalizador_sha256_final":norm_after,"normalizador_modificado":norm_before!=norm_after,"sqlite_final":after,"sqlite_modificada":before!=after,"recomendacion_paso26":"Cerrar esta microfamilia sin aplicación y auditar Otras especialidades docentes, si el recuento real sigue siendo pequeño."}


def main():
    p=argparse.ArgumentParser(); p.add_argument("--bd",type=Path,default=DB); p.add_argument("--salida",type=Path,default=OUT); p.add_argument("--csv",type=Path,default=CSV_OUT); a=p.parse_args(); report=auditar(a.bd); a.salida.parent.mkdir(parents=True,exist_ok=True); a.salida.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    fields=["id","puesto","plazas","clasificacion_paso20","clasificacion_paso25","subfamilia","funcion_adicional","especialidades","relacion_laboral","centro_servicio","administracion","ano"]
    with a.csv.open("w",newline="",encoding="utf-8") as fh:
        w=csv.DictWriter(fh,fieldnames=fields); w.writeheader(); w.writerows({**{k:r.get(k) for k in fields},"funcion_adicional":" | ".join(r["funcion_adicional"]),"especialidades":" | ".join(r["especialidades"])} for r in report["registros"])
    print(json.dumps({"universo":report["universo"],"clasificacion":report["clasificacion"],"sqlite_modificada":report["sqlite_modificada"],"gate":report["puerta_global_paso19"]},ensure_ascii=False,indent=2))

if __name__=="__main__": main()
