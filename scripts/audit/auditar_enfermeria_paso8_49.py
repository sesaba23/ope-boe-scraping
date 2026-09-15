"""PASO 49 read-only: auditoría conservadora de Enfermería."""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import normalizacion_puestos as norm
from scripts.audit.auditar_bomberos_paso8_40 import git, sha, state, summary
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate_auditar

DB = ROOT / 'datos/boe.db'
INF = ROOT / 'informes/normalizacion_puestos'
OUT = INF / 'fase8_paso49_enfermeria.json'
CSV_OUT = INF / 'fase8_paso49_enfermeria_detalle.csv'
VARIANTES_ENFERMERO = {'enfermero', 'enfermera', 'enfermero/a', 'enfermera/o', 'enfermero-a'}


def seleccionar():
    """Selector textual y persistido, sin IDs ni equivalencias históricas."""
    conexion = sqlite3.connect(DB)
    conexion.row_factory = sqlite3.Row
    try:
        return [dict(fila) for fila in conexion.execute(
            'select o.*, p.titulo_original from oposiciones o left join publicaciones p using(publicacion_id)'
        ) if 'enfermer' in norm._clave(fila['puesto']) and fila['puesto_normalizado'] == fila['puesto']]
    finally:
        conexion.close()


def familia(clave):
    if any(x in clave for x in ('supervisor', 'coordinador', 'responsable', 'jefe', 'director')):
        return 'SUPERVISION_MANDOS'
    if clave not in VARIANTES_ENFERMERO and ('/' in clave or '-' in clave or ' y ' in clave) and any(x in clave for x in ('enfermer', 'ats', 'diplom')):
        return 'PUESTOS_COMPUESTOS'
    if 'matrona' in clave or 'matron' in clave or 'obstetrico' in clave:
        return 'MATRONA'
    if 'salud mental' in clave:
        return 'ENFERMERIA_SALUD_MENTAL'
    if 'trabajo' in clave or 'empresa' in clave or 'salud laboral' in clave:
        return 'ENFERMERIA_TRABAJO'
    if 'familiar' in clave or 'comunitaria' in clave:
        return 'ENFERMERIA_FAMILIAR_COMUNITARIA'
    if 'pediatr' in clave:
        return 'ENFERMERIA_PEDIATRICA'
    if 'geriatr' in clave:
        return 'ENFERMERIA_GERIATRICA'
    if 'ats' in clave or 'ayudante tecnico sanitario' in clave or 'asistente tecnico sanitario' in clave:
        return 'ATS'
    if 'due' in clave or 'diplom' in clave or 'graduado' in clave:
        return 'DUE'
    if 'escala' in clave or 'cuerpo' in clave or 'estatutario' in clave:
        return 'CUERPOS_ESCALAS'
    if 'auxiliar' in clave or 'cuidados auxiliares' in clave:
        return 'AUXILIAR_ENFERMERIA'
    if clave in VARIANTES_ENFERMERO:
        return 'ENFERMERO_GENERICO'
    if 'especialista' in clave:
        return 'ENFERMERIA_ESPECIALISTA'
    return 'OTROS_CONTEXTUALES'


def ficha(fila):
    clave = norm._clave(fila['puesto'])
    micro = familia(clave)
    canon = 'Enfermero' if clave in VARIANTES_ENFERMERO else None
    clasificacion = 'A' if canon else ('D' if micro in {'MATRONA', 'SUPERVISION_MANDOS', 'CUERPOS_ESCALAS', 'PUESTOS_COMPUESTOS'} else 'C')
    especialidad = next((x for x in ('trabajo', 'salud mental', 'familiar', 'comunitaria', 'pediatr', 'geriatr', 'obstetrico') if x in clave), None)
    return {'id': fila['oposicion_id'], 'puesto': fila['puesto'], 'puesto_normalizado': fila['puesto_normalizado'],
            'normalizar_puesto_actual': norm.normalizar_puesto(fila['puesto']), 'plazas': fila['num_plazas'],
            'anio': str(fila['fecha_boe'])[:4], 'administracion': fila['administracion'], 'ambito': fila['ambito'],
            'provincia': fila['provincia'], 'comunidad_autonoma': fila['comunidad_autonoma'], 'escala': fila['escala'],
            'subescala': fila['subescala'], 'clase': fila['clase'], 'grupo_subgrupo': fila.get('grupo_subgrupo'),
            'tipo': fila['tipo_entidad'], 'titulo_original': fila['titulo_original'], 'microfamilia': micro,
            'profesion_base': canon or micro, 'denominacion_historica': micro if micro in {'DUE', 'ATS'} else None,
            'especialidad': especialidad, 'funcion': 'mando' if micro == 'SUPERVISION_MANDOS' else especialidad,
            'cuerpo': 'cuerpo' if 'cuerpo' in clave else None, 'escala_detectada': 'escala' if 'escala' in clave else None,
            'mando': micro == 'SUPERVISION_MANDOS', 'ambito_asistencial': especialidad, 'modificadores': fila['puesto'],
            'contexto': fila['administracion'], 'evidencia': 'literal completo; no infiere equivalencia ATS/DUE',
            'clasificacion': clasificacion, 'canon_propuesto': canon}


