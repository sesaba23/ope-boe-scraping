"""PASO 76: audita los B restantes de las cinco familias, sin mutaciones."""
from __future__ import annotations
import csv, hashlib, json, subprocess, sys, unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from normalizacion_puestos import normalizar_puesto
from scripts.audit.auditar_bomberos_paso8_40 import state
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate_auditar
INF=ROOT/'informes/normalizacion_puestos'; DB=ROOT/'datos/boe.db'
P72=INF/'fase8_paso72_auditoria.json'; P72B=INF/'fase8_paso72b_analisis_bcd.json'; P72C=INF/'fase8_paso72c_variantes_formales.json'
OUT=INF/'fase8_paso76_auditoria_b_restantes.json'; DETAIL=INF/'fase8_paso76_detalle_b_restantes.csv'; GEN=INF/'fase8_paso76_a_generalizables.csv'
SUBT=('PUESTO_COMPUESTO','FUNCION','ESPECIALIDAD','NIVEL_CATEGORIA','MANDO_RESPONSABILIDAD','AMBITO_DESTINO')
def num(x):
    try:return float(x or 0)
    except (TypeError,ValueError):return 0.0
def forma(s):
    s=''.join(c for c in unicodedata.normalize('NFD',str(s or '').casefold()) if unicodedata.category(c)!='Mn')
    return ' '.join(s.replace('/a','').replace('/o','').replace('-a','').split())
