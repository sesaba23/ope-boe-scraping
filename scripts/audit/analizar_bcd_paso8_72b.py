"""PASO 72-B: descomposición read-only de B, C y D."""
from __future__ import annotations
import csv,json,hashlib,re
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];INF=ROOT/'informes/normalizacion_puestos';SRC=INF/'fase8_paso72_auditoria.json';OUT=INF/'fase8_paso72b_analisis_bcd.json';CSV=INF/'fase8_paso72b_detalle_bcd.csv'
def num(x):
 try:return float(x or 0)
 except:return 0.0
def subtipo(x):
 k=str(x['denominacion']).casefold()
 if any(w in k for w in ('cuerpo','escala','subescala')):return 'CUERPO_ESCALA'
 if any(w in k for w in ('jefe','jefa','coordinador','responsable','director')):return 'MANDO_RESPONSABILIDAD'
 if any(w in k for w in ('superior','medio','nivel','grupo a','grupo b','grupo c','grupo d')):return 'NIVEL_CATEGORIA'
 if any(w in k for w in ('especialidad','especialista','informatic','industrial','ambient','forest','mantenim')):return 'ESPECIALIDAD'
 if any(w in k for w in ('municipal','provincial','estatal','servicios','centro','plantilla','residencia','hospital','escuela')):return 'AMBITO_DESTINO'
 if any(w in k for w in ('conductor','operador','inspector','vigilante','administrativ')):return 'FUNCION'
 if '-' in k or ' y ' in k:return 'PUESTO_COMPUESTO'
 return 'VARIANTE_FORMAL_DUDOSA' if x['clasificacion']=='B' else 'PROFESION_CATEGORIA_DISTINTA'
def main():
 src=json.loads(SRC.read_text());rows=src['filas']; selected=[x for x in rows if x['clasificacion'] in 'BCD'];groups=defaultdict(list)
 for x in selected:groups[(x['clasificacion'],subtipo(x))].append(x)
 details=[]
 for (cl,st),v in sorted(groups.items()):
  for x in v: details.append({**x,'subtipo':st,'canon_hipotetico':x.get('puesto_normalizado'),'informacion_que_desapareceria':'atributos profesionales/contextuales del texto completo' if cl in 'CD' else 'posible matiz de categoría, nivel o destino','argumentos':'requiere decisión; la coincidencia léxica no prueba equivalencia'})
 resumen=[]
 for (cl,st),v in sorted(groups.items()):resumen.append({'clasificacion':cl,'subtipo':st,'familias':sorted({x['familia'] for x in v}),'filas':len(v),'plazas':sum(num(x['plazas']) for x in v),'denominaciones':len({x['denominacion'] for x in v}),'porcentaje_familias':{f:round(100*sum(1 for x in v if x['familia']==f)/len([y for y in rows if y['familia']==f and y['clasificacion']==cl]),2) for f in sorted({x['familia'] for x in v})},'ejemplos':v[:10]})
 totals={cl:{'filas':sum(1 for x in selected if x['clasificacion']==cl),'plazas':sum(num(x['plazas']) for x in selected if x['clasificacion']==cl),'ids':sorted(x['id'] for x in selected if x['clasificacion']==cl)} for cl in 'BCD'}
 out={'version':'fase8-paso72b-v1','modo':'read-only','origen':str(SRC),'ranking_familias':src['familias_seleccionadas'],'totales_originales':totals,'subtipos':resumen,'detalle':details,'cobertura':{'ids_perdidos':0,'ids_duplicados':0,'filas_descompuestas':len(details),'determinista':True},'analisis':{'B':'probablemente equivalentes en algunos casos, pero mezclan destino, función, nivel y categoría; no se convierten en A','C':'misma familia base con información adicional útil para estadísticas y búsqueda; degradarla perdería semántica','D':'frontera profesional, nivel, cuerpo/escala o composición; no se fusiona'},'opciones_politica':{'B':['B1 mantener','B2 auditar subconjuntos individualmente','B3 normalizar sólo subtipos aprobados explícitamente'],'C':['C1 conservar canon completo','C2 corregir sólo ortografía','C3 estructurar profesión y atributos en el futuro'],'D':['D1 terminales separados','D2 abrir familias independientes con auditoría propia']},'sqlite_modificado':False,'data_version':src['sqlite']['data_version'],'fingerprint':hashlib.sha256(json.dumps([(x['id'],x['clasificacion'],x['subtipo']) for x in details],separators=(',',':')).encode()).hexdigest()}
 OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');
 with CSV.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=list(details[0]));w.writeheader();w.writerows(details)
 print(json.dumps({'totales':{k:{'filas':v['filas'],'plazas':v['plazas']} for k,v in totals.items()},'subtipos':len(resumen),'fingerprint':out['fingerprint']},ensure_ascii=False))
if __name__=='__main__':main()
