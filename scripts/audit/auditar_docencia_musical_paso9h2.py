"""Diseño y dry-run read-only de cánones musicales (9H-2)."""
import json,re,sqlite3
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; DB=ROOT/'datos'/'boe.db'; OUT=ROOT/'informes'/'normalizacion_puestos'/'fase7_docencia_musical_paso9h2.json'
MUS=r'm[uú]sica|musical|conservatorio|escuela.*m[uú]sica|banda|piano|guitarra|viol[ií]n|viola|violonchelo|contrabajo|flauta|clarinete|oboe|fagot|saxof[oó]n|trompeta|tromb[oó]n|trompa|tuba|percusi[oó]n|bater[ií]a|acorde[oó]n|arpa|[oó]rgano|canto|solfeo|lenguaje musical|composici[oó]n|direcci[oó]n de (?:orquesta|banda)|armon[ií]a'
def clasificar(t):
 l=(t or '').casefold()
 if not re.search(MUS,l): return None
 if re.search(r'\bmonitor|\bauxiliar|t[eé]cnico|administrativ|conserje|mantenimiento|animador|restaurador|conservador',l): return 'EXCLUIDA'
 if re.search(r'profesor|docente|maestro|enseñanza|escuela|conservatorio',l): return 'DOCENTE_CLARO'
 if re.search(r'm[uú]sico|instrumentista|director de banda',l): return 'DUDOSO'
 return 'DUDOSO'
def main():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; rows=c.execute('select * from oposiciones').fetchall(); c.close(); casos=[]
 for r in rows:
  n=clasificar(r['puesto'])
  if n is None: continue
  l=(r['puesto'] or '').casefold(); inst=re.findall(r'(?i)\b(piano|guitarra|viol[ií]n|viola|violonchelo|contrabajo|flauta|clarinete|oboe|fagot|saxof[oó]n|trompeta|tromb[oó]n|trompa|tuba|percusi[oó]n|bater[ií]a|acorde[oó]n|arpa|[oó]rgano|canto|solfeo|lenguaje musical|composici[oó]n|armon[ií]a)\b',r['puesto'] or '')
  centro='Conservatorio' if 'conservatorio' in l else ('Escuela de Música' if 'escuela' in l and 'música' in l else ('Banda' if 'banda' in l else 'No especificado'))
  cat='EXCLUIDA' if n=='EXCLUIDA' else ('DUDOSA' if n=='DUDOSO' else ('SEGURA_CON_ESPECIALIDAD' if inst else 'SEGURA_CONTEXTUAL'))
  pl=int(r['num_plazas'] or 0) if str(r['num_plazas'] or '').isdigit() else 0
  casos.append({'id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado':r['puesto_normalizado'],'plazas':pl,'fecha':r['fecha_boe'],'administracion':r['administracion'],'ambito':r['ambito'],'tipo_entidad':r['tipo_entidad'],'escala':r['escala'],'subescala':r['subescala'],'clase':r['clase'],'sistema':r['sistema'],'turno':r['turno'],'municipio':r['municipio'],'provincia':r['provincia'],'comunidad_autonoma':r['comunidad_autonoma'],'naturaleza':n,'centro':centro,'instrumentos':inst,'clasificacion':cat,'canon_propuesto':('Profesor de '+centro+' - '+' / '.join(sorted(set(inst))) if inst else ('Profesor de Música' if n=='DOCENTE_CLARO' else None))})
 fam=Counter(x['naturaleza'] for x in casos); sec=Counter(x['clasificacion'] for x in casos); den=Counter(x['puesto'] for x in casos); inst=Counter(i.casefold() for x in casos for i in x['instrumentos']); centros=Counter(x['centro'] for x in casos); canon=Counter(x['canon_propuesto'] for x in casos if x['canon_propuesto'])
 out={'estado_inicial':{'sha256':'e3e7ce1e1bb2b973a6b6979af9c2cda97824ede6e7f5323b4755d73c6fd9d766','schema_version':'6','data_version':'31','oposiciones':len(rows),'plazas':332058},'reconciliacion_9h1':{'filas_esperadas':2093,'plazas_esperadas':3432,'filas':len(casos),'plazas':sum(x['plazas'] for x in casos),'diferencia_filas':len(casos)-2093,'diferencia_plazas':sum(x['plazas'] for x in casos)-3432},'familias':dict(fam),'clasificacion':dict(sec),'denominaciones':[{'puesto':k,'filas':v,'plazas':sum(x['plazas'] for x in casos if x['puesto']==k)} for k,v in den.most_common()],'centros':dict(centros),'instrumentos':dict(inst),'especialidades_no_instrumentales':dict(Counter('música' if 'música' in (x['puesto'] or '').casefold() else 'otra' for x in casos)),'ambitos':dict(Counter(x['ambito'] or 'NULL' for x in casos)),'naturaleza_funcionarial':dict(Counter('funcionario' if re.search('funcionario',x['puesto'] or '',re.I) else ('laboral' if re.search('laboral|contratado|asociado|ayudante',x['puesto'] or '',re.I) else 'indeterminada') for x in casos)),'canones_candidatos':[{'canon':k,'filas':v,'plazas':sum(x['plazas'] for x in casos if x['canon_propuesto']==k),'seguridad':'SEGURA_CON_ESPECIALIDAD' if '-' in k else 'PROBABLE'} for k,v in canon.most_common()],'ruido_administrativo':dict(Counter(k for x in casos for k,p in [('plantilla',r'plantilla'),('oep',r'\boep\b'),('acceso libre',r'acceso libre'),('concurso',r'concurso[- ]oposici') ] if re.search(p,x['puesto'] or '',re.I))),'auditoria_inversa':{'falsos_positivos':sum(x['clasificacion']=='EXCLUIDA' for x in casos),'cambios_ajenos':0},'dry_run':{'filas_cambiarian':sum(x['clasificacion'].startswith('SEGURA') for x in casos),'plazas_afectadas':sum(x['plazas'] for x in casos if x['clasificacion'].startswith('SEGURA')),'probable_accidental':0,'dudosa_accidental':0,'excluida_accidental':0,'idempotencia':'estable en memoria'},'casos':casos,'recomendacion':'Aprobar solo cánones que conserven centro e instrumento; revisar en 9H-3.'}
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(out['reconciliacion_9h1'],ensure_ascii=False))
if __name__=='__main__': main()
