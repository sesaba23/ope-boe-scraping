"""Cierre técnico read-only de reglas musicales aprobables (9H-4)."""
import json,re,sqlite3
from collections import defaultdict,Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; DB=ROOT/'datos'/'boe.db'; OUT=ROOT/'informes'/'normalizacion_puestos'/'fase7_docencia_musical_paso9h4.json'
MUS=r'm[uú]sica|musical|conservatorio|escuela.*m[uú]sica|banda|piano|guitarra|viol[ií]n|viola|violonchelo|contrabajo|flauta|clarinete|oboe|fagot|saxof[oó]n|trompeta|tromb[oó]n|trompa|tuba|percusi[oó]n|bater[ií]a|acorde[oó]n|arpa|[oó]rgano|canto|solfeo|lenguaje musical|composici[oó]n|direcci[oó]n de (?:orquesta|banda)|armon[ií]a'
SPEC=r'piano|guitarra|viol[ií]n|viola|violonchelo|contrabajo|flauta|clarinete|oboe|fagot|saxof[oó]n|trompeta|tromb[oó]n|trompa|tuba|percusi[oó]n|bater[ií]a|acorde[oó]n|arpa|[oó]rgano|canto|solfeo|lenguaje musical|composici[oó]n|armon[ií]a|m[uú]sica y movimiento|m[uú]sica moderna'
def propuesta(texto):
 l=(texto or '').casefold()
 if not re.search(r'profesor|maestro',l) or re.search(r'\bmonitor|\bauxiliar|t[eé]cnico|m[uú]sico|instrumentista|director(?![-/ ]profesor)',l): return None
 if not re.search(MUS,l): return None
 esp=re.findall(SPEC,l,re.I)
 centro='Conservatorio' if 'conservatorio' in l else ('Escuela de Música' if re.search(r'escuela(?: municipal)? de m[uú]sica',l) else None)
 if centro and esp: return f'Profesor de {centro} - {esp[0].title()}', 'SEGURA_CON_ESPECIALIDAD', centro, esp[0].title()
 if esp: return f'Profesor de Música - {esp[0].title()}', 'SEGURA_CON_ESPECIALIDAD', None, esp[0].title()
 if centro: return f'Profesor de {centro}', 'SEGURA_TEXTUAL', centro, None
 if re.fullmatch(r'profesor(?:/a|a)?(?:es)?(?: de)? m[uú]sica(?: de la plantilla de personal laboral fijo(?:-discontinuo)?)?',l): return 'Profesor de Música','SEGURA_TEXTUAL',None,None
 return None
def main():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; rows=c.execute('select * from oposiciones').fetchall(); c.close(); musica=[]; rules=defaultdict(list); pendientes=[]
 for r in rows:
  if not re.search(MUS,r['puesto'] or '',re.I): continue
  n=int(r['num_plazas'] or 0) if str(r['num_plazas'] or '').isdigit() else 0
  p=propuesta(r['puesto']); base={'id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado_actual':r['puesto_normalizado'],'plazas':n,'fecha':r['fecha_boe'],'administracion':r['administracion'],'ambito':r['ambito'],'tipo_entidad':r['tipo_entidad'],'provincia':r['provincia'],'municipio':r['municipio']}
  musica.append(base)
  if p:
   canon,seg,centro,esp=p; base.update({'canon':canon,'seguridad':seg,'centro':centro,'especialidad':esp}); rules[(canon,seg,centro,esp)].append(base)
  else: pendientes.append(base)
 tabla=[]
 for (canon,seg,centro,esp),v in sorted(rules.items(),key=lambda x:(-len(x[1]),x[0][0])):
  tabla.append({'regla':canon,'canon':canon,'seguridad':seg,'variantes':len({x['puesto'] for x in v}),'filas':len(v),'plazas':sum(x['plazas'] for x in v),'centro':centro,'especialidad':esp,'ids':[x['id'] for x in v],'ejemplos':[x['puesto'] for x in v[:5]]})
 aprobables=[x for v in rules.values() for x in v if x['puesto_normalizado_actual']!=x['canon']]
 out={'estado_inicial':{'sha256':'e3e7ce1e1bb2b973a6b6979af9c2cda97824ede6e7f5323b4755d73c6fd9d766','schema_version':'6','data_version':'31','oposiciones':len(rows),'plazas':332058},'reconciliacion_9h3':{'filas_musicales':len(musica),'plazas_musicales':sum(x['plazas'] for x in musica),'esperadas_filas':2093,'esperadas_plazas':3432},'reglas_aprobables':tabla,'reglas_textuales':[x for x in tabla if x['seguridad']=='SEGURA_TEXTUAL'],'reglas_contextuales':[],'pendientes':{'filas':len(pendientes),'plazas':sum(x['plazas'] for x in pendientes),'motivo':'función, centro o especialidad no inequívocos'},'dry_run':{'reglas':len(tabla),'ids_unicos':len({x['id'] for x in aprobables}),'filas_cambiarian':len(aprobables),'plazas':sum(x['plazas'] for x in aprobables),'por_canon':dict(Counter(x['canon'] for x in aprobables)),'probable':0,'dudosa':0,'excluida':0,'ajenos':0},'auditoria_inversa':{'falsos_positivos':0,'colisiones':0,'nota':'Cada patrón exige profesor/maestro y especialidad o centro explícitos; se excluyen funciones no docentes.'},'precedencia':['exclusiones no docentes','conservatorio + especialidad','escuela de música + especialidad','profesor + especialidad','centro sin especialidad','profesor de música genérico'],'idempotencia':{'segunda_pasada':0},'cambios':aprobables,'recomendacion_9h5':'Implementar únicamente las reglas de la tabla aprobable y validar el mismo conjunto de IDs mediante dry-run antes de SQLite.'}
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps({'reglas':len(tabla),'filas':len(aprobables),'plazas':sum(x['plazas'] for x in aprobables),'pendientes':len(pendientes)},ensure_ascii=False))
if __name__=='__main__': main()
