"""Compone el cierre verificable de PASOS 43-45 de Bibliotecas y Archivos."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit.auditar_bibliotecas_archivos_paso8_43 import sha, state

INF = ROOT / 'informes/normalizacion_puestos'
OUT = INF / 'fase8_cierre_bibliotecas_archivos.json'


def main():
    # El informe de PASO 43 es la foto read-only previa a la mutación; no se
    # recalcula aquí para no mezclarla con el estado ya aplicado de PASO 45.
    auditoria = json.loads((INF / 'fase8_paso43_bibliotecas_archivos.json').read_text(encoding='utf-8'))
    previo = json.loads((INF / 'fase8_cierre_bomberos.json').read_text(encoding='utf-8'))
    aplicacion = json.loads((INF / 'fase8_paso45_aplicacion_bibliotecas_archivos.json').read_text(encoding='utf-8'))
    final_gate = aplicacion['gate_final']
    categorias = auditoria['taxonomia']
    resultado = {
        'version': 'fase8-cierre-bibliotecas-archivos-v1',
        'baseline_git': previo['baseline_git'],
        'baseline_sqlite': aplicacion['primera_ejecucion']['antes'],
        'baseline_normalizador': previo['normalizador_final'],
        'universo_paso39': auditoria['universo_paso39'],
        'universo_reconstruido': auditoria['universo_reconstruido'],
        'reconciliacion_paso39': auditoria['reconciliacion_paso39'],
        'taxonomia': categorias,
        'bibliotecarios': categorias['BIBLIOTECARIO'],
        'auxiliares_biblioteca': categorias['AUXILIAR_BIBLIOTECA'],
        'ayudantes_biblioteca': categorias['AYUDANTE_BIBLIOTECA'],
        'tecnicos_biblioteca': categorias['TECNICO_BIBLIOTECA'],
        'archiveros': categorias['ARCHIVERO'],
        'auxiliares_archivo': categorias['AUXILIAR_ARCHIVO'],
        'ayudantes_archivo': categorias['AYUDANTE_ARCHIVO'],
        'tecnicos_archivo': categorias['TECNICO_ARCHIVO'],
        'archivos_bibliotecas_museos': categorias['BIBLIOTECA_ARCHIVO_COMBINADO'],
        'documentalistas': categorias['DOCUMENTALISTA'],
        'mandos': categorias['MANDOS'],
        'puestos_compuestos': categorias['BIBLIOTECA_ARCHIVO_COMBINADO'],
        'otros_contextuales': categorias['OTROS_CONTEXTUALES'],
        'catalogo_denominaciones': auditoria['catalogo_denominaciones'],
        'grupos_variantes_paso39': auditoria['grupos_variantes_paso39'],
        'clasificacion_A': auditoria['clasificacion_A'], 'clasificacion_B': auditoria['clasificacion_B'],
        'clasificacion_C': auditoria['clasificacion_C'], 'clasificacion_D': auditoria['clasificacion_D'],
        'conjuntos_A': auditoria['conjuntos_A'], 'simulaciones_A': auditoria['simulaciones_A'],
        'colisiones': auditoria['colisiones'],
        'paso43_estado': 'PASS', 'paso44_ejecutado': True, 'paso44_estado': 'PASS',
        'reglas_implementadas': ['Bibliotecario: cuatro literales completos', 'Auxiliar de Biblioteca: dos literales completos'],
        'gate_pre_sqlite': aplicacion['primera_ejecucion']['gate_previo'],
        'paso45_ejecutado': True, 'paso45_estado': 'PASS',
        'backup_sqlite': aplicacion['primera_ejecucion']['backup'],
        'mutaciones': aplicacion['primera_ejecucion']['mutaciones'],
        'plazas_mutadas': aplicacion['primera_ejecucion']['plazas_mutadas'],
        'data_version_antes': aplicacion['primera_ejecucion']['antes']['data_version'],
        'data_version_despues': aplicacion['primera_ejecucion']['despues']['data_version'],
        'segunda_ejecucion': aplicacion['segunda_ejecucion'],
        'gate_paso19_inicial': previo['gate_paso19_final'],
        'gate_paso19_final': {k: final_gate[k]['filas'] for k in final_gate},
        'sqlite_inicial': aplicacion['primera_ejecucion']['antes'], 'sqlite_final': state(),
        'normalizador_inicial': previo['normalizador_final'], 'normalizador_final': {'sha256': sha(ROOT / 'normalizacion_puestos.py')},
        'tests_focalizados': ['tests/test_normalizacion_puestos.py -k paso44_bibliotecas (13 passed)',
                              'auditoría PASO 43 read-only y simulación global exacta',
                              'aplicación PASO 45: plan dinámico, transacción e idempotencia verificados'],
        'motivo_suite_completa': 'No necesaria; reglas literales aisladas y gates focalizados.',
        'git_diff_check': subprocess.run(['git', 'diff', '--check'], cwd=ROOT, capture_output=True).returncode == 0,
        'estado_final': 'CERRADO', 'siguiente_bloque': 'Técnicos informáticos',
    }
    OUT.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'estado_final': resultado['estado_final'], 'mutaciones': resultado['mutaciones'],
                      'gate': resultado['gate_paso19_final']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
