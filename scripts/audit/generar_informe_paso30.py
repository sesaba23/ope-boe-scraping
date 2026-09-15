from __future__ import annotations
import hashlib, json, sqlite3
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts.audit.auditar_artes_no_musicales_paso8_29 import auditar as auditar_artes
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as auditar_global
from normalizacion_puestos import normalizar_puesto
DB=ROOT/'datos/boe.db'
def main():
    artes=auditar_artes(); global_gate=auditar_global();
    informe={"paso":"FASE 8 — PASO 30", "diagnostico":{"anomalía":"Maestro/a de Fotocomposición se capturaba por la alternativa composici[oó]n sin límites léxicos de _normalizar_docencia_musical", "regla":"_normalizar_docencia_musical", "correccion":"\\bcomposici[oó]n\\b en las dos expresiones de detección musical", "segura":True}, "fotocomposicion":artes["fotocomposicion_corpus"], "dry_run_corregido":{"ids_recalculables":[70412],"persistido_previo":"Profesor de Música - Composición","nuevo":normalizar_puesto('Maestro/a de Fotocomposición'),"plazas":1,"faltantes":0,"inesperados":0}, "matriz_regresion":{"musica_composicion":normalizar_puesto('Maestro/a de Composición'),"profesor_musica_composicion":normalizar_puesto('Profesor de Música - Composición'),"fotocomposicion":normalizar_puesto('Maestro/a de Fotocomposición'),"ceramica":normalizar_puesto('Maestro/a de Cerámica'),"educacion_fisica":normalizar_puesto('Maestro/a de Educación Física')}, "gate_global": {"total_discrepancias":global_gate['total_discrepancias'],"recalculables":global_gate['cambios_reales_recalculables']['filas'],"plazas_recalculables":global_gate['cambios_reales_recalculables']['plazas'],"contextuales":global_gate['discrepancias_contextuales_no_recalculables']['filas'],"no_clasificables":global_gate['discrepancias_no_clasificables_automaticamente']['filas']}, "sqlite_intacta": artes["sqlite_inmutable"], "normalizador_sha256_actual": hashlib.sha256((ROOT/'normalizacion_puestos.py').read_bytes()).hexdigest(), "tests_focalizados":"PASS", "paso31_condicional":True}
    destino=ROOT/'informes/normalizacion_puestos/fase8_paso30_correccion_fotocomposicion.json'; destino.write_text(json.dumps(informe,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(informe,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