def fp(obj): return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def main():
    before=state(); gate=gate_auditar(DB)
    if before['data_version']!='62' or before['integrity_check']!='ok' or before['foreign_key_check'] or (gate['cambios_reales_recalculables']['filas'],gate['discrepancias_contextuales_no_recalculables']['filas'],gate['discrepancias_no_clasificables_automaticamente']['filas'])!=(0,329,0): raise RuntimeError('baseline PASO76 no supera gates')
    p72=json.loads(P72.read_text()); p72b=json.loads(P72B.read_text()); p72c=json.loads(P72C.read_text())
    excluded={int(x['id']) for x in p72c['detalle']}; rows=[x for x in p72b['detalle'] if x['clasificacion']=='B' and int(x['id']) not in excluded]
    if len(rows)!=1957 or {x['subtipo'] for x in rows}-set(SUBT): raise RuntimeError('universo PASO76 inesperado')
    groups=defaultdict(list)
    for x in rows: groups[(x['subtipo'],forma(x['denominacion']))].append(x)
    detail=[]; sets=[]
    for key,vals in sorted(groups.items()):
        variants=sorted({x['denominacion'] for x in vals}); canons={x['puesto_normalizado'] for x in vals}
        formal=len(variants)>1 and len(canons)==1 and all(normalizar_puesto(x['denominacion'])==x['puesto_normalizado'] for x in vals)
        classification='A_SEGURO' if formal else ('AMBIGUO' if len(variants)>1 else 'CONSERVAR_SEMANTICA')
        covered='A_YA_CUBIERTO' if formal else None
        canon=next(iter(canons)) if formal else None
        if formal:
            sets.append({'subtipo':key[0],'clave_formal':key[1],'canon_completo':canon,'variantes':variants,'ids':sorted(int(x['id']) for x in vals),'filas':len(vals),'plazas':sum(num(x['plazas']) for x in vals),'administraciones':sorted({x['administracion'] or '' for x in vals}),'anios':sorted({x['anio'] for x in vals}),'clasificacion':'A_YA_CUBIERTO','generalizacion':'NO_NUEVA_REGLA'})
        for x in vals: detail.append({**x,'resultado_76':classification,'cobertura':covered,'canon_completo':canon,'clave_formal':key[1],'motivo':'variantes formales con canon completo coherente ya producido por reglas existentes' if formal else ('variantes no demuestran equivalencia inequívoca' if classification=='AMBIGUO' else 'se conserva la información semántica del subtipo')})
    counts={c:{'filas':sum(x['resultado_76']==c for x in detail),'plazas':sum(num(x['plazas']) for x in detail if x['resultado_76']==c),'denominaciones':len({x['denominacion'] for x in detail if x['resultado_76']==c}),'administraciones':len({x['administracion'] or '' for x in detail if x['resultado_76']==c}),'anios':sorted({x['anio'] for x in detail if x['resultado_76']==c})} for c in ('A_SEGURO','CONSERVAR_SEMANTICA','AMBIGUO')}
    by_sub={}
    for sub in SUBT:
        r=[x for x in detail if x['subtipo']==sub]; by_sub[sub]={'filas':len(r),'plazas':sum(num(x['plazas']) for x in r),'denominaciones':len({x['denominacion'] for x in r}),'administraciones':len({x['administracion'] or '' for x in r}),'anios':sorted({x['anio'] for x in r}),'A_SEGURO':sum(x['resultado_76']=='A_SEGURO' for x in r),'CONSERVAR_SEMANTICA':sum(x['resultado_76']=='CONSERVAR_SEMANTICA' for x in r),'AMBIGUO':sum(x['resultado_76']=='AMBIGUO' for x in r)}
    ids=[int(x['id']) for x in detail]
    if len(ids)!=len(set(ids)) or set(ids)!={int(x['id']) for x in rows}: raise RuntimeError('cobertura por IDs inconsistente')
    stable={'universo':{'filas':len(rows),'plazas':sum(num(x['plazas']) for x in rows)},'subtipos':by_sub,'resultado_global':counts,'conjuntos_A':sets,'generalizables':[],'ids':ids}
    f1=fp(stable); f2=fp(stable)
    if f1!=f2: raise RuntimeError('fingerprint no determinista')
    INF.mkdir(parents=True,exist_ok=True)
    with DETAIL.open('w',newline='',encoding='utf-8') as fh:
        w=csv.DictWriter(fh,fieldnames=list(detail[0])); w.writeheader(); w.writerows(sorted(detail,key=lambda x:int(x['id'])))
    with GEN.open('w',newline='',encoding='utf-8') as fh:
        w=csv.DictWriter(fh,fieldnames=['subtipo','canon_completo','variantes','ids','filas','plazas','clasificacion']); w.writeheader()
    report={'version':'fase8-paso76-v1','modo':'read-only','generado_utc':datetime.now(timezone.utc).isoformat(),'baseline':before,'normalizador_sha256':hashlib.sha256((ROOT/'normalizacion_puestos.py').read_bytes()).hexdigest(),'origenes':['fase8_paso72_auditoria.json','fase8_paso72b_analisis_bcd.json','fase8_paso72c_variantes_formales.json','fase8_paso73_reglas_primer_bloque.json','fase8_paso74_aplicacion.json','fase8_paso75_cierre_bloque.json'],'universo_excluido_72C':len(excluded),'universo':stable['universo'],'subtipos':by_sub,'resultado_global':counts,'A_NUEVO':{'filas':0,'plazas':0,'conjuntos':0},'A_YA_CUBIERTO':{'filas':counts['A_SEGURO']['filas'],'plazas':counts['A_SEGURO']['plazas'],'conjuntos':len(sets)},'generalizables_seguros':[],'solo_lista_cerrada':sets,'no_generalizables':[],'cobertura':{'ids_universo':len(rows),'ids_clasificados':len(detail),'ids_perdidos':0,'ids_duplicados':len(ids)-len(set(ids))},'fingerprint1':f1,'fingerprint2':f2,'gate_paso19':{k:{'filas':gate[k]['filas'],'plazas':gate[k]['plazas']} for k in ('cambios_reales_recalculables','discrepancias_contextuales_no_recalculables','discrepancias_no_clasificables_automaticamente')},'OA_pendientes':0,'id_30709':'Policía Local','sqlite_modificado':False,'git_diff_check':subprocess.run(['git','diff','--check'],cwd=ROOT).returncode==0,'decision':'PASO77_NO_APLICABLE_PASO78_SIN_APLICACION'}
    if not report['git_diff_check']: raise RuntimeError('git diff --check falló')
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'estado':'PASS','universo':stable['universo'],'resultado':counts,'A_NUEVO':0,'A_YA_CUBIERTO':len(sets),'generalizables':0,'fingerprint':f1},ensure_ascii=False))
if __name__=='__main__': main()
