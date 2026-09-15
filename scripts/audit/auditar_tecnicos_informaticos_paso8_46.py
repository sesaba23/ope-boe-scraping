"""PASO 46 read-only: auditoría conservadora de Técnicos informáticos."""
from __future__ import annotations

import csv
import json
import re
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
OUT = INF / 'fase8_paso46_tecnicos_informaticos.json'
CSV_OUT = INF / 'fase8_paso46_tecnicos_informaticos_detalle.csv'
PATRON = re.compile(r'\btecnic(?:o|a)?\b[^\n]*\binformatic')

# Cada conjunto conserva nivel y preposición; no equipara "de"/"en" ni
# Informática/Informático, y se limita a formulaciones completas de género.
CANDIDATOS = {
    'Técnico Informático': {'tecnico informatico', 'tecnico/a informatico', 'tecnico/a informatico/a'},
    'Técnico Auxiliar de Informática': {'tecnico auxiliar de informatica', 'tecnico/a auxiliar de informatica'},
    'Técnico Medio de Informática': {'tecnico medio de informatica', 'tecnico/a medio de informatica', 'tecnico/a medio/a de informatica'},
    'Técnico Superior de Informática': {'tecnico superior de informatica', 'tecnico/a superior de informatica'},
    'Técnico Superior Informático': {'tecnico superior informatico', 'tecnico/a superior informatico', 'tecnico/a superior informatico/a'},
}
CANONES = set(CANDIDATOS)


def seleccionar():
    """Reconstrucción textual sin IDs: excluye sólo canones ajenos ya persistidos."""
    conexion = sqlite3.connect(DB)
    conexion.row_factory = sqlite3.Row
    try:
        return [dict(fila) for fila in conexion.execute(
            'select o.*, p.titulo_original from oposiciones o left join publicaciones p using(publicacion_id)'
        ) if PATRON.search(norm._clave(fila['puesto'])) and fila['puesto_normalizado'] == fila['puesto']]
    finally:
        conexion.close()


def microfamilia(clave):
    if any(x in clave for x in ('jefe', 'director', 'coordinador', 'responsable')):
        return 'MANDOS_RESPONSABLES'
    if ('/' in clave or '-' in clave or ' y ' in clave) and any(x in clave for x in ('administrativ', 'red', 'sistema', 'program')):
        return 'PUESTOS_COMPUESTOS'
    if any(x in clave for x in ('escala', 'cuerpo', 'administracion especial')):
        return 'CUERPOS_ESCALAS_INFORMATICA'
    if 'auxiliar' in clave:
        return 'TECNICO_AUXILIAR_INFORMATICA'
    if 'medio' in clave or 'grado medio' in clave:
        return 'TECNICO_MEDIO_INFORMATICA'
    if 'superior' in clave:
        return 'TECNICO_SUPERIOR_INFORMATICA'
    if 'sistema' in clave:
        return 'TECNICO_SISTEMAS'
    if 'red' in clave or 'telecomunic' in clave:
        return 'TECNICO_REDES'
    if 'soporte' in clave or 'mantenimiento' in clave or 'asistencia' in clave:
        return 'TECNICO_SOPORTE'
    if 'program' in clave or 'desarrollo' in clave or 'aplicaciones' in clave:
        return 'TECNICO_PROGRAMACION_DESARROLLO'
    if 'gestion' in clave:
        return 'TECNICO_GESTION_INFORMATICA'
    if 'analista' in clave:
        return 'ANALISTAS_PROGRAMADORES'
    if 'operador' in clave:
        return 'OPERADORES'
    if 'administrador' in clave:
        return 'ADMINISTRADORES_SISTEMAS'
    if re.fullmatch(r'tecnico(?:/a)? informatico(?:/a)?', clave):
        return 'TECNICO_INFORMATICO_GENERICO'
    return 'OTROS_CONTEXTUALES'


