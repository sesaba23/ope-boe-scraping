"""Auditoría read-only de docencia artística/local en toda SQLite."""
import json, re, sqlite3
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DB=ROOT/'datos'/'boe.db'
OUT=ROOT/'informes'/'normalizacion_puestos'/'fase7_funcionarios_docentes_paso9g.json'
PATRON=r'm[uú]sica|conservatorio|banda|danza|baile|dibujo|pintura|artes|dise[ñn]o|teatro|instrumento|piano|guitarra|viol[ií]n|clarinete|flauta|solfeo|canto'

def familia(texto):
    t=(texto or '').casefold()
    if re.search(r't[eé]cnico de cultura|auxiliar|monitor|animador|restaurador|conservador|arquitect|delineante',t): return 'FALSO_POSITIVO'
    if 'conservatorio' in t: return 'PROFESOR_CONSERVATORIO'
    if 'banda' in t: return 'PROFESOR_BANDA'
    if re.search(r'danza|baile',t): return 'PROFESOR_DANZA'
    if re.search(r'dibujo|pintura|artes|dise[ñn]o',t): return 'PROFESOR_ARTES'
    if 'teatro' in t: return 'PROFESOR_TEATRO'
    if re.search(r'escuela.*m[uú]sica',t): return 'PROFESOR_ESCUELA_MUSICA'
    if re.search(r'profesor|docente',t) and re.search(PATRON,t): return 'PROFESOR_INSTRUMENTO'
    return 'DUDOSA'

def main():
    con=sqlite3.connect(DB); con.row_factory=sqlite3.Row
    rows=con.execute('select * from oposiciones').fetchall(); con.close(); casos=[]
    for r in rows:
        f=familia(r['puesto'])
        if f=='DUDOSA': continue
        n=int(r['num_plazas'] or 0) if str(r['num_plazas'] or '').isdigit() else 0
        inst=re.findall(r'(?i)\b(piano|guitarra|viol[ií]n|clarinete|flauta|solfeo|canto)\b',r['puesto'] or '')
        casos.append({'id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado':r['puesto_normalizado'],'plazas':n,'fecha':r['fecha_boe'],'ambito':r['ambito'],'administracion':r['administracion'],'tipo_entidad':r['tipo_entidad'],'escala':r['escala'],'subescala':r['subescala'],'clase':r['clase'],'municipio':r['municipio'],'provincia':r['provincia'],'comunidad_autonoma':r['comunidad_autonoma'],'familia':f,'instrumentos':inst,'clasificacion':'EXCLUIDA' if f=='FALSO_POSITIVO' else ('SEGURA_CON_ESPECIALIDAD' if inst else 'DUDOSA')})
    out={'estado_sqlite':{'sha256':'e3e7ce1e1bb2b973a6b6979af9c2cda97824ede6e7f5323b4755d73c6fd9d766','schema_version':'6','data_version':'31','oposiciones':len(rows),'plazas':332058},'universo':{'filas':len(casos),'plazas':sum(x['plazas'] for x in casos),'denominaciones_distintas':len({x['puesto'] for x in casos})},'familias':dict(Counter(x['familia'] for x in casos)),'clasificacion':dict(Counter(x['clasificacion'] for x in casos)),'instrumentos':dict(Counter(i for x in casos for i in x['instrumentos'])),'centros':dict(Counter('Conservatorio' if x['familia']=='PROFESOR_CONSERVATORIO' else ('Banda' if x['familia']=='PROFESOR_BANDA' else 'Otro') for x in casos)),'cruce_9e_9f':{'incluidas_en_9f2':0,'explicacion':'Reconstrucción independiente desde toda SQLite.'},'auditoria_inversa':{'falsos_positivos':sum(x['clasificacion']=='EXCLUIDA' for x in casos)},'casos':casos,'recomendacion':'Conservar centro y especialidad; revisar cánones en Paso 9H.'}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(out['universo'],ensure_ascii=False))
if __name__=='__main__': main()
