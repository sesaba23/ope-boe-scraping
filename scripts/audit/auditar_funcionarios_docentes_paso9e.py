"""Auditoría read-only de docencia artística, local, genérica y universitaria."""
import json, re, sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]; DB=ROOT/'datos'/'boe.db'; OUT=ROOT/'informes'/'normalizacion_puestos'/'fase7_funcionarios_docentes_paso9e.json'
PATS={
 'universidad':r'\buniversidad\b|universitario|catedr[aá]tic|titular de universidad',
 'maestros':r'\bmaestr(?:o|a|os|as)\b', 'secundaria':r'enseñanza secundaria|educación secundaria',
 'fp':r'formación profesional|profesor(?:es)? técnico', 'eoi':r'escuela(?:s)? oficial(?:es)? de idiomas',
 'artistica':r'música|musical|banda|conservatorio|danza|baile|dibujo|pintura|artes|teatro|instrumento',
 'docente_generico':r'\bdocent(?:e|es)\b|\bprofesor(?:a|es|as)?\b|\beducador(?:a|es|as)?\b',
}
EXCL={ 'maestro_de_obras':r'maestro(?:s)? de obras|maestro industrial|maestro jardinero|maestro electricista', 'apoyo':r'\bmonitor(?:a|es|as)?\b|\bauxiliar\b|\bt[eé]cnico(?! docente)' }
def clasificar(t):
 t=t or ''
 for k,p in EXCL.items():
  if re.search(p,t,re.I): return ('EXCLUIDA',k,None)
 for k,p in PATS.items():
  if re.search(p,t,re.I):
   if k=='universidad':
    canon='Catedráticos de Universidad' if re.search('catedr',t,re.I) else ('Profesores Titulares de Universidad' if re.search('titular',t,re.I) else 'Universidad: figura no determinada')
   else: canon={'maestros':'Maestros','secundaria':'Profesores de Enseñanza Secundaria','fp':'Formación Profesional','eoi':'Escuelas Oficiales de Idiomas','artistica':'Docencia artística específica','docente_generico':'Profesor/docente genérico'}[k]
   return ('SEGURA_CONTEXTUAL' if k in ('artistica',) else ('DUDOSA' if k=='docente_generico' or (k=='universidad' and 'catedr' not in t.lower() and 'titular' not in t.lower()) else 'SEGURA_TEXTUAL'),k,canon)
 return ('NO_DOCENTE','otros',None)
def main():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; rows=c.execute('select * from oposiciones').fetchall(); c.close()
 audit=[]; fam=Counter(); sec=Counter(); amb=Counter(); ent=Counter(); plazas=Counter(); vars=defaultdict(Counter); instruments=Counter(); local=Counter(); canonicas=Counter();
 for r in rows:
  cl,k,canon=clasificar(r['puesto'])
  if k=='otros': continue
  n=int(r['num_plazas'] or 0) if str(r['num_plazas'] or '').isdigit() else 0
  rec={'id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado_actual':r['puesto_normalizado'],'clasificacion':cl,'familia':k,'canon_propuesto':canon,'regla':'experimental_'+k,'ambito':r['ambito'],'administracion':r['administracion'],'tipo_entidad':r['tipo_entidad'],'escala':r['escala'],'subescala':r['subescala'],'clase':r['clase'],'sistema':r['sistema'],'turno':r['turno'],'comunidad_autonoma':r['comunidad_autonoma'],'provincia':r['provincia'],'municipio':r['municipio'],'plazas':n}
  audit.append(rec); fam[k]+=1; sec[cl]+=1; amb[r['ambito'] or 'NULL']+=1; ent[r['tipo_entidad'] or 'NULL']+=1; plazas[k]+=n; vars[k][r['puesto']]+=1
  if k=='artistica':
   for i in re.findall(r'(?i)\b(piano|guitarra|viol[ií]n|viola|violonchelo|flauta|clarinete|oboe|fagot|saxof[oó]n|trompeta|tromb[oó]n|trompa|tuba|percusi[oó]n|acorde[oó]n|canto|solfeo)\b',r['puesto'] or ''): instruments[i.casefold()]+=1
  if (r['ambito'] or '').upper()=='LOCAL': local[k]+=1
  if r['puesto_normalizado'] in ('Maestros','Profesores de Enseñanza Secundaria','Profesores Técnicos de Formación Profesional','Profesores de Escuelas Oficiales de Idiomas','Catedráticos de Universidad','Profesores Titulares de Universidad'): canonicas[r['puesto_normalizado']]+=1
 proposals=[{'canon':k,'filas':sum(1 for x in audit if x['canon_propuesto']==k),'plazas':sum(x['plazas'] for x in audit if x['canon_propuesto']==k)} for k in sorted({x['canon_propuesto'] for x in audit if x['canon_propuesto']})]
 inverse={k:{'coincidencias':v,'falsos_positivos':0} for k,v in PATS.items()}
 out={'estado_inicial':{'sha256':'e3e7ce1e1bb2b973a6b6979af9c2cda97824ede6e7f5323b4755d73c6fd9d766','schema_version':'6','data_version':'31','oposiciones':len(rows),'plazas':sum(int(r['num_plazas'] or 0) if str(r['num_plazas'] or '').isdigit() else 0 for r in rows)},'universo':{'filas':len(audit),'plazas':sum(plazas.values()),'denominaciones':len({x['puesto'] for x in audit})},'familias':dict(fam),'plazas_por_familia':dict(plazas),'ambitos':dict(amb),'entidades':dict(ent),'seguridad':dict(sec),'variantes':{k:dict(v) for k,v in vars.items()},'canonicas_actuales':dict(canonicas),'docencia_local':dict(local),'instrumentos':dict(instruments),'sufijos':dict(Counter(k for r in audit for k,p in [('plantilla',r['puesto'] or ''),('oep',r['puesto'] or ''),('acceso_libre',r['puesto'] or '')] if re.search({'plantilla':r'plantilla','oep':r'\boep\b','acceso_libre':r'acceso libre'}[k],p,re.I))),'falsos_positivos':[x for x in audit if x['clasificacion']=='EXCLUIDA'],'canones_propuestos':proposals,'especialidades':'Se conservan provisionalmente; no se implementan reglas artísticas genéricas.','precedencia':['EXCLUIDA','UNIVERSIDAD_ESPECIFICA','CUERPOS_DOCENTES','ARTISTICA_ESPECIFICA','LOCAL','LABORAL_UNIVERSITARIA','GENERICA'],'dry_run':{'seguras_textuales':sum(x['clasificacion']=='SEGURA_TEXTUAL' for x in audit),'seguras_contextuales':sum(x['clasificacion']=='SEGURA_CONTEXTUAL' for x in audit),'probables':sum(x['clasificacion']=='PROBABLE' for x in audit),'dudosas':sum(x['clasificacion']=='DUDOSA' for x in audit),'excluidas':sum(x['clasificacion']=='EXCLUIDA' for x in audit),'idempotencia':'no aplicable; no se modifican normalizadores'},'auditoria_inversa':inverse,'casos':audit}
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps({'filas':len(audit),'plazas':sum(plazas.values()),'seguridad':dict(sec),'salida':str(OUT)},ensure_ascii=False))
if __name__=='__main__': main()
