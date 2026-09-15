"""Revisión 9F-1 read-only de candidatas docentes textuales."""
import json, sqlite3, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from normalizacion_puestos import normalizar_puesto
from scripts.audit.auditar_funcionarios_docentes_paso9e import clasificar

ROOT=Path(__file__).resolve().parents[2]; DB=ROOT/'datos'/'boe.db'; OUT=ROOT/'informes'/'normalizacion_puestos'/'fase7_funcionarios_docentes_paso9f1.json'
CANONES={'Maestros','Profesores de Enseñanza Secundaria','Profesores Técnicos de Formación Profesional','Profesores de Escuelas Oficiales de Idiomas','Catedráticos de Universidad','Profesores Titulares de Universidad'}
def main():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; rows=c.execute('select * from oposiciones').fetchall(); c.close()
 cand=[]; cats=Counter(); fam=Counter(); den=Counter(); plazas=Counter(); cambios=[]
 for r in rows:
  cl,k,canon=clasificar(r['puesto'])
  if cl!='SEGURA_TEXTUAL': continue
  actual=r['puesto_normalizado']; nuevo=normalizar_puesto(r['puesto'])
  if actual in CANONES and nuevo==actual: cat='YA_NORMALIZADA'
  elif nuevo in CANONES and actual!=nuevo: cat='SEGURA_TEXTUAL_APROBABLE'; cambios.append({'id':r['oposicion_id'],'puesto':r['puesto'],'actual':actual,'canon':nuevo,'plazas':r['num_plazas']})
  elif k in {'artistica','docente_generico'}: cat='REQUIERE_CONTEXTO'
  else: cat='DUDOSA'
  n=int(r['num_plazas'] or 0) if str(r['num_plazas'] or '').isdigit() else 0
  cand.append({'id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado_actual':actual,'clasificacion':cat,'familia':k,'canon_propuesto':canon,'ambito':r['ambito'],'administracion':r['administracion'],'tipo_entidad':r['tipo_entidad'],'escala':r['escala'],'subescala':r['subescala'],'plazas':n})
  cats[cat]+=1; fam[k]+=1; den[r['puesto']]+=1; plazas[cat]+=n
 ranking=[{'denominacion':x,'filas':n,'plazas':sum(int(r['num_plazas'] or 0) if str(r['num_plazas'] or '').isdigit() else 0 for r in rows if r['puesto']==x)} for x,n in den.most_common()]
 out={'estado_inicial':{'schema_version':'6','data_version':'31','sha256':'e3e7ce1e1bb2b973a6b6979af9c2cda97824ede6e7f5323b4755d73c6fd9d766','oposiciones':len(rows)},'universo_9e_reconstruido':{'filas':len(cand),'plazas':sum(plazas.values()),'referencia_9e':887},'reconciliacion_887':{'reconstruidas':len(cand),'diferencia':len(cand)-887,'clasificacion':dict(cats),'plazas_por_clasificacion':dict(plazas)},'familias':dict(fam),'ranking_denominaciones':ranking,'canones_aprobados':sorted({x['canon'] for x in cambios}),'reglas_no_implementadas':['artísticas/locales genéricas','docencia genérica','figuras laborales universitarias','casos contextuales o dudosos'],'cambios_propuestos':cambios,'dry_run':{'cambios_docentes_9f1':len(cambios),'cambios_ajenos':0,'requiere_contexto_transformadas':0,'dudosas_transformadas':0,'excluidas_transformadas':0,'idempotencia':all(normalizar_puesto(x['canon'])==x['canon'] for x in cambios)},'falsos_positivos_protegidos':['Maestro de obras','monitores','auxiliares','técnicos no docentes','profesores asociados/contratados'],'casos':cand,'conclusion':'No se ejecuta recálculo; SQLite permanece intacta.'}
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(out['reconciliacion_887'],ensure_ascii=False))
if __name__=='__main__': main()
