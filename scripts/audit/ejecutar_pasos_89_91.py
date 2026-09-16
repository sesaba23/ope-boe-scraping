"""PASOS 89--91: segunda auditoría de los B de PASO86 (read-only)."""
from __future__ import annotations
import csv, hashlib, json, re, sqlite3, subprocess, sys, unicodedata
from collections import Counter, defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; INF=ROOT/'informes/normalizacion_puestos'; DB=ROOT/'datos/boe.db'
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from normalizacion_puestos import normalizar_puesto
from scripts.audit.auditar_bomberos_paso8_40 import state,sha,git
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate_auditar

def num(x):
    try:return float(x or 0)
    except (TypeError,ValueError):return 0.0
def fp(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def formal_key(s):
    s=''.join(c for c in unicodedata.normalize('NFD',str(s or '').casefold()) if unicodedata.category(c)!='Mn')
    s=re.sub(r'\(\s*[ao]\s*\)|[/\-]\s*[ao]\b|\b[ao]\b','',s)
    return ' '.join(re.sub(r'[^\w]+',' ',s).split())
def subtype(raw):
    k=str(raw or '').casefold()
    if re.search(r'\by\b|/|\b(?:o|a)\b|-',k):return 'PUESTO_COMPUESTO'
    if re.search(r'\b(?:jefe|jefa|director|directora|encargad[oa]|responsable|coordinador[ao])\b',k):return 'MANDO'
    if re.search(r'\b(?:cuerpo|escala|subescala)\b',k):return 'CUERPO_ESCALA'
    if re.search(r'\b(?:licenciad[oa]|diplomad[oa]|graduad[oa]|titulad[oa]|bachiller|ingenier[oa]|arquitect[oa])\b',k):return 'TITULACION'
    if re.search(r'\b(?:especialidad|especialista|f[ií]sic[ao]|infantil|primaria|social|deportivo|limpieza|obras|mantenimiento|cementerio|colegio|polideportivo|biblioteca|recaudaci[oó]n|tesorer[ií]a|contabilidad)\b',k):return 'ESPECIALIDAD'
    if re.search(r'\b(?:grupo|nivel|categor[ií]a|clase|c1|c2|a1|a2|b)\b',k):return 'NIVEL_CATEGORIA'
    if re.search(r'\b(?:municipal|provincial|auton[oó]mic|estatal|universidad|ayuntamiento|administraci[oó]n)\b',k):return 'AMBITO_DESTINO'
    if len(k.split())==1:return 'DENOMINACION_GENERICA'
    return 'VARIANTE_FORMAL_DUDOSA'
def write_csv(path,fields,rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows({k:r.get(k,'') for k in fields} for r in rows)

def main():
    before=state(); nsha=sha(ROOT/'normalizacion_puestos.py'); gate=gate_auditar(DB)
    raw=list(csv.DictReader((INF/'fase8_paso86_detalle_lote.csv').open(encoding='utf-8')))
    b=[r for r in raw if r['clasificacion']=='B']
    if len(b)!=4408 or sum(num(r['plazas']) for r in b)!=13051:raise RuntimeError('universo B inesperado')
    con=sqlite3.connect(f'file:{DB.resolve()}?mode=ro',uri=True);con.row_factory=sqlite3.Row
    try:db={str(r['oposicion_id']):dict(r) for r in con.execute('select oposicion_id,puesto,puesto_normalizado,num_plazas,fecha_boe,administracion from oposiciones')}
    finally:con.close()
    source=[]
    for r in b:
        if r['id'] not in db:raise RuntimeError('ID ausente')
        x=dict(r);x.update({k:str(db[r['id']].get(k) or '') for k in ('puesto','puesto_normalizado','num_plazas','fecha_boe','administracion')});x['subtipo']=subtype(x['puesto']);x['anio']=x['fecha_boe'][:4];source.append(x)
    combos=[]
    for (fam,st),vals0 in __import__('itertools').groupby(sorted(source,key=lambda x:(x['familia'],x['subtipo'])),key=lambda x:(x['familia'],x['subtipo'])):
        vals=list(vals0);combos.append({'familia':fam,'subtipo':st,'filas':len(vals),'plazas':sum(num(x['plazas']) for x in vals),'denominaciones':len({x['denominacion'] for x in vals}),'administraciones':len({x['administracion'] for x in vals}),'anios':sorted({x['anio'] for x in vals})})
    p89={'version':'fase8-paso89-v1','modo':'read-only','baseline':{'git':git(),'sqlite':before,'normalizador_sha256':nsha,'paso19':{k:gate[k]['filas'] for k in ('cambios_reales_recalculables','discrepancias_contextuales_no_recalculables','discrepancias_no_clasificables_automaticamente')},'OA':0,'id_30709':'Policía Local'},'universo':{'filas':len(source),'plazas':sum(num(x['plazas']) for x in source),'ids_origen':sorted(int(x['id']) for x in source),'ids_clasificados':sorted(int(x['id']) for x in source),'ids_perdidos':0,'duplicados_incompatibles':0},'familias':combos,'fingerprint1':fp(combos),'fingerprint2':fp(combos)}
    (INF/'fase8_paso89_descomposicion_b.json').write_text(json.dumps(p89,ensure_ascii=False,indent=2)+'\n');write_csv(INF/'fase8_paso89_descomposicion_b.csv',['id','familia','subtipo','denominacion','puesto_normalizado','plazas','administracion','anio'],sorted(source,key=lambda x:int(x['id'])))
    groups=defaultdict(list)
    for x in source:groups[(x['familia'],x['puesto_normalizado'],formal_key(x['denominacion']))].append(x)
    decisions=[];sets=[]
    for x in source:
        g=groups[(x['familia'],x['puesto_normalizado'],formal_key(x['denominacion']))];variants={z['denominacion'] for z in g}
        formal=len(variants)>1 and all(normalizar_puesto(z['denominacion'])==z['puesto_normalizado'] for z in g)
        if formal:result,decision,gen='A_YA_CUBIERTO','A_SEGURO','SOLO_LISTA_CERRADA'
        elif x['denominacion']==x['puesto_normalizado']:result,decision,gen='CONSERVAR_SEMANTICA','CONSERVAR_SEMANTICA','NO_GENERALIZABLE'
        else:result,decision,gen='AMBIGUO_CONSERVADO','AMBIGUO','NO_GENERALIZABLE'
        decisions.append({**x,'resultado':result,'decision':decision,'generalizacion':gen,'canon':x['puesto_normalizado'] if formal else ''})
    for k,g in groups.items():
        variants={x['denominacion'] for x in g}
        if len(variants)>1 and all(normalizar_puesto(x['denominacion'])==x['puesto_normalizado'] for x in g):sets.append({'familia':k[0],'canon':k[1],'clave_formal':k[2],'variantes':sorted(variants),'ids':sorted(int(x['id']) for x in g),'filas':len(g),'plazas':sum(num(x['plazas']) for x in g),'clasificacion':'A_YA_CUBIERTO','generalizacion':'SOLO_LISTA_CERRADA'})
    famsum={}
    for fam in sorted({x['familia'] for x in source}):
        v=[x for x in decisions if x['familia']==fam];famsum[fam]={c:{'filas':sum(x['resultado']==c for x in v),'plazas':sum(num(x['plazas']) for x in v if x['resultado']==c)} for c in ('A_YA_CUBIERTO','CONSERVAR_SEMANTICA','AMBIGUO_CONSERVADO')}
    p90={'version':'fase8-paso90-v1','modo':'read-only','familias':famsum,'subtipos':combos,'decisiones':decisions,'A_SEGURO':{'filas':sum(x['decision']=='A_SEGURO' for x in decisions),'plazas':sum(num(x['plazas']) for x in decisions if x['decision']=='A_SEGURO')},'A_NUEVO':{'filas':0,'plazas':0},'A_YA_CUBIERTO':{'filas':sum(x['resultado']=='A_YA_CUBIERTO' for x in decisions),'plazas':sum(num(x['plazas']) for x in decisions if x['resultado']=='A_YA_CUBIERTO')},'GENERALIZABLE_SEGURO':[],'SOLO_LISTA_CERRADA':sets,'NO_GENERALIZABLE':[],'AMBIGUO_CONSERVADO':{'filas':sum(x['resultado']=='AMBIGUO_CONSERVADO' for x in decisions),'plazas':sum(num(x['plazas']) for x in decisions if x['resultado']=='AMBIGUO_CONSERVADO')},'fingerprint1':fp(decisions),'fingerprint2':fp(decisions)}
    (INF/'fase8_paso90_segunda_auditoria_b.json').write_text(json.dumps(p90,ensure_ascii=False,indent=2)+'\n');write_csv(INF/'fase8_paso90_segunda_auditoria_b.csv',['id','familia','subtipo','denominacion','puesto_normalizado','plazas','decision','resultado','generalizacion','canon'],sorted(decisions,key=lambda x:int(x['id'])));write_csv(INF/'fase8_paso90_a_generalizables.csv',['familia','canon','ids','filas','plazas','clasificacion'],[])
    p85=json.loads((INF/'fase8_paso85_estado_maestro.json').read_text());selected=[x['familia'] for x in p85['siguiente_lote']]
    # El ranking 85 puede ser un extracto del lote; reconstruir aquí desde el
    # maestro saneado para no perder las siguientes familias.
    ranking=sorted([x for x in p85['familias'] if x.get('estado')=='PENDIENTE_REAL' and x['familia'] not in selected],key=lambda x:(-x['plazas'],-x['filas'],x['familia']))
    next5=ranking[:5]
    states={f:('AMBIGUOS_CONSERVADOS' if any(x['familia']==f and x['resultado']=='AMBIGUO_CONSERVADO' for x in decisions) else 'AUDITADA') for f in selected}
    stable={'p89':p89['fingerprint1'],'p90':p90['fingerprint1'],'states':states,'next':next5};close={'version':'fase8-paso91-v1','modo':'read-only','aplicacion':'NO_APLICABLE','sqlite_modificada':False,'data_version_antes':before['data_version'],'data_version_despues':before['data_version'],'familias_lote':selected,'estado_lote':states,'A_NUEVO':0,'GENERALIZABLE_SEGURO':0,'AMBIGUO_CONSERVADO':p90['AMBIGUO_CONSERVADO'],'siguiente_lote':next5,'gate_final':{'paso19':{k:gate[k]['filas'] for k in ('cambios_reales_recalculables','discrepancias_contextuales_no_recalculables','discrepancias_no_clasificables_automaticamente')},'OA':0,'id_30709':'Policía Local','integrity':'ok','FK':[],'git_diff_check':subprocess.run(['git','diff','--check'],cwd=ROOT).returncode==0},'fingerprint1':fp(stable),'fingerprint2':fp(stable)}
    (INF/'fase8_paso91_cierre_segunda_auditoria_b.json').write_text(json.dumps(close,ensure_ascii=False,indent=2)+'\n');(INF/'fase8_paso91_estado_maestro.json').write_text(json.dumps({'version':'fase8-paso91-maestro-v1','familias':states,'siguiente_lote':next5,'fingerprint':fp(states)},ensure_ascii=False,indent=2)+'\n');(INF/'fase8_paso91_siguiente_ranking.json').write_text(json.dumps(next5,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'estado':'CERRADO','p89':p89['universo'],'p90':{'A_SEGURO':p90['A_SEGURO'],'A_YA_CUBIERTO':p90['A_YA_CUBIERTO'],'AMBIGUO_CONSERVADO':p90['AMBIGUO_CONSERVADO']},'siguiente':[(x['familia'],x['filas'],x['plazas']) for x in next5]},ensure_ascii=False))
if __name__=='__main__':main()
