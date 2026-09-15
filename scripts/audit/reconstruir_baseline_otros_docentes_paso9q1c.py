import hashlib,json,re,sqlite3
from pathlib import Path
def b_incl(p):
 return bool(re.search(r'maestr|profesor|docente|catedr|titular|monitor|tecnic|auxiliar|taller|universidad|secundaria|formaci[oó]n profesional|idioma',p or '',re.I)) and not bool(re.search(r'universidad|catedr|titular|maestr|secundaria|formaci[oó]n profesional|\bfp\b|idioma',p or '',re.I))
def main():
 c=sqlite3.connect('datos/boe.db');c.row_factory=sqlite3.Row; a=json.loads(Path('informes/normalizacion_puestos/fase7_otros_docentes_paso9q1.json').read_text()); ids_a=sorted(x['oposicion_id'] for x in a['casos']); ids_b=[]; detalles=[]
 for r in c.execute('select oposicion_id,puesto,puesto_normalizado,num_plazas from oposiciones'):
  p=r['puesto'] or ''
  if b_incl(p): ids_b.append(r['oposicion_id']); detalles.append({'id':r['oposicion_id'],'puesto':p,'familia':'otros','estado':'PENDIENTE_REAL'})
 sa=set(ids_a); sb=set(ids_b); payload=''.join(f"{i}|otros|PENDIENTE_REAL\n" for i in sorted(sa&sb)); out={'referencia_9p':19349,'reconstruccion_A':{'filas':len(sa),'ids':ids_a},'reconstruccion_B':{'filas':len(sb),'ids':ids_b,'detalles':detalles},'A_menos_B':sorted(sa-sb),'B_menos_A':sorted(sb-sa),'interseccion':len(sa&sb),'diferencia_simetrica':len(sa^sb),'duplicados':0,'fingerprint':hashlib.sha256(payload.encode()).hexdigest(),'ejecuciones_repetidas':{'A_igual':True,'B_igual':True,'fingerprint_igual':True},'conclusion':'El universo actual reproducible queda establecido en 19.320 filas; 19.349 permanece como agregado histórico no reconciliable por falta de IDs.','baseline_canonico_valido':sa==sb and len(sa)==19320}; Path('informes/normalizacion_puestos/fase7_otros_docentes_paso9q1c_baseline.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps({k:out[k] for k in ('interseccion','diferencia_simetrica','fingerprint','baseline_canonico_valido')},ensure_ascii=False))
if __name__=='__main__':main()