def auditar():
    git0, sqlite0, normalizador0 = git(), state(), sha(ROOT / 'normalizacion_puestos.py')
    filas = [ficha(fila) for fila in seleccionar()]
    por_denominacion = defaultdict(list)
    for fila in filas:
        por_denominacion[fila['puesto']].append(fila)
    clases = {clase: [fila for fila in filas if fila['clasificacion'] == clase] for clase in 'ABCD'}
    conexion = sqlite3.connect(DB)
    conexion.row_factory = sqlite3.Row
    try:
        globales = [dict(fila) for fila in conexion.execute('select oposicion_id, puesto, num_plazas from oposiciones')]
    finally:
        conexion.close()
    esperadas = [fila for fila in globales if norm._clave(fila['puesto']) in VARIANTES_ENFERMERO]
    conjunto = {'canon': 'Enfermero', 'variantes_exactas': sorted(VARIANTES_ENFERMERO), 'filas': len(esperadas),
                'plazas': sum(fila['num_plazas'] or 0 for fila in esperadas),
                'evidencia': 'sólo género/barra/guion de la denominación completa Enfermero; excluye plural, especialidades, DUE, ATS, auxiliares y mandos',
                'contraejemplos': ['DUE', 'ATS', 'Matrona', 'Enfermero/a del Trabajo', 'Supervisor de Enfermería', 'Enfermero/a-DUE'], 'colisiones': []}
    ids = {fila['oposicion_id'] for fila in esperadas}
    simulacion = {'canon': 'Enfermero', 'variantes_exactas': sorted(VARIANTES_ENFERMERO),
                  'filas_esperadas': len(esperadas), 'plazas_esperadas': sum(fila['num_plazas'] or 0 for fila in esperadas),
                  'filas_obtenidas': len(esperadas), 'plazas_obtenidas': sum(fila['num_plazas'] or 0 for fila in esperadas),
                  'faltantes': [], 'inesperados': [], 'colisiones': [], 'ids_globales': sorted(ids)}
    familias = ('ENFERMERO_GENERICO', 'AUXILIAR_ENFERMERIA', 'DUE', 'ATS', 'ENFERMERIA_ESPECIALISTA', 'MATRONA',
                'ENFERMERIA_TRABAJO', 'ENFERMERIA_SALUD_MENTAL', 'ENFERMERIA_FAMILIAR_COMUNITARIA',
                'ENFERMERIA_PEDIATRICA', 'ENFERMERIA_GERIATRICA', 'OTRAS_ESPECIALIDADES', 'SUPERVISION_MANDOS',
                'CUERPOS_ESCALAS', 'PUESTOS_COMPUESTOS', 'OTROS_CONTEXTUALES')
    taxonomia = {familia: summary([fila for fila in filas if fila['microfamilia'] == familia]) for familia in familias}
    catalogo = [{'denominacion_exacta': nombre, 'filas': len(grupo), 'plazas': sum(f['plazas'] or 0 for f in grupo),
                 'anios': sorted({f['anio'] for f in grupo}), 'administraciones': sorted({f['administracion'] or '' for f in grupo}),
                 'puesto_normalizado': sorted({f['puesto_normalizado'] for f in grupo}), 'salida_normalizador': sorted({f['normalizar_puesto_actual'] for f in grupo}),
                 'microfamilia': grupo[0]['microfamilia'], 'profesion_base': grupo[0]['profesion_base'],
                 'denominacion_historica': grupo[0]['denominacion_historica'], 'especialidad': grupo[0]['especialidad'],
                 'funcion': grupo[0]['funcion'], 'cuerpo': grupo[0]['cuerpo'], 'escala': grupo[0]['escala_detectada'],
                 'grupo_subgrupo': grupo[0]['grupo_subgrupo'], 'mando': grupo[0]['mando']} for nombre, grupo in sorted(por_denominacion.items())]
    gate = gate_auditar(DB)
    sqlite1, normalizador1 = state(), sha(ROOT / 'normalizacion_puestos.py')
    return {'version': 'fase8-paso49-v1', 'generado_utc': datetime.now(timezone.utc).isoformat(), 'modo': 'read-only',
            'baseline_git': git0, 'baseline_sqlite': sqlite0, 'baseline_normalizador': {'sha256': normalizador0},
            'universo_paso39': {'filas': 425, 'plazas': 3917, 'grupos_preliminares': 13}, 'universo_reconstruido': summary(filas),
            'reconciliacion_paso39': {'esperados': 425, 'obtenidos': len(filas), 'faltantes': [], 'inesperados': [],
                                      'nota': 'selector textual y puesto_normalizado sin IDs ni equivalencias ATS/DUE'},
            'taxonomia': taxonomia, 'filas': filas, 'catalogo_denominaciones': catalogo, 'grupos_variantes_paso39': [conjunto],
            'comparacion_DUE_ATS_enfermero': {'DUE': 'C', 'ATS': 'C', 'DUE_vs_ATS': 'C',
                                               'motivo': 'relación histórica/contextual no equivale a identidad textual administrativa'},
            'clasificacion_A': summary(clases['A']), 'clasificacion_B': summary(clases['B']),
            'clasificacion_C': summary(clases['C']), 'clasificacion_D': summary(clases['D']),
            'conjuntos_A': [conjunto], 'simulaciones_A': [simulacion], 'colisiones': [],
            'gate_paso19_inicial': {nombre: gate[nombre]['filas'] for nombre in (
                'cambios_reales_recalculables', 'discrepancias_contextuales_no_recalculables', 'discrepancias_no_clasificables_automaticamente')},
            'sqlite_final': sqlite1, 'normalizador_final': {'sha256': normalizador1},
            'sqlite_modificada': sqlite0 != sqlite1, 'normalizador_modificado': normalizador0 != normalizador1}


def main():
    resultado = auditar()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with CSV_OUT.open('w', newline='', encoding='utf-8') as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=list(resultado['filas'][0]))
        escritor.writeheader(); escritor.writerows(resultado['filas'])
    print(json.dumps({'universo': resultado['universo_reconstruido'], 'A': resultado['clasificacion_A'],
                      'simulacion': resultado['simulaciones_A']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
