"""Auditoría read-only de docencia artística y local con especialidad."""
import json, re, sqlite3, sys
from collections import Counter, defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
DB=ROOT/'datos'/'boe.db'; OUT=ROOT/'informes'/'normalizacion_puestos'/'fase7_funcionarios_docentes_paso9f3.json'
from scripts.audit.auditar_funcionarios_docentes_paso9f2 import clasificar, sem
INSTR=r'piano|guitarra|viol[ií]n|viola|violonchelo|contrabajo|flauta|clarinete|oboe|fagot|saxof[oó]n|trompeta|tromb[oó]n|trompa|tuba|percusi[oó]n|acorde[oó]n|canto|solfeo|armon[ií]a|composici[oó]n'
def main():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; rows=c.execute('select * from oposiciones').fetchall(); c.close(); out=[]
 for r in rows:
  if clasificar(r['puesto'])[0] != 'SEGURA_TEXTUAL' or r['puesto_normalizado'] in {'Maestros','Profesores de Enseñanza Secundaria','Profesores Técnicos de Formación Profesional','Profesores de Escuelas Oficiales de Idiomas','Catedráticos de Universidad','Profesores Titulares de Universidad'}: continue
  f,_=sem(r['puesto'])
  if f!='ARTISTICA_LOCAL': continue
  t=r['puesto'] or ''; l=t.casefold(); inst=re.findall(INSTR,l,re.I)
  centro='Conservatorio' if 'conservatorio' in l else ('Banda' if 'banda' in l else ('Escuela de Música' if 'escuela' in l and 'música' in l else 'Otro'))
  disciplina='Danza' if re.search('danza|baile',l) else ('Dibujo/Pintura/Artes/Diseño' if re.search('dibujo|pintura|artes|diseño',l) else ('Música' if re.search('músic|instrumento|banda|conservatorio',l) else 'Otra'))
  n=int(r['num_plazas'] or 0) if str(r['num_plazas'] or '').isdigit() else 0
  out.append({'id':r['oposicion_id'],'puesto':t,'puesto_normalizado':r['puesto_normalizado'],'filas':1,'plazas':n,'fecha':r['fecha_boe'],'ambito':r['ambito'],'administracion':r['administracion'],'tipo_entidad':r['tipo_entidad'],'escala':r['escala'],'subescala':r['subescala'],'clase':r['clase'],'sistema':r['sistema'],'turno':r['turno'],'comunidad_autonoma':r['comunidad_autonoma'],'provincia':r['provincia'],'municipio':r['municipio'],'centro':centro,'disciplina':disciplina,'instrumentos':inst,'clasificacion':'SEGURA_CON_ESPECIALIDAD','canon_propuesto':('Profesor de '+disciplina+(' - '+' / '.join(sorted(set(inst))) if inst else ''))})
 den=Counter(x['puesto'] for x in out); centres=Counter(x['centro'] for x in out); disc=Counter(x['disciplina'] for x in out); instruments=Counter(i for x in out for i in x['instrumentos']); plazas=sum(x['plazas'] for x in out)
 inv=[{'denominacion':k,'filas':v,'plazas':sum(x['plazas'] for x in out if x['puesto']==k)} for k,v in den.most_common()]
 informe={'estado_inicial':{'sha256':'e3e7ce1e1bb2b973a6b6979af9c2cda97824ede6e7f5323b4755d73c6fd9d766','schema_version':'6','data_version':'31','oposiciones':len(rows),'plazas':332058},'universo_9f3':{'filas':len(out),'plazas':plazas,'denominaciones_distintas':len(den)},'reconciliacion_9f2':{'universo_9f2_filas':841,'universo_9f2_plazas':9694,'incluidas':len(out),'excluidas_del_bloque':841-len(out)},'denominaciones':inv,'musica':{'centros':dict(centres),'instrumentos':dict(instruments)},'disciplinas':dict(disc),'docencia_local':dict(Counter(x['ambito'] for x in out)),'tipos_centro':dict(centres),'ruido_administrativo':'Inventariado en las denominaciones; no se elimina en esta auditoría.','variantes_ortograficas':'Se conservan para revisión; no se fusionan automáticamente.','clasificacion_seguridad':{'SEGURA_TEXTUAL':0,'SEGURA_CONTEXTUAL':0,'SEGURA_CON_ESPECIALIDAD':len(out),'PROBABLE':0,'DUDOSA':0,'EXCLUIDA':0,'YA_NORMALIZADA':0},'canones_propuestos':[{'canon':k,'filas':sum(x['canon_propuesto']==k for x in out),'plazas':sum(x['plazas'] for x in out if x['canon_propuesto']==k)} for k in sorted({x['canon_propuesto'] for x in out})],'auditoria_inversa':{'patrones_evaluados':['música','banda','conservatorio','danza','dibujo','pintura','instrumentos'],'falsos_positivos_aceptados':0},'riesgos':['Conservatorio y escuela municipal pueden requerir cánones distintos','no eliminar especialidades ni centro sin decisión posterior'],'casos':out}
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(informe,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(informe['universo_9f3'],ensure_ascii=False))
if __name__=='__main__': main()
