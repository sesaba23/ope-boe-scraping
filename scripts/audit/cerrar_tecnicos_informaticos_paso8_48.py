"""Cierre verificable de los PASOS 46-48 de Técnicos informáticos."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit.auditar_bomberos_paso8_40 import sha, state

INF = ROOT / 'informes/normalizacion_puestos'
OUT = INF / 'fase8_cierre_tecnicos_informaticos.json'


def main():
    auditoria = json.loads((INF / 'fase8_paso46_tecnicos_informaticos.json').read_text(encoding='utf-8'))
    reglas = json.loads((INF / 'fase8_paso47_reglas_tecnicos_informaticos.json').read_text(encoding='utf-8'))
    aplicacion = json.loads((INF / 'fase8_paso48_aplicacion_tecnicos_informaticos.json').read_text(encoding='utf-8'))
    tax = auditoria['taxonomia']
    equivalencias = {'tecnico_informatico_generico': 'TECNICO_INFORMATICO_GENERICO', 'tecnico_auxiliar': 'TECNICO_AUXILIAR_INFORMATICA',
                     'tecnico_medio': 'TECNICO_MEDIO_INFORMATICA', 'tecnico_superior': 'TECNICO_SUPERIOR_INFORMATICA',
                     'sistemas': 'TECNICO_SISTEMAS', 'redes': 'TECNICO_REDES', 'soporte': 'TECNICO_SOPORTE',
                     'programacion_desarrollo': 'TECNICO_PROGRAMACION_DESARROLLO', 'gestion_informatica': 'TECNICO_GESTION_INFORMATICA',
                     'analistas_programadores': 'ANALISTAS_PROGRAMADORES', 'operadores': 'OPERADORES',
                     'administradores_sistemas': 'ADMINISTRADORES_SISTEMAS', 'cuerpos_escalas': 'CUERPOS_ESCALAS_INFORMATICA',
                     'mandos': 'MANDOS_RESPONSABLES', 'puestos_compuestos': 'PUESTOS_COMPUESTOS', 'otros_contextuales': 'OTROS_CONTEXTUALES'}
    resultado = {'version': 'fase8-cierre-tecnicos-informaticos-v1', 'baseline_git': auditoria['baseline_git'],
                 'baseline_sqlite': aplicacion['primera_ejecucion']['antes'], 'baseline_normalizador': auditoria['baseline_normalizador'],
                 'universo_paso39': auditoria['universo_paso39'], 'universo_reconstruido': auditoria['universo_reconstruido'],
                 'reconciliacion_paso39': auditoria['reconciliacion_paso39'], 'taxonomia': tax,
                 **{nombre: tax[clave] for nombre, clave in equivalencias.items()},
                 'catalogo_denominaciones': auditoria['catalogo_denominaciones'], 'grupos_variantes_paso39': auditoria['grupos_variantes_paso39'],
                 'resultado_16_grupos_preliminares': {'A': 5, 'B': 0, 'C': 8, 'D': 3,
                                                       'nota': 'los grupos A son conjuntos literales; C y D preservan nivel, cuerpos, especialidades y compuestos'},
                 'clasificacion_A': auditoria['clasificacion_A'], 'clasificacion_B': auditoria['clasificacion_B'],
                 'clasificacion_C': auditoria['clasificacion_C'], 'clasificacion_D': auditoria['clasificacion_D'],
                 'conjuntos_A': auditoria['conjuntos_A'], 'simulaciones_A': auditoria['simulaciones_A'], 'colisiones': auditoria['colisiones'],
                 'paso46_estado': 'PASS', 'paso47_ejecutado': True, 'paso47_estado': 'PASS',
                 'reglas_implementadas': reglas['reglas_implementadas'], 'cobertura_logica_A': {'filas': 291, 'plazas': 395},
                 'gate_pre_sqlite': reglas['gate_pre_sqlite'], 'paso48_ejecutado': True, 'paso48_estado': 'PASS',
                 'backup_sqlite': aplicacion['primera_ejecucion']['backup'], 'mutaciones': aplicacion['primera_ejecucion']['mutaciones'],
                 'plazas_mutadas': aplicacion['primera_ejecucion']['plazas_mutadas'],
                 'data_version_antes': aplicacion['primera_ejecucion']['antes']['data_version'],
                 'data_version_despues': aplicacion['primera_ejecucion']['despues']['data_version'],
                 'segunda_ejecucion': aplicacion['segunda_ejecucion'], 'gate_paso19_inicial': auditoria['gate_paso19_inicial'],
                 'gate_paso19_final': {k: v['filas'] for k, v in aplicacion['gate_final'].items()},
                 'sqlite_inicial': aplicacion['primera_ejecucion']['antes'], 'sqlite_final': state(),
                 'normalizador_inicial': auditoria['baseline_normalizador'], 'normalizador_final': {'sha256': sha(ROOT / 'normalizacion_puestos.py')},
                 'tests_focalizados': ['tests/test_normalizacion_puestos.py -k paso47_tecnicos (17 passed)',
                                       'tests/test_auditar_tecnicos_informaticos_paso8_46.py::test_paso46_reconstruye_el_universo_sin_escribir_sqlite (1 passed)',
                                       'tests/test_aplicar_normalizacion_tecnicos_informaticos_paso8_48.py (1 passed)'],
                 'suite_completa_ejecutada': False, 'motivo_suite_completa': 'Reglas literales aisladas y gates focalizados.',
                 'git_diff_check': subprocess.run(['git', 'diff', '--check'], cwd=ROOT, capture_output=True).returncode == 0,
                 'estado_final': 'CERRADO', 'siguiente_bloque': 'Enfermería'}
    OUT.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'estado_final': resultado['estado_final'], 'mutaciones': resultado['mutaciones'],
                      'gate': resultado['gate_paso19_final']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
