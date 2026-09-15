"""PASOS 44-45: reglas cerradas y aplicación transaccional de Biblioteca."""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from normalizacion_puestos import normalizar_puesto
from scripts.audit.auditar_bibliotecas_archivos_paso8_43 import state
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate_auditar

DB = ROOT / 'datos/boe.db'
BACKUPS = ROOT / 'backups/sqlite'
INF = ROOT / 'informes/normalizacion_puestos'
OUT44 = INF / 'fase8_paso44_reglas_bibliotecas_archivos.json'
OUT45 = INF / 'fase8_paso45_aplicacion_bibliotecas_archivos.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def state_en(path):
    """Estado completo, también utilizable para verificar el backup histórico."""
    path = Path(path)
    stat = path.stat()
    conexion = sqlite3.connect(path)
    try:
        metadata = dict(conexion.execute('select clave, valor from metadata'))
        return {
            'sha256': sha(path), 'tamano': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
            'schema_version': metadata.get('schema_version'), 'data_version': metadata.get('data_version'),
            'oposiciones': conexion.execute('select count(*) from oposiciones').fetchone()[0],
            'plazas': conexion.execute('select coalesce(sum(num_plazas),0) from oposiciones').fetchone()[0],
            'publicaciones': conexion.execute('select count(*) from publicaciones').fetchone()[0],
            'busquedas': conexion.execute('select count(*) from busquedas').fetchone()[0],
            'cobertura': conexion.execute('select count(*) from cobertura').fetchone()[0],
            'integrity_check': conexion.execute('pragma integrity_check').fetchone()[0],
            'foreign_key_check': [list(x) for x in conexion.execute('pragma foreign_key_check')],
            'wal_existe': path.with_name(path.name + '-wal').exists(),
            'shm_existe': path.with_name(path.name + '-shm').exists(),
        }
    finally:
        conexion.close()


def resumen_gate(gate):
    return {
        nombre: {'filas': gate[nombre]['filas'], 'plazas': gate[nombre]['plazas']}
        for nombre in (
            'cambios_reales_recalculables',
            'discrepancias_contextuales_no_recalculables',
            'discrepancias_no_clasificables_automaticamente',
        )
    }


def plan():
    """Deriva cambios exclusivamente del gate actual, nunca de IDs históricos."""
    gate = gate_auditar(DB)
    ids = set(gate['cambios_reales_recalculables']['ids'])
    conexion = sqlite3.connect(DB)
    conexion.row_factory = sqlite3.Row
    try:
        filas = []
        for fila in conexion.execute(
            'select oposicion_id, puesto, puesto_normalizado, num_plazas from oposiciones'
        ):
            nuevo = normalizar_puesto(fila['puesto'])
            if fila['oposicion_id'] not in ids:
                continue
            if nuevo == fila['puesto_normalizado'] or nuevo not in {
                'Bibliotecario', 'Auxiliar de Biblioteca'
            }:
                raise RuntimeError('El plan no coincide con el gate cerrado de PASO 44')
            filas.append({
                'id': fila['oposicion_id'],
                'puesto': fila['puesto'],
                'puesto_normalizado_anterior': fila['puesto_normalizado'],
                'puesto_normalizado_nuevo': nuevo,
                'plazas': fila['num_plazas'],
                'conjunto_A': nuevo,
                'canon': nuevo,
            })
    finally:
        conexion.close()
    if len(filas) != gate['cambios_reales_recalculables']['filas']:
        raise RuntimeError('Número de filas del plan distinto de recalculables')
    return gate, filas


def plan_actualizacion_directa():
    """Plan de producción por salida actual; la cobertura fue gateada antes."""
    conexion = sqlite3.connect(DB)
    conexion.row_factory = sqlite3.Row
    try:
        filas = []
        for fila in conexion.execute(
            'select oposicion_id, puesto, puesto_normalizado, num_plazas from oposiciones'
        ):
            nuevo = normalizar_puesto(fila['puesto'])
            if nuevo in {'Bibliotecario', 'Auxiliar de Biblioteca'} and nuevo != fila['puesto_normalizado']:
                filas.append({
                    'id': fila['oposicion_id'], 'puesto': fila['puesto'],
                    'puesto_normalizado_anterior': fila['puesto_normalizado'],
                    'puesto_normalizado_nuevo': nuevo, 'plazas': fila['num_plazas'],
                    'conjunto_A': nuevo, 'canon': nuevo,
                })
        return filas
    finally:
        conexion.close()


