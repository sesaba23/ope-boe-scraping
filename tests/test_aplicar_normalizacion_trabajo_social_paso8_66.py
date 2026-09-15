from scripts.audit.aplicar_normalizacion_trabajo_social_paso8_66 import CANON,V,plan
from normalizacion_puestos import _clave
def test_plan_trabajo_social_es_dinamico_y_acotado():assert all(x['canon']==CANON and _clave(x['puesto']) in V for x in plan())
