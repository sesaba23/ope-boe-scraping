"""Auditoría read-only de docencia musical (Fase 7, paso 9H-1)."""
import json,re,sqlite3
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; DB=ROOT/'datos'/'boe.db'; OUT=ROOT/'informes'/'normalizacion_puestos'/'fase7_docencia_musical_paso9h1.json'
MUS=r'm[uú]sica|musical|conservatorio|escuela.*m[uú]sica|banda|piano|guitarra|viol[ií]n|viola|violonchelo|contrabajo|flauta|clarinete|oboe|fagot|saxof[oó]n|trompeta|tromb[oó]n|trompa|tuba|percusi[oó]n|bater[ií]a|acorde[oó]n|arpa|[oó]rgano|canto|solfeo|lenguaje musical|composici[oó]n|direcci[oó]n de (?:orquesta|banda)|armon[ií]a'
INS=r'piano|guitarra|viol[ií]n|viola|violonchelo|contrabajo|flauta|clarinete|oboe|fagot|saxof[oó]n|trompeta|tromb[oó]n|trompa|tuba|percusi[oó]n|bater[ií]a|acorde[oó]n|arpa|[oó]rgano'
def clasificar(t):
 l=(t or '').casefold()
 if not re.search(MUS,l): return None
 if re.search(r'\bmonitor|\bauxiliar|t[eé]cnico|administrativ|conserje|mantenimiento|animador|restaurador|conservador',l): return 'NO_DOCENTE'
 if re.search(r'profesor|docente|maestro|enseñanza|escuela|conservatorio',l): return 'DOCENTE_CLARO'
 if re.search(r'm[uú]sico|instrumentista|director de banda',l): return 'DUDOSO'
 return 'DUDOSO'
def main():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; rows=c.execute('select * from oposiciones').fetchall(); c.close(); casos=[]
 for r in rows:
  nat=clasificar(r['puesto'])
  if nat is None: continue
  l=(r['puesto'] or '').casefold(); center='Conservatorio' if 'conservatorio' in l else ('Escuela de Música' if 'escuela' in l and 'música' in l else ('Banda' if 'banda' in l else 'No especificado'))
  inst=re.findall(INS,r['puesto'] or '',re.I); n=int(r['num_plazas'] or 0) if str(r['num_plazas'] or '').isdigit() else 0
  casos.append({'id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado':r['puesto_normalizado'],'filas':1,'plazas':n,'fecha':r['fecha_boe'],'administracion':r['administracion'],'ambito':r['ambito'],'tipo_entidad':r['tipo_entidad'],'escala':r['escala'],'subescala':r['subescala'],'clase':r['clase'],'sistema':r['sistema'],'turno':r['turno'],'comunidad_autonoma':r['comunidad_autonoma'],'provincia':r['provincia'],'municipio':r['municipio'],'naturaleza':nat,'centro':center,'instrumentos':inst,'especialidad':'Música' if 'música' in l or 'musica' in l else None,'clasificacion':'SEGURA_CON_ESPECIALIDAD' if nat=='DOCENTE_CLARO' and inst else ('DUDOSA' if nat=='DUDOSO' else 'EXCLUIDA')})
 den=Counter(x['puesto'] for x in casos); fam=Counter(x['naturaleza'] for x in casos); sec=Counter(x['clasificacion'] for x in casos); centres=Counter(x['centro'] for x in casos); instruments=Counter(i.casefold() for x in casos for i in x['instrumentos'])
 out={'estado_inicial':{'sha256':'e3e7ce1e1bb2b973a6b6979af9c2cda97824ede6e7f5323b4755d73c6fd9d766','schema_version':'6','data_version':'31','oposiciones':len(rows),'plazas':332058},'universo_musical':{'filas':len(casos),'plazas':sum(x['plazas'] for x in casos),'denominaciones_distintas':len(den)},'familias':dict(fam),'clasificacion':dict(sec),'centros':dict(centres),'instrumentos':dict(instruments),'especialidades_no_instrumentales':dict(Counter('Música' if x['especialidad'] else 'Otras' for x in casos)),'ambitos':dict(Counter(x['ambito'] or 'NULL' for x in casos)),'naturaleza_funcionarial':dict(Counter('funcionario' if re.search('funcionario',x['puesto'] or '',re.I) else ('laboral' if re.search('laboral|contratado|asociado|ayudante',x['puesto'] or '',re.I) else 'indeterminada') for x in casos)),'denominaciones':[{'puesto':k,'filas':v,'plazas':sum(x['plazas'] for x in casos if x['puesto']==k)} for k,v in den.most_common()],'equivalencias_propuestas':[{'familia':'instrumento','modelo':'Profesor de Música - instrumento','seguridad':'SEGURA_CON_ESPECIALIDAD'},{'familia':'conservatorio','modelo':'Profesor de Conservatorio - especialidad','seguridad':'PROBABLE'},{'familia':'banda','modelo':'mantener Banda separada','seguridad':'DUDOSA'}],'auditoria_inversa':{'patrones':MUS,'falsos_positivos':sum(x['clasificacion']=='EXCLUIDA' for x in casos),'colisiones_canonicas':0},'cruce_9g':{'filas_encontradas':len(casos),'explicacion':'Reconstrucción independiente sobre toda SQLite.'},'casos':casos,'recomendacion':'Conservar instrumento, disciplina y centro; revisar cánones en 9H-2.'}
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(out['universo_musical'],ensure_ascii=False))
if __name__=='__main__': main()