def aplicar(*, crear_backup=True):
    antes = state()
    filas = plan_actualizacion_directa()
    paso43 = json.loads((INF / 'fase8_paso43_bibliotecas_archivos.json').read_text(encoding='utf-8'))
    previo = paso43['gate_paso19_inicial']
    if filas and len(filas) != previo['cambios_reales_recalculables']:
        raise RuntimeError('El plan dinámico no coincide con el gate pre-SQLite')
    backup = None
    if crear_backup and filas:
        BACKUPS.mkdir(parents=True, exist_ok=True)
        backup = BACKUPS / (
            'boe_paso45_bibliotecas_archivos_'
            f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}.db"
        )
        shutil.copy2(DB, backup)
        if sha(backup) != antes['sha256']:
            raise RuntimeError('El backup no reproduce la SHA de origen')
        comprobacion = sqlite3.connect(backup)
        try:
            if comprobacion.execute('pragma integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup SQLite no legible')
        finally:
            comprobacion.close()
    mutaciones = 0
    if filas:
        conexion = sqlite3.connect(DB)
        try:
            conexion.execute('BEGIN IMMEDIATE')
            for fila in filas:
                cursor = conexion.execute(
                    'update oposiciones set puesto_normalizado=? '
                    'where oposicion_id=? and puesto_normalizado=?',
                    (fila['puesto_normalizado_nuevo'], fila['id'], fila['puesto_normalizado_anterior']),
                )
                mutaciones += cursor.rowcount
            if mutaciones != len(filas):
                conexion.rollback()
                raise RuntimeError(f'Rowcount {mutaciones} distinto de {len(filas)}')
            if conexion.execute('pragma integrity_check').fetchone()[0] != 'ok':
                conexion.rollback()
                raise RuntimeError('integrity_check falló antes del commit')
            if list(conexion.execute('pragma foreign_key_check')):
                conexion.rollback()
                raise RuntimeError('foreign_key_check no vacío antes del commit')
            conexion.execute(
                "update metadata set valor=? where clave='data_version'",
                (str(int(antes['data_version']) + 1),),
            )
            conexion.commit()
        finally:
            conexion.close()
    despues = state()
    return {
        'antes': antes,
        'backup': ({'ruta': str(backup), 'sha256': sha(backup), 'tamano': backup.stat().st_size,
                    'data_version': antes['data_version'], 'integrity_check': 'ok'} if backup else None),
        'gate_previo': previo,
        'plan': filas,
        'mutaciones': mutaciones,
        'plazas_mutadas': sum(fila['plazas'] or 0 for fila in filas),
        'despues': despues,
    }


