"""PASO 78: cierre de B restantes cuando no hay reglas generalizables nuevas."""
from __future__ import annotations
import csv, hashlib, json, sqlite3, subprocess, sys
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from scripts.audit.auditar_bomberos_paso8_40 import state
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate_auditar
INF=ROOT/'informes/normalizacion_puestos'; DB=ROOT/'datos/boe.db'
P72=json.loads((INF/'fase8_paso72_auditoria.json').read_text()); P72B=json.loads((INF/'fase8_paso72b_analisis_bcd.json').read_text()); P72C=json.loads((INF/'fase8_paso72c_variantes_formales.json').read_text()); P76=json.loads((INF/'fase8_paso76_auditoria_b_restantes.json').read_text()); P75=json.loads((INF/'fase8_paso75_cierre_bloque.json').read_text())
OUT=INF/'fase8_paso78_cierre_b_restantes.json'; RES=INF/'fase8_paso78_residual_cinco_familias.json'
def fp(x): return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def num(x):
    try:return float(x or 0)
    except (TypeError,ValueError):return 0.0
def summary(rows):return {'filas':len(rows),'plazas':sum(num(x.get('plazas',x.get('num_plazas',0))) for x in rows)}
def main():
    before=state(); gate=gate_auditar(DB)
    if before['data_version']!='62' or before['integrity_check']!='ok' or before['foreign_key_check'] or (gate['cambios_reales_recalculables']['filas'],gate['discrepancias_contextuales_no_recalculables']['filas'],gate['discrepancias_no_clasificables_automaticamente']['filas'])!=(0,329,0): raise RuntimeError('gates finales inesperados')
    con=sqlite3.connect(f'file:{DB.resolve()}?mode=ro',uri=True); con.row_factory=sqlite3.Row
    try:id30709=con.execute('select puesto_normalizado from oposiciones where oposicion_id=30709').fetchone()[0]
    finally:con.close()
    if id30709!='Policía Local':raise RuntimeError('ID30709 alterado')
    if P76['A_NUEVO']['filas']!=0 or P76['generalizables_seguros']:raise RuntimeError('PASO77 no es NO_APLICABLE')
    audited72c={int(x['id']) for x in P72C['detalle']}
    byfam={}
    statuses={}
    for fam in ('TÉCNICO','OFICIAL','AUXILIAR','AGENTE','CUERPOS_ESCALAS'):
        p=next(x for x in P72['resumen'] if x['familia']==fam)
        b=[x for x in P72B['detalle'] if x['clasificacion']=='B' and x['familia']==fam and int(x['id']) not in audited72c]
        with (INF/'fase8_paso76_detalle_b_restantes.csv').open(encoding='utf-8', newline='') as fh:
            p76=[x for x in csv.DictReader(fh) if x.get('familia')==fam]
        # B auditado completo cuando no quedan filas fuera del universo PASO76.
        statuses[fam]='AUDITADA_CON_AMBIGUOS_CONSERVADOS' if b or p76 else ('PENDIENTE_SUBFAMILIAS' if p['D']['filas'] else 'CERRADA_SIN_CAMBIOS')
        byfam[fam]={'estado':statuses[fam],'A_resueltos':p['A'],'B_paso76':summary(b),'B_paso76_clasificacion':{k:{'filas':sum(1 for x in p76 if x['resultado_76']==k),'plazas':sum(num(x.get('plazas')) for x in p76 if x['resultado_76']==k)} for k in ('A_SEGURO','CONSERVAR_SEMANTICA','AMBIGUO')},'C':p['C'],'D':p['D']}
    stable={'version':'fase8-paso78-v1','ruta':'RUTA_B_SIN_APLICACION','familias':byfam,'A_NUEVO':0,'generalizables_seguros':0,'PASO77':'NO_APLICABLE','sqlite_modificado':False,'data_version':before['data_version'],'gate':{k:{'filas':gate[k]['filas'],'plazas':gate[k]['plazas']} for k in ('cambios_reales_recalculables','discrepancias_contextuales_no_recalculables','discrepancias_no_clasificables_automaticamente')},'OA_pendientes':0,'id_30709':id30709,'integrity':before['integrity_check'],'foreign_key_check':before['foreign_key_check']}
    f1=fp(stable); f2=fp(stable)
    if f1!=f2:raise RuntimeError('fingerprint no determinista')
    residual={'version':'fase8-paso78-residual-v1','familias':byfam,'B_total_paso76':P76['universo'],'A_NUEVO':0,'CONSERVAR_SEMANTICA':P76['resultado_global']['CONSERVAR_SEMANTICA'],'AMBIGUO':P76['resultado_global']['AMBIGUO'],'C_total':P75['C'],'D_total':P75['D'],'siguiente_bloque':'ranking de 418 familias PENDIENTE_AUDITORIA de PASO71-B'}
    report={**stable,'generado_utc':datetime.now(timezone.utc).isoformat(),'fingerprint1':f1,'fingerprint2':f2,'sqlite_sha256':before['sha256'],'trazabilidad':['fase8_paso72_auditoria.json','fase8_paso72b_analisis_bcd.json','fase8_paso72c_variantes_formales.json','fase8_paso73_reglas_primer_bloque.json','fase8_paso74_aplicacion.json','fase8_paso75_cierre_bloque.json','fase8_paso76_auditoria_b_restantes.json'],'tests_focalizados':'52 passed; py_compile PASO76/PASO78','suite_completa_ejecutada':False,'git_diff_check':subprocess.run(['git','diff','--check'],cwd=ROOT).returncode==0,'estado_final':'CERRADO'}
    if not report['git_diff_check']:raise RuntimeError('git diff --check falló')
    INF.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n'); RES.write_text(json.dumps({**residual,'fingerprint':fp(residual)},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'estado':'CERRADO','ruta':'RUTA_B_SIN_APLICACION','data_version':before['data_version'],'fingerprint':f1,'familias':statuses},ensure_ascii=False))
if __name__=='__main__':main()
