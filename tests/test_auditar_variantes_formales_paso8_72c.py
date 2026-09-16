import json
from scripts.audit.auditar_variantes_formales_paso8_72c import OUT,main
def test_paso72c_cobertura_total():
 main();r=json.loads(OUT.read_text());assert r['cobertura']['ids_perdidos']==0;assert r['cobertura']['ids_clasificados']==r['cobertura']['ids_origen']