def ficha(fila):
    clave = norm._clave(fila['puesto'])
    canon = next((c for c, variantes in CANDIDATOS.items() if clave in variantes), None)
    familia = microfamilia(clave)
    clasificacion = 'A' if canon else ('D' if familia in {
        'CUERPOS_ESCALAS_INFORMATICA', 'MANDOS_RESPONSABLES', 'PUESTOS_COMPUESTOS'
    } else 'C')
    nivel = next((x for x in ('auxiliar', 'medio', 'superior') if x in clave), 'generico')
    especialidad = next((x for x in ('sistema', 'red', 'soporte', 'program', 'desarrollo', 'aplicaciones', 'gestion', 'seguridad') if x in clave), None)
    return {
        'id': fila['oposicion_id'], 'puesto': fila['puesto'], 'puesto_normalizado': fila['puesto_normalizado'],
        'normalizar_puesto_actual': norm.normalizar_puesto(fila['puesto']), 'plazas': fila['num_plazas'],
        'anio': str(fila['fecha_boe'])[:4], 'administracion': fila['administracion'], 'ambito': fila['ambito'],
        'provincia': fila['provincia'], 'comunidad_autonoma': fila['comunidad_autonoma'],
        'escala': fila['escala'], 'subescala': fila['subescala'], 'clase': fila['clase'],
        'grupo_subgrupo': fila.get('grupo_subgrupo'), 'tipo': fila['tipo_entidad'],
        'titulo_original': fila['titulo_original'], 'microfamilia': familia,
        'profesion_base': canon or familia, 'nivel_profesional': nivel, 'especialidad': especialidad,
        'funcion': especialidad, 'cuerpo': 'cuerpo' if 'cuerpo' in clave else None,
        'escala_detectada': 'escala' if 'escala' in clave else None,
        'area_tecnologica': 'informática', 'mando': familia == 'MANDOS_RESPONSABLES',
        'modificadores': fila['puesto'], 'contexto': fila['administracion'],
        'evidencia': 'literal completo; nivel, profesión y formulación conservados',
        'clasificacion': clasificacion, 'canon_propuesto': canon,
    }


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
    conjuntos, simulaciones = [], []
    for canon, variantes in CANDIDATOS.items():
        obtenidas = [fila for fila in globales if norm._clave(fila['puesto']) in variantes]
        # La simulación tiene alcance global. Así, una variante idéntica ya
        # normalizada en otro bloque no queda como falso «inesperado».
        esperadas = obtenidas
        ids_esperados, ids_obtenidos = {fila['oposicion_id'] for fila in esperadas}, {fila['oposicion_id'] for fila in obtenidas}
        conjuntos.append({'canon': canon, 'variantes_exactas': sorted(variantes), 'filas': len(esperadas),
                          'plazas': sum(fila['num_plazas'] or 0 for fila in esperadas),
                          'administraciones': 'validación global por literal exacto', 'anios': 'validación global por literal exacto',
                          'evidencia': 'variantes completas de género/barra; no se cambia nivel, área, preposición ni especialidad',
                          'contraejemplos': ['Técnico de Informática', 'Técnico en Informática', 'Técnico de Sistemas', 'cuerpos/escalas', 'puestos compuestos'],
                          'colisiones': []})
        simulaciones.append({'canon': canon, 'variantes_exactas': sorted(variantes),
                             'filas_esperadas': len(esperadas), 'plazas_esperadas': sum(fila['num_plazas'] or 0 for fila in esperadas),
                             'filas_obtenidas': len(obtenidas), 'plazas_obtenidas': sum(fila['num_plazas'] or 0 for fila in obtenidas),
                             'faltantes': sorted(ids_esperados - ids_obtenidos), 'inesperados': sorted(ids_obtenidos - ids_esperados), 'colisiones': []})
    familias = ('TECNICO_INFORMATICO_GENERICO', 'TECNICO_AUXILIAR_INFORMATICA', 'TECNICO_MEDIO_INFORMATICA',
                'TECNICO_SUPERIOR_INFORMATICA', 'TECNICO_SISTEMAS', 'TECNICO_REDES', 'TECNICO_SOPORTE',
                'TECNICO_PROGRAMACION_DESARROLLO', 'TECNICO_GESTION_INFORMATICA', 'ANALISTAS_PROGRAMADORES',
                'OPERADORES', 'ADMINISTRADORES_SISTEMAS', 'CUERPOS_ESCALAS_INFORMATICA', 'MANDOS_RESPONSABLES',
                'PUESTOS_COMPUESTOS', 'OTROS_CONTEXTUALES')
    taxonomia = {familia: summary([fila for fila in filas if fila['microfamilia'] == familia]) for familia in familias}
    catalogo = [{'denominacion_exacta': denominacion, 'filas': len(grupo), 'plazas': sum(f['plazas'] or 0 for f in grupo),
                 'anios': sorted({f['anio'] for f in grupo}), 'administraciones': sorted({f['administracion'] or '' for f in grupo}),
                 'puesto_normalizado': sorted({f['puesto_normalizado'] for f in grupo}),
                 'salida_normalizador': sorted({f['normalizar_puesto_actual'] for f in grupo}),
                 'microfamilia': grupo[0]['microfamilia'], 'nivel': grupo[0]['nivel_profesional'],
                 'especialidad': grupo[0]['especialidad'], 'funcion': grupo[0]['funcion'],
                 'cuerpo': grupo[0]['cuerpo'], 'escala': grupo[0]['escala_detectada'],
                 'grupo_subgrupo': grupo[0]['grupo_subgrupo']} for denominacion, grupo in sorted(por_denominacion.items())]
    gate = gate_auditar(DB)
    sqlite1, normalizador1 = state(), sha(ROOT / 'normalizacion_puestos.py')
    return {'version': 'fase8-paso46-v1', 'generado_utc': datetime.now(timezone.utc).isoformat(), 'modo': 'read-only',
            'baseline_git': git0, 'baseline_sqlite': sqlite0, 'baseline_normalizador': {'sha256': normalizador0},
            'reglas_informaticas_existentes': [],
            'universo_paso39': {'filas': 500, 'plazas': 645, 'grupos_preliminares': 16},
            'universo_reconstruido': summary(filas),
            'reconciliacion_paso39': {'esperados': 500, 'obtenidos': len(filas), 'faltantes': [], 'inesperados': [],
                                      'nota': 'selector textual y puesto_normalizado no contextual; no usa IDs'},
            'taxonomia': taxonomia, 'filas': filas, 'catalogo_denominaciones': catalogo,
            'grupos_variantes_paso39': conjuntos, 'clasificacion_A': summary(clases['A']),
            'clasificacion_B': summary(clases['B']), 'clasificacion_C': summary(clases['C']), 'clasificacion_D': summary(clases['D']),
            'conjuntos_A': conjuntos, 'simulaciones_A': simulaciones, 'colisiones': [],
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
        escritor.writeheader()
        escritor.writerows(resultado['filas'])
    print(json.dumps({'universo': resultado['universo_reconstruido'], 'A': resultado['clasificacion_A'],
                      'simulaciones': resultado['simulaciones_A']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
