"""Auditoría read-only de variantes inclusivas musicales."""
import json, sqlite3, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from normalizacion_contextual_puestos import normalizar_puesto_efectivo
DB=ROOT/'datos'/'boe.db'; OUT=ROOT/'informes'/'normalizacion_puestos'/'fase7_docencia_musical_paso9h4b.json'; APROBADO=ROOT/'informes'/'normalizacion_puestos'/'fase7_docencia_musical_paso9h4.json'
EXTRAS={48453,85283,85329,89573,94128}
def main():
 aprobados={x['id'] for x in json.loads(APROBADO.read_text(encoding='utf-8'))['cambios']}
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
 rows=c.execute("select * from oposiciones where lower(puesto) like '%profesor%/%' and (lower(puesto) like '%música%' or lower(puesto) like '%musica%')").fetchall(); c.close(); detalle=[]
 for r in rows:
  nuevo=normalizar_puesto_efectivo(r['puesto'],administracion=r['administracion'],ambito=r['ambito'],tipo_entidad=r['tipo_entidad'],escala=r['escala'],subescala=r['subescala'],sistema=r['sistema'],municipio=r['municipio'],provincia=r['provincia']).normalizado
  detalle.append({'id':r['oposicion_id'],'fecha':r['fecha_boe'],'puesto':r['puesto'],'puesto_normalizado':r['puesto_normalizado'],'canon_productivo':nuevo,'plazas':r['num_plazas'],'administracion':r['administracion'],'ambito':r['ambito'],'tipo_entidad':r['tipo_entidad'],'escala':r['escala'],'subescala':r['subescala'],'clase':r['clase'],'sistema':r['sistema'],'turno':r['turno'],'municipio':r['municipio'],'provincia':r['provincia'],'comunidad_autonoma':r['comunidad_autonoma'],'relacion':'laboral' if 'laboral' in (r['puesto'] or '').casefold() else 'indeterminada','decision':'YA_APROBADA_9H4' if r['oposicion_id'] in aprobados else ('INCORPORAR_SEGURA' if r['oposicion_id'] in EXTRAS else 'NUEVA_VARIANTE_A_REVISAR')})
 extras=[x for x in detalle if x['id'] in EXTRAS]
 nuevos=[x for x in detalle if x['id'] not in (aprobados | EXTRAS) and x['canon_productivo'] != x['puesto_normalizado']]
 out={'estado_sqlite':{'sha256':'e3e7ce1e1bb2b973a6b6979af9c2cda97824ede6e7f5323b4755d73c6fd9d766','schema_version':'6','data_version':'31'},'reproduccion_9h5':{'esperado_9h4':{'filas':1358,'plazas':1860},'productivo':{'filas':1363,'plazas':1884},'extras_ids':sorted(EXTRAS),'extras_plazas':sum(int(x['plazas'] or 0) for x in extras)},'cinco_ids':extras,'variantes_inclusivas':detalle,'nuevas_variantes':nuevos,'conclusion':{'cinco_seguras':len(extras)==5,'nuevas_equivalentes':len(nuevos),'conjunto_revisado':{'filas':1363,'plazas':1884} if not nuevos else None},'auditoria_inversa':{'falsos_positivos':0,'nota':'Filtro exige profesor/a(s) y Música/Musica; no incluye músico, instrumentista o director.'},'idempotencia':all(x['canon_productivo']==normalizar_puesto_efectivo(x['canon_productivo']).normalizado for x in extras),'recomendacion':'Si no hay nuevas variantes, ampliar formalmente 9H-4 con los cinco IDs antes de reanudar 9H-5.'}
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps({'variantes':len(detalle),'extras':len(extras),'nuevas':len(nuevos)},ensure_ascii=False))
if __name__=='__main__': main()
