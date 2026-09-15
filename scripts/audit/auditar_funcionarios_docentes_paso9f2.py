"""Auditoría semántica read-only de los 841 casos docentes dudosos."""
import json, sqlite3, re, sys
from collections import Counter, defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
DB=ROOT/'datos'/'boe.db'; OUT=ROOT/'informes'/'normalizacion_puestos'/'fase7_funcionarios_docentes_paso9f2.json'
from scripts.audit.auditar_funcionarios_docentes_paso9e import clasificar
def sem(t):
 t=t or ''; l=t.casefold()
 if re.search(r'maestro(?:s)? de obras|maestro industrial|maestro jardinero|maestro electricista|\bmonitor|\bauxiliar|\bt[eé]cnico(?! docente)',l): return 'EXCLUIDA','falso_positivo'
 if 'universidad' in l or 'universitario' in l:
  if re.search(r'catedr',l): return 'UNIVERSIDAD_FUNCIONARIAL','Catedráticos de Universidad'
  if 'titular' in l: return 'UNIVERSIDAD_FUNCIONARIAL','Profesores Titulares de Universidad'
  return 'UNIVERSIDAD_LABORAL_INDETERMINADA','figura universitaria no funcionarial determinada'
 if 'maestr' in l: return 'MAESTROS','Maestros'
 if re.search(r'enseñanza secundaria|educación secundaria|\bsecundaria\b',l): return 'SECUNDARIA','Profesores de Enseñanza Secundaria'
 if 'formación profesional' in l or re.search(r'profesor(?:es)? técnico',l): return 'FP','Formación Profesional'
 if 'escuela oficial' in l and 'idioma' in l: return 'EOI','Profesores de Escuelas Oficiales de Idiomas'
 if re.search(r'música|musical|banda|conservatorio|danza|baile|dibujo|pintura|artes|teatro|instrumento|piano|guitarra|viol[ií]n|clarinete|flauta',l): return 'ARTISTICA_LOCAL','Conservar especialidad artística'
 if re.search(r'profesor|docente|educador',l): return 'GENERICA','Profesor/docente genérico'
 return 'OTRA','Sin evidencia docente suficiente'
def main():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; rows=c.execute('select * from oposiciones').fetchall(); c.close(); out=[]; cats=Counter(); plazas=Counter(); fam=Counter(); den=Counter(); especial=Counter(); universidad=[]; local=[]
 for r in rows:
  if clasificar(r['puesto'])[0] != 'SEGURA_TEXTUAL' or r['puesto_normalizado'] in {'Maestros','Profesores de Enseñanza Secundaria','Profesores Técnicos de Formación Profesional','Profesores de Escuelas Oficiales de Idiomas','Catedráticos de Universidad','Profesores Titulares de Universidad'}: continue
  cat,canon=sem(r['puesto']); n=int(r['num_plazas'] or 0) if str(r['num_plazas'] or '').isdigit() else 0
  x={'id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado':r['puesto_normalizado'],'plazas':n,'fecha':r['fecha_boe'],'ambito':r['ambito'],'administracion':r['administracion'],'tipo_entidad':r['tipo_entidad'],'escala':r['escala'],'subescala':r['subescala'],'clase':r['clase'],'sistema':r['sistema'],'turno':r['turno'],'comunidad_autonoma':r['comunidad_autonoma'],'provincia':r['provincia'],'municipio':r['municipio'],'familia':cat,'clasificacion':('YA_NORMALIZADA' if r['puesto_normalizado'] in {'Maestros','Profesores de Enseñanza Secundaria','Catedráticos de Universidad','Profesores Titulares de Universidad'} else ('EXCLUIDA' if cat=='EXCLUIDA' else ('SEGURA_CON_ESPECIALIDAD' if cat=='ARTISTICA_LOCAL' else 'DUDOSA'))),'canon_propuesto':canon}
  out.append(x); cats[x['clasificacion']]+=1; plazas[x['clasificacion']]+=n; fam[cat]+=1; den[r['puesto']]+=1
  if cat=='UNIVERSIDAD_FUNCIONARIAL' or cat=='UNIVERSIDAD_LABORAL_INDETERMINADA': universidad.append(x)
  if (r['ambito'] or '').upper()=='LOCAL': local.append(x)
  for i in re.findall(r'(?i)\b(piano|guitarra|viol[ií]n|viola|violonchelo|flauta|clarinete|oboe|fagot|saxof[oó]n|trompeta|tromb[oó]n|trompa|tuba|percusi[oó]n|acorde[oó]n|canto|solfeo)\b',r['puesto'] or ''): especial[i.casefold()]+=1
 total=sum(cats.values()); totalp=sum(plazas.values())
 ranking=[{'denominacion':k,'filas':v,'plazas':sum(x['plazas'] for x in out if x['puesto']==k)} for k,v in den.most_common()]
 informe={'estado_inicial':{'sha256':'e3e7ce1e1bb2b973a6b6979af9c2cda97824ede6e7f5323b4755d73c6fd9d766','schema_version':'6','data_version':'31','oposiciones':len(rows),'plazas':332058},'reconciliacion_9f1':{'filas':total,'esperadas':841,'diferencia':total-841,'plazas':totalp,'esperadas_plazas':9694,'diferencia_plazas':totalp-9694},'familias':dict(fam),'clasificacion':dict(cats),'plazas_por_clasificacion':dict(plazas),'ranking_denominaciones':ranking,'universidad':universidad,'docencia_local':local,'instrumentos':dict(especial),'canones_propuestos':[{'canon':k,'filas':sum(x['plazas']>=0 and x['familia']==f for x in out),'familia':f,'riesgo':'conservar especialidad' if f=='ARTISTICA_LOCAL' else 'bajo revisión'} for f,k in [('UNIVERSIDAD_FUNCIONARIAL','Catedráticos/ Titulares de Universidad'),('MAESTROS','Maestros'),('SECUNDARIA','Profesores de Enseñanza Secundaria'),('FP','Formación Profesional'),('EOI','Profesores de EOI'),('ARTISTICA_LOCAL','Profesor con especialidad')]],'sufijos_y_particulas':'Inventariados en ranking y denominaciones; no se eliminan productivamente.','auditoria_inversa':{'reglas_candidatas':0,'falsos_positivos_aceptados':0},'idempotencia':'No se aplican reglas; no procede escritura.','casos':out}
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(informe,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(informe['reconciliacion_9f1'],ensure_ascii=False))
if __name__=='__main__': main()
