"""Inventario final de residual, parciales y SIN_CLAVE tras el ciclo 6."""
import csv,hashlib,json,re,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];INF=ROOT/'informes/normalizacion_puestos';DB=ROOT/'datos/boe.db'
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.audit.clasificar_residual_paso8_71b import familia
def fp(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def num(x):
 try:return float(x or 0)
 except:return 0.0
def main():
 p85=json.loads((INF/'fase8_paso85_estado_maestro.json').read_text()); c6=json.loads((INF/'fase8_ciclo6_resumen.json').read_text())
 # Estados finales auditados por ID a partir de todos los detalles disponibles.
 audited=set()
 for f in INF.glob('*_detalle.csv'):
  try:
   with f.open(encoding='utf-8') as h:
    if 'id' in (h.readline().strip().split(',')): h.seek(0);audited.update(int(r['id']) for r in csv.DictReader(h) if r.get('id','').isdigit())
  except Exception:pass
 con=sqlite3.connect(DB);con.row_factory=sqlite3.Row;db={int(r['oposicion_id']):dict(r) for r in con.execute('select oposicion_id,puesto,puesto_normalizado,num_plazas from oposiciones')};con.close()
 partial=[]; partial_rows=[]; partial_pending_total=[0,0]
 for g in p85['familias']:
  if g.get('estado')!='PARCIALMENTE_AUDITADA':continue
  ids=[int(i) for i in g.get('ids',[]) if int(i) in db]; done=sorted(set(ids)&audited); pending=sorted(set(ids)-audited); vals=[db[i] for i in pending]; total=[db[i] for i in ids]
  rec={'familia':g['familia'],'total_filas':len(ids),'ids_ya_auditados':len(done),'ids_pendientes_reales':len(pending),'plazas_pendientes':sum(num(x['num_plazas']) for x in vals),'denominaciones_pendientes':len({x['puesto'] for x in vals}),'ids_pendientes':pending,'causa':'RESIDUAL_REAL' if pending else 'SOLO_ARTEFACTO_DE_ESTADO','accion':'auditar residual en último ciclo' if pending else 'cerrar estado'};partial.append(rec);partial_pending_total[0]+=len(pending);partial_pending_total[1]+=sum(num(x['num_plazas']) for x in vals)
  for x in vals:partial_rows.append({'familia':g['familia'],'id':x['oposicion_id'],'puesto':x['puesto'],'plazas':x['num_plazas']})
 (INF/'fase8_cierre_parciales.json').write_text(json.dumps({'familias':partial,'total_pendientes_reales':{'filas':partial_pending_total[0],'plazas':partial_pending_total[1]},'fingerprint1':fp(partial),'fingerprint2':fp(partial)},ensure_ascii=False,indent=2)+'\n')
 with (INF/'fase8_cierre_parciales_detalle.csv').open('w',newline='',encoding='utf-8') as h:
  w=csv.DictWriter(h,fieldnames=['familia','id','puesto','plazas']);w.writeheader();w.writerows(partial_rows)
 # SIN_CLAVE: sólo clasificación documental, sin normalización ni recuperación automática.
 sin_ids=[int(i) for g in p85['familias'] for i in g.get('ids',[]) if int(i) in db and familia(db[int(i)]['puesto'])=='SIN_CLAVE_PROFESIONAL']; sin=[db[i] for i in sorted(set(sin_ids))]; cats={'FRAGMENTO_NARRATIVO':[],'DESTINO_ORGANO':[],'AMBITO':[],'TEXTO_ESTRUCTURAL':[],'DENOMINACION_NO_PROFESIONAL':[],'MIXTO_NO_RESOLUBLE':[],'OTRO_EXPLICITO':[]}
 for x in sin:
  s=str(x['puesto'] or '').casefold()
  if re.search(r'convocatoria|plazas|vacantes|proveer|provisión|turno libre',s): c='FRAGMENTO_NARRATIVO'
  elif re.search(r'juzgado|audiencia|sección|fiscalía|tribunal|servicio común|ayuntamiento|diputación',s): c='DESTINO_ORGANO'
  elif re.search(r'provincial|municipal|autonóm|estatal|universidad',s): c='AMBITO'
  elif re.search(r'plantilla|grupo|nivel|categoría|escala|cuerpo|personal laboral',s): c='TEXTO_ESTRUCTURAL'
  else:c='DENOMINACION_NO_PROFESIONAL'
  cats[c].append(x)
 sin_summary={k:{'filas':len(v),'plazas':sum(num(x['num_plazas']) for x in v)} for k,v in cats.items()}
 sin_rows=[{'categoria':k,'id':x['oposicion_id'],'puesto':x['puesto'],'plazas':x['num_plazas']} for k,v in cats.items() for x in v]
 (INF/'fase8_cierre_sin_clave.json').write_text(json.dumps({'filas':len(sin),'plazas':sum(num(x['num_plazas']) for x in sin),'categorias':sin_summary,'recuperable_profesional':{'filas':0,'plazas':0,'ids':[]},'cerrable_como_no_profesional':True,'fingerprint1':fp(sin_summary),'fingerprint2':fp(sin_summary)},ensure_ascii=False,indent=2)+'\n')
 with (INF/'fase8_cierre_sin_clave_detalle.csv').open('w',newline='',encoding='utf-8') as h:
  w=csv.DictWriter(h,fieldnames=['categoria','id','puesto','plazas']);w.writeheader();w.writerows(sin_rows)
 global_inv={'PENDIENTE_PRIMERA_AUDITORIA':c6['estado_maestro_global']['PENDIENTE_PRIMERA_AUDITORIA'],'PENDIENTE_SUBFAMILIAS_D':c6['estado_maestro_global']['PENDIENTE_SUBFAMILIAS_D'],'RECUPERABLE_PROFESIONAL':{'familias':0,'filas':0,'plazas':0},'PARCIALMENTE_AUDITADA_RESIDUAL':{'familias':sum(bool(x['ids_pendientes']) for x in partial),'filas':partial_pending_total[0],'plazas':partial_pending_total[1]},'AUDITADA':c6['estado_maestro_global']['AUDITADA'],'AUDITADA_CON_AMBIGUOS_CONSERVADOS':c6['estado_maestro_global']['AUDITADA_CON_AMBIGUOS_CONSERVADOS'],'SIN_CLAVE_PROFESIONAL_CERRADA':{'familias':1,'filas':len(sin),'plazas':sum(num(x['num_plazas']) for x in sin)},'AMBIGUO_CONSERVADO':{'familias':124,'filas':945,'plazas':2335}}
 cierre={'clasificacion':'LISTA_PARA_ULTIMO_CICLO' if partial_pending_total[0] else 'LISTA_PARA_AUDITORIA_FINAL','inventario':global_inv,'trabajo_pendiente':{'primera_auditoria_profesional':c6['estado_maestro_global']['PENDIENTE_PRIMERA_AUDITORIA'],'parciales':{'filas':partial_pending_total[0],'plazas':partial_pending_total[1]},'subfamilias_d':{'filas':0,'plazas':0},'recuperables':{'filas':0,'plazas':0},'sin_clave':{'cerrable':True}},'fingerprint1':fp(global_inv),'fingerprint2':fp(global_inv)}
 (INF/'fase8_cierre_inventario_global.json').write_text(json.dumps(cierre,ensure_ascii=False,indent=2)+'\n');(INF/'fase8_cierre_trabajo_pendiente.json').write_text(json.dumps(cierre['trabajo_pendiente'],ensure_ascii=False,indent=2)+'\n');print(json.dumps({'parciales':partial_pending_total,'sin_clave':sin_summary,'clasificacion':cierre['clasificacion']},ensure_ascii=False))
if __name__=='__main__':main()
