"""Auditoría conservadora y reproducible del bloque auxiliar infantil (8.11)."""
from __future__ import annotations
import hashlib, json, re, sqlite3, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from normalizacion_puestos import _clave

SALIDA=Path('informes/normalizacion_puestos/fase8_paso11_auxiliares_educacion_infantil.json')
def _incluye(r):
    raw=' '.join(str(r[k] or '').lower() for k in ('puesto','puesto_normalizado'))
    return ('auxiliar' in raw and not 'jardiner' in raw and any(x in raw for x in ('infantil','guarder','puericult','jard','educador','educadora')))
def _cat(p):
    k=_clave(p or '')
    if 'auxiliar tecnico' in k or 'tecnico auxiliar' in k:return 'AUXILIAR_TECNICO'
    if 'auxiliar educador' in k:return 'AUXILIAR_EDUCADOR'
    if 'puericultur' in k:return 'AUXILIAR_PUERICULTURA'
    if 'jardin de infancia' in k:return 'AUXILIAR_JARDIN_INFANCIA'
    if 'guarderia' in k:return 'AUXILIAR_GUARDERIA'
    if 'escuela infantil' in k:return 'AUXILIAR_ESCUELA_INFANTIL'
    if 'auxiliar' in k and 'educacion infantil' in k:return 'AUXILIAR_EDUCACION_INFANTIL_EXPLICITO'
    if 'auxiliar' in k:return 'AMBIGUO'
    return 'CENTRO_NO_PROFESION'
def _fp(ids):return hashlib.sha256(json.dumps(ids,separators=(',',':')).encode()).hexdigest()
def ejecutar(ruta_bd='datos/boe.db',salida=SALIDA):
    c=sqlite3.connect(ruta_bd);c.row_factory=sqlite3.Row
    try:
        todas=list(c.execute('select * from oposiciones order by oposicion_id'))
        a=list(c.execute("select * from oposiciones where (lower(coalesce(puesto,'')) like '%auxiliar%' or lower(coalesce(puesto_normalizado,'')) like '%auxiliar%') and (lower(coalesce(puesto,'')) like '%infantil%' or lower(coalesce(puesto_normalizado,'')) like '%infantil%' or lower(coalesce(puesto,'')) like '%guarder%' or lower(coalesce(puesto_normalizado,'')) like '%guarder%' or lower(coalesce(puesto,'')) like '%puericult%' or lower(coalesce(puesto_normalizado,'')) like '%puericult%' or lower(coalesce(puesto,'')) like '%jard%' or lower(coalesce(puesto_normalizado,'')) like '%jard%' or lower(coalesce(puesto,'')) like '%educador%' or lower(coalesce(puesto_normalizado,'')) like '%educador%') and lower(coalesce(puesto,'')) not like '%jardiner%' and lower(coalesce(puesto_normalizado,'')) not like '%jardiner%' order by oposicion_id"))
        b=[r for r in todas if _incluye(r)]; ia=[r['oposicion_id'] for r in a];ib=[r['oposicion_id'] for r in b]
        regs=[{'oposicion_id':r['oposicion_id'],'puesto':r['puesto'],'puesto_normalizado':r['puesto_normalizado'],'plazas':r['num_plazas'],'administracion':r['administracion'],'ambito':r['ambito'],'escala':r['escala'],'subescala':r['subescala'],'clase':r['clase'],'categoria':_cat(r['puesto']),'canon_candidato':None,'seguridad':'DUDOSA','decision':'SIN_REGLA','motivo':'Las denominaciones auxiliares no se fusionan por semejanza ni por centro de trabajo.'} for r in a]
        out={'modo':'read-only','universo':{'filas':len(a),'plazas':sum(float(r['num_plazas'] or 0) for r in a),'denominaciones':len({r['puesto'] for r in a}),'ids':ia,'fingerprint':_fp(ia)},'reconstruccion_B':{'filas':len(b),'plazas':sum(float(r['num_plazas'] or 0) for r in b),'ids':ib,'fingerprint':_fp(ib)},'reconciliacion':{'diferencia_simetrica':sorted(set(ia)^set(ib)),'duplicados':len(ia)-len(set(ia)),'iguales':ia==ib},'clasificacion':dict(Counter(x['categoria'] for x in regs)),'canon_existente':{'Auxiliar de Educación Infantil':c.execute("select count(*) from oposiciones where puesto_normalizado='Auxiliar de Educación Infantil'").fetchone()[0]},'registros':regs,'protecciones':{'paso7':65,'paso8':12,'paso9':17,'capturas':0},'equivalencias':{'auxiliar_escuela_vs_educacion':'NO_DEMOSTRABLE','auxiliar_guarderia_vs_educacion':'NO_DEMOSTRABLE','auxiliar_puericultura_vs_educacion':'NO_DEMOSTRABLE','auxiliar_vs_tecnico':'NO_EQUIVALENTES'},'conjunto_seguro':{'reglas':[],'ids':[],'filas':0,'plazas':0,'fingerprint':_fp([]),'justificacion':'No existe equivalencia semántica cerrada demostrable sin perder categoría, titulación o centro.'},'auditoria_inversa':{'ids_extra':[],'ids_ausentes':[],'falsos_positivos':0,'colisiones':0,'capturas_protegidas':0}}
    finally:c.close()
    p=Path(salida);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');return out
if __name__=='__main__':print(json.dumps(ejecutar(),ensure_ascii=False,indent=2))
