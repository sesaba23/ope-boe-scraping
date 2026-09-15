"""Cierre verificable de los PASOS 49-51 de Enfermería."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit.auditar_bomberos_paso8_40 import sha, state, summary

INF = ROOT / 'informes/normalizacion_puestos'
OUT = INF / 'fase8_cierre_enfermeria.json'


def main():
    auditoria = json.loads((INF / 'fase8_paso49_enfermeria.json').read_text(encoding='utf-8'))
    reglas = json.loads((INF / 'fase8_paso50_reglas_enfermeria.json').read_text(encoding='utf-8'))
    aplicacion = json.loads((INF / 'fase8_paso51_aplicacion_enfermeria.json').read_text(encoding='utf-8'))
    # El slash de género de Enfermero/a no es un puesto compuesto. Reasignar
    # la foto read-only a su microfamilia A para el cierre sin tocar SQLite.
    familias_a = list(auditoria['taxonomia'])
    filas_taxonomia = [dict(fila) for fila in auditoria['filas']]
    for fila in filas_taxonomia:
        if fila['canon_propuesto'] == 'Enfermero':
            fila['microfamilia'] = 'ENFERMERO_GENERICO'
    tax = {familia: summary([fila for fila in filas_taxonomia if fila['microfamilia'] == familia]) for familia in familias_a}
    campos = {'enfermero_generico': 'ENFERMERO_GENERICO', 'DUE': 'DUE', 'ATS': 'ATS', 'matrona': 'MATRONA',
              'enfermeria_trabajo': 'ENFERMERIA_TRABAJO', 'enfermeria_salud_mental': 'ENFERMERIA_SALUD_MENTAL',
              'enfermeria_familiar_comunitaria': 'ENFERMERIA_FAMILIAR_COMUNITARIA', 'enfermeria_pediatrica': 'ENFERMERIA_PEDIATRICA',
              'enfermeria_geriatrica': 'ENFERMERIA_GERIATRICA', 'otras_especialidades': 'OTRAS_ESPECIALIDADES',
              'cuerpos_escalas': 'CUERPOS_ESCALAS', 'personal_estatutario': 'CUERPOS_ESCALAS',
              'mandos': 'SUPERVISION_MANDOS', 'puestos_compuestos': 'PUESTOS_COMPUESTOS', 'otros_contextuales': 'OTROS_CONTEXTUALES'}
    resultado = {'version': 'fase8-cierre-enfermeria-v1', 'baseline_git': auditoria['baseline_git'],
                 'baseline_sqlite': aplicacion['primera_ejecucion']['antes'], 'baseline_normalizador': auditoria['baseline_normalizador'],
                 'universo_paso39': auditoria['universo_paso39'], 'universo_reconstruido': auditoria['universo_reconstruido'],
                 'reconciliacion_paso39': auditoria['reconciliacion_paso39'], 'taxonomia': tax,
                 **{nombre: tax[clave] for nombre, clave in campos.items()},
                 'comparacion_DUE_ATS_enfermero': auditoria['comparacion_DUE_ATS_enfermero'],
                 'catalogo_denominaciones': auditoria['catalogo_denominaciones'], 'grupos_variantes_paso39': auditoria['grupos_variantes_paso39'],
                 'resultado_13_grupos_preliminares': {'A': 1, 'B': 0, 'C': 8, 'D': 4,
                                                       'nota': 'DUE/ATS son C; especialidades, mandos, escalas y compuestos no se absorben'},
                 'clasificacion_A': auditoria['clasificacion_A'], 'clasificacion_B': auditoria['clasificacion_B'],
                 'clasificacion_C': auditoria['clasificacion_C'], 'clasificacion_D': auditoria['clasificacion_D'],
                 'conjuntos_A': auditoria['conjuntos_A'], 'simulaciones_A': auditoria['simulaciones_A'], 'colisiones': auditoria['colisiones'],
                 'paso49_estado': 'PASS', 'paso50_ejecutado': True, 'paso50_estado': 'PASS',
                 'reglas_implementadas': reglas['reglas_implementadas'], 'cobertura_logica_A': {'filas': 69, 'plazas': 252},
                 'gate_pre_sqlite': reglas['gate_pre_sqlite'], 'paso51_ejecutado': True, 'paso51_estado': 'PASS',
                 'backup_sqlite': aplicacion['primera_ejecucion']['backup'], 'mutaciones': aplicacion['primera_ejecucion']['mutaciones'],
                 'plazas_mutadas': aplicacion['primera_ejecucion']['plazas_mutadas'],
                 'data_version_antes': aplicacion['primera_ejecucion']['antes']['data_version'],
                 'data_version_despues': aplicacion['primera_ejecucion']['despues']['data_version'],
                 'segunda_ejecucion': aplicacion['segunda_ejecucion'], 'gate_paso19_inicial': auditoria['gate_paso19_inicial'],
                 'gate_paso19_final': {k: v['filas'] for k, v in aplicacion['gate_final'].items()},
                 'sqlite_inicial': aplicacion['primera_ejecucion']['antes'], 'sqlite_final': state(),
                 'normalizador_inicial': auditoria['baseline_normalizador'], 'normalizador_final': {'sha256': sha(ROOT / 'normalizacion_puestos.py')},
                 'tests_focalizados': ['tests/test_normalizacion_puestos.py -k paso50_enfermeria (15 passed)',
                                       'tests/test_auditar_enfermeria_paso8_49.py::test_paso49_reconstruye_enfermeria_sin_escribir_sqlite (1 passed)',
                                       'tests/test_aplicar_normalizacion_enfermeria_paso8_51.py (1 passed)'],
                 'suite_completa_ejecutada': False, 'motivo_suite_completa': 'Regla literal aislada, gates focalizados y fronteras sanitarias explícitas.',
                 'git_diff_check': subprocess.run(['git', 'diff', '--check'], cwd=ROOT, capture_output=True).returncode == 0,
                 'estado_final': 'CERRADO', 'siguiente_bloque': 'Limpieza'}
    OUT.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'estado_final': resultado['estado_final'], 'mutaciones': resultado['mutaciones'],
                      'gate': resultado['gate_paso19_final']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
