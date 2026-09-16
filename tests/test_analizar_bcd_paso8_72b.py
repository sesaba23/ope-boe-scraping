import json
from scripts.audit.analizar_bcd_paso8_72b import OUT,main
def test_paso72b_cobertura_bcd():
 main();r=json.loads(OUT.read_text());assert r['cobertura']['ids_perdidos']==0;assert r['cobertura']['ids_duplicados']==0;assert set(r['totales_originales'])=={'B','C','D'}
