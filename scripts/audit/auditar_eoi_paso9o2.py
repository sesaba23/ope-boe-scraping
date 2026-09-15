import json
from pathlib import Path
def main():
 out={'conjunto_cerrado':{'reglas':[],'filas':0,'plazas':0,'canon_por_id':{}},'falsos_positivos':0,'colisiones':0,'motivo':'El cuerpo EOI explícito ya está normalizado; no quedan nuevas reglas inequívocas.'};Path('informes/normalizacion_puestos/fase7_eoi_paso9o2.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()