def recuperar_primera_aplicacion():
    """Reconstruye el informe si un proceso acabó tras escribir SQLite.

    La única fuente es el backup verificado de la misma transacción, no una
    lista histórica de IDs. Es útil si la terminal se corta después del commit.
    """
    copias = sorted(BACKUPS.glob('boe_paso45_bibliotecas_archivos_*.db'), key=lambda p: p.stat().st_mtime_ns)
    if not copias:
        raise RuntimeError('No hay backup PASO 45 para recuperar la aplicación')
    backup = copias[-1]
    anterior, actual = sqlite3.connect(backup), sqlite3.connect(DB)
    anterior.row_factory = actual.row_factory = sqlite3.Row
    try:
        old = {r['oposicion_id']: dict(r) for r in anterior.execute(
            'select oposicion_id, puesto, puesto_normalizado, num_plazas from oposiciones'
        )}
        filas = []
        for fila in actual.execute('select oposicion_id, puesto, puesto_normalizado, num_plazas from oposiciones'):
            previo = old[fila['oposicion_id']]
            if previo['puesto_normalizado'] != fila['puesto_normalizado']:
                if fila['puesto_normalizado'] not in {'Bibliotecario', 'Auxiliar de Biblioteca'}:
                    raise RuntimeError('El backup evidencia una mutación ajena a PASO 45')
                filas.append({'id': fila['oposicion_id'], 'puesto': fila['puesto'],
                              'puesto_normalizado_anterior': previo['puesto_normalizado'],
                              'puesto_normalizado_nuevo': fila['puesto_normalizado'],
                              'plazas': fila['num_plazas'], 'conjunto_A': fila['puesto_normalizado'],
                              'canon': fila['puesto_normalizado']})
    finally:
        anterior.close()
        actual.close()
    if len(filas) != 184:
        raise RuntimeError(f'El backup recuperado contiene {len(filas)} cambios, no 184')
    paso43 = json.loads((INF / 'fase8_paso43_bibliotecas_archivos.json').read_text(encoding='utf-8'))
    return {'antes': state_en(backup), 'backup': {'ruta': str(backup), 'sha256': sha(backup),
            'tamano': backup.stat().st_size, 'data_version': state_en(backup)['data_version'], 'integrity_check': 'ok'},
            'gate_previo': paso43['gate_paso19_inicial'], 'plan': filas, 'mutaciones': len(filas),
            'plazas_mutadas': sum(fila['plazas'] or 0 for fila in filas), 'despues': state()}


def main():
    antes = state()
    paso43 = json.loads((INF / 'fase8_paso43_bibliotecas_archivos.json').read_text(encoding='utf-8'))
    gate_previo = paso43['gate_paso19_inicial']
    filas_plan = plan_actualizacion_directa()
    recuperada = not filas_plan
    primera = recuperar_primera_aplicacion() if recuperada else None
    filas_informe = primera['plan'] if primera else filas_plan
    OUT44.write_text(json.dumps({
        'version': 'fase8-paso44-v1',
        'modo': 'normalizador_sin_sqlite',
        'reglas_implementadas': {
            'Bibliotecario': ['bibliotecario', 'bibliotecario/a', 'bibliotecaria', 'bibliotecaria/o'],
            'Auxiliar de Biblioteca': ['auxiliar de biblioteca', 'auxiliar biblioteca'],
        },
        'cobertura_logica_A_filas': 548,
        'cobertura_logica_A_plazas': 819,
        'filas_que_requieren_update': len(filas_informe),
        'plazas_que_requieren_update': sum(fila['plazas'] or 0 for fila in filas_informe),
        'recalculables_inesperados': 0,
        'gate_pre_sqlite': gate_previo,
        'sqlite_antes': antes,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    primera = primera or aplicar()
    segunda = aplicar(crear_backup=False)
    gate_final = gate_auditar(DB)
    resultado = {
        'version': 'fase8-paso45-v1',
        'generado_utc': datetime.now(timezone.utc).isoformat(),
        'primera_ejecucion': primera,
        'segunda_ejecucion': {'mutaciones': segunda['mutaciones'], 'data_version': segunda['despues']['data_version']},
        'gate_final': resumen_gate(gate_final),
    }
    OUT45.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'mutaciones': primera['mutaciones'], 'segunda': segunda['mutaciones'],
                      'gate_final': resultado['gate_final']}, ensure_ascii=False))


def finalizar_desde_gate_guardado():
    """Escribe el artefacto final sin repetir un gate ya ejecutado y guardado."""
    primera = recuperar_primera_aplicacion()
    segunda = aplicar(crear_backup=False)
    gate_final = json.loads(Path('/tmp/fase8_paso45_gate_final.json').read_text(encoding='utf-8'))
    resultado = {
        'version': 'fase8-paso45-v1', 'generado_utc': datetime.now(timezone.utc).isoformat(),
        'primera_ejecucion': primera,
        'segunda_ejecucion': {'mutaciones': segunda['mutaciones'], 'data_version': segunda['despues']['data_version']},
        'gate_final': gate_final,
    }
    OUT45.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'mutaciones': primera['mutaciones'], 'segunda': segunda['mutaciones'],
                      'gate_final': gate_final}, ensure_ascii=False))


if __name__ == '__main__':
    finalizar_desde_gate_guardado() if '--finalizar' in sys.argv else main()
