import json
from scripts.audit.auditar_familias_paso8_72 import OUT,main
def test_paso72_cinco_familias_y_cobertura():
 main();r=json.loads(OUT.read_text());assert len(r['familias_seleccionadas'])==5;assert r['cobertura']['sin_clasificar']==0
