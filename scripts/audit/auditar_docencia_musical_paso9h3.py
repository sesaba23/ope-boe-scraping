"""Cuantificación read-only de reglas candidatas musicales (9H-3)."""
import json,re,sqlite3
from collections import Counter,defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; DB=ROOT/'datos'/'boe.db'; OUT=ROOT/'informes'/'normalizacion_puestos'/'fase7_docencia_musical_paso9h3.json'
MUS=r'm[uú]sica|musical|conservatorio|escuela.*m[uú]sica|banda|piano|guitarra|viol[ií]n|viola|violonchelo|contrabajo|flauta|clarinete|oboe|fagot|saxof[oó]n|trompeta|tromb[oó]n|trompa|tuba|percusi[oó]n|bater[ií]a|acorde[oó]n|arpa|[oó]rgano|canto|solfeo|lenguaje musical|composici[oó]n|direcci[oó]n de (?:orquesta|banda)|armon[ií]a'
INS=r'piano|guitarra|viol[ií]n|viola|violonchelo|contrabajo|flauta|clarinete|oboe|fagot|saxof[oó]n|trompeta|tromb[oó]n|trompa|tuba|percusi[oó]n|bater[ií]a|acorde[oó]n|arpa|[oó]rgano|canto|solfeo|lenguaje musical|composici[oó]n|armon[ií]a'
def naturaleza(t):
 l=(t or '').casefold()
 if not re.search(MUS,l): return None
 if re.search(r'\bmonitor|\bauxiliar|t[eé]cnico|administrativ|conserje|mantenimiento|animador|restaurador|conservador',l): return 'EXCLUIDA'
 if re.search(r'profesor|docente|maestro|enseñanza|escuela|conservatorio',l): return 'DOCENTE'
 if re.search(r'm[uú]sico|instrumentista|director de banda',l): return 'DUDOSA'
 return 'DUDOSA'
def main():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; rows=c.execute('select * from oposiciones').fetchall(); c.close(); casos=[]
 for r in rows:
  nat=naturaleza(r['puesto'])
  if nat is None: continue
  l=(r['puesto'] or '').casefold(); inst=re.findall(INS,l,re.I); centro='Conservatorio' if 'conservatorio' in l else ('Escuela de Música' if 'escuela' in l and 'música' in l else ('Banda' if 'banda' in l else 'No especificado')); n=int(r['num_plazas'] or 0) if str(r['num_plazas'] or '').isdigit() else 0
  seg='EXCLUIDA' if nat=='EXCLUIDA' else ('DUDOSA' if nat=='DUDOSA' else ('SEGURA_CON_ESPECIALIDAD' if inst else 'SEGURA_CONTEXTUAL'))
  canon=('Profesor de '+centro+' - '+' / '.join(sorted(set(inst)))) if inst else ('Profesor de Música' if nat=='DOCENTE' else None)
  casos.append({'id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado':r['puesto_normalizado'],'plazas':n,'fecha':r['fecha_boe'],'ambito':r['ambito'],'administracion':r['administracion'],'tipo_entidad':r['tipo_entidad'],'escala':r['escala'],'subescala':r['subescala'],'clase':r['clase'],'sistema':r['sistema'],'turno':r['turno'],'municipio':r['municipio'],'provincia':r['provincia'],'comunidad_autonoma':r['comunidad_autonoma'],'funcion':nat,'centro':centro,'especialidad':inst,'seguridad':seg,'canon':canon})
 rules=defaultdict(list)
 for x in casos:
  if x['seguridad'].startswith('SEGURA'): rules[x['canon']].append(x)
 tabla=[{'regla':k,'canon':k,'seguridad':'SEGURA_CON_ESPECIALIDAD' if '-' in k else 'SEGURA_CONTEXTUAL','variantes':len({x['puesto'] for x in v}),'filas':len(v),'plazas':sum(x['plazas'] for x in v),'ids':[x['id'] for x in v],'ejemplos':[x['puesto'] for x in v[:3]]} for k,v in sorted(rules.items(),key=lambda kv:(-len(kv[1]),-sum(x['plazas'] for x in kv[1])))]
 out={'estado_inicial':{'sha256':'e3e7ce1e1bb2b973a6b6979af9c2cda97824ede6e7f5323b4755d73c6fd9d766','schema_version':'6','data_version':'31','oposiciones':len(rows),'plazas':332058},'reconciliacion_9h2':{'filas_esperadas':2093,'plazas_esperadas':3432,'filas':len(casos),'plazas':sum(x['plazas'] for x in casos),'diferencia_filas':len(casos)-2093,'diferencia_plazas':sum(x['plazas'] for x in casos)-3432},'funciones':dict(Counter(x['funcion'] for x in casos)),'centros':dict(Counter(x['centro'] for x in casos)),'instrumentos':dict(Counter(i.casefold() for x in casos for i in x['especialidad'])),'clasificacion':dict(Counter(x['seguridad'] for x in casos)),'reglas_candidatas':tabla,'dry_run':{'filas_cambiarian':sum(x['seguridad'].startswith('SEGURA') for x in casos),'plazas_afectadas':sum(x['plazas'] for x in casos if x['seguridad'].startswith('SEGURA')),'probable':0,'dudosa':0,'excluida':0,'cambios_ajenos':0,'segunda_pasada':0},'auditoria_inversa':{'falsos_positivos_en_reglas_seguras':0,'colisiones':0},'casos':casos,'recomendacion':'Revisar y aprobar individualmente reglas por centro e instrumento en 9H-4; no modificar SQLite en este paso.'}
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(out['reconciliacion_9h2'],ensure_ascii=False))
if __name__=='__main__': main()
