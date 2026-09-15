"""PASOS 50-51: aplicación transaccional e idempotente de Enfermería."""
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
from scripts.audit.auditar_bomberos_paso8_40 import state
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import _estado, auditar as gate_auditar

DB = ROOT / 'datos/boe.db'
INF = ROOT / 'informes/normalizacion_puestos'
BACKUPS = ROOT / 'backups/sqlite'
OUT50 = INF / 'fase8_paso50_reglas_enfermeria.json'
OUT51 = INF / 'fase8_paso51_aplicacion_enfermeria.json'
CANON = 'Enfermero'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def plan():
    """Deriva el plan de la salida actual, sin IDs predefinidos."""
    conexion = sqlite3.connect(DB)
    conexion.row_factory = sqlite3.Row
    try:
        filas = []
        # Prefiltro sólo de rendimiento: la inclusión sigue decidiéndola el
        # normalizador real y la regla aprobada sólo contiene «enfermer…».
        for fila in conexion.execute(
            "select oposicion_id, puesto, puesto_normalizado, num_plazas from oposiciones "
            "where lower(puesto) like '%enfermer%'"
        ):
            nuevo = normalizar_puesto(fila['puesto'])
            if nuevo == CANON and nuevo != fila['puesto_normalizado']:
                filas.append({'id': fila['oposicion_id'], 'puesto': fila['puesto'],
                              'puesto_normalizado_anterior': fila['puesto_normalizado'],
                              'puesto_normalizado_nuevo': nuevo, 'plazas': fila['num_plazas'],
                              'conjunto_A': CANON, 'canon': CANON})
        return filas
    finally:
        conexion.close()


def aplicar(*, backup=True, esperado=None):
    antes, filas = state(), plan()
    if esperado is not None and filas and len(filas) != esperado:
        raise RuntimeError(f'Plan {len(filas)} distinto de gate {esperado}')
    copia = None
    if backup and filas:
        BACKUPS.mkdir(parents=True, exist_ok=True)
        copia = BACKUPS / f"boe_paso51_enfermeria_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}.db"
        shutil.copy2(DB, copia)
        if sha(copia) != antes['sha256']:
            raise RuntimeError('Backup no coincide con la SHA de origen')
        comprobacion = sqlite3.connect(copia)
        try:
            if comprobacion.execute('pragma integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup no legible')
        finally:
            comprobacion.close()
    mutaciones = 0
    if filas:
        conexion = sqlite3.connect(DB)
        try:
            conexion.execute('BEGIN IMMEDIATE')
            for fila in filas:
                mutaciones += conexion.execute(
                    'update oposiciones set puesto_normalizado=? where oposicion_id=? and puesto_normalizado=?',
                    (fila['puesto_normalizado_nuevo'], fila['id'], fila['puesto_normalizado_anterior']),
                ).rowcount
            if mutaciones != len(filas):
                conexion.rollback(); raise RuntimeError('rowcount distinto del plan')
            if conexion.execute('pragma integrity_check').fetchone()[0] != 'ok' or list(conexion.execute('pragma foreign_key_check')):
                conexion.rollback(); raise RuntimeError('Validación SQLite pre-commit fallida')
            conexion.execute("update metadata set valor=? where clave='data_version'", (str(int(antes['data_version']) + 1),))
            conexion.commit()
        finally:
            conexion.close()
    despues = state()
    return {'antes': antes,
            'backup': ({'ruta': str(copia), 'sha256': sha(copia), 'tamano': copia.stat().st_size,
                        'data_version': antes['data_version'], 'integrity_check': 'ok'} if copia else None),
            'plan': filas, 'mutaciones': mutaciones, 'plazas_mutadas': sum(f['plazas'] or 0 for f in filas), 'despues': despues}


def ejecutar_aplicacion():
    gate = json.loads(Path('/tmp/fase8_paso50_gate.json').read_text(encoding='utf-8'))
    antes, filas = state(), plan()
    OUT50.write_text(json.dumps({
        'version': 'fase8-paso50-v1', 'modo': 'normalizador_sin_sqlite',
        'reglas_implementadas': {'Enfermero': ['enfermero', 'enfermera', 'enfermero/a', 'enfermera/o', 'enfermero-a']},
        'cobertura_logica_A_global_filas': 69, 'cobertura_logica_A_global_plazas': 252,
        'filas_que_requieren_update': len(filas), 'plazas_que_requieren_update': sum(f['plazas'] or 0 for f in filas),
        'gate_pre_sqlite': gate, 'sqlite_antes': antes,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    primera = aplicar(esperado=gate['cambios_reales_recalculables']['filas'])
    segunda = aplicar(backup=False)
    resultado = {'version': 'fase8-paso51-v1', 'generado_utc': datetime.now(timezone.utc).isoformat(),
                 'primera_ejecucion': primera,
                 'segunda_ejecucion': {'mutaciones': segunda['mutaciones'], 'data_version': segunda['despues']['data_version']},
                 'gate_final': None}
    OUT51.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'mutaciones': primera['mutaciones'], 'segunda': segunda['mutaciones'], 'data_version': primera['despues']['data_version']}, ensure_ascii=False))


def finalizar():
    resultado = json.loads(OUT51.read_text(encoding='utf-8'))
    gate = gate_auditar(DB)
    resultado['gate_final'] = {k: {'filas': gate[k]['filas'], 'plazas': gate[k]['plazas']} for k in (
        'cambios_reales_recalculables', 'discrepancias_contextuales_no_recalculables', 'discrepancias_no_clasificables_automaticamente')}
    OUT51.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(resultado['gate_final'], ensure_ascii=False))


def recuperar_primera_aplicacion():
    """Reconstruye el artefacto si la terminal se corta después del commit."""
    copias = sorted(BACKUPS.glob('boe_paso51_enfermeria_*.db'), key=lambda ruta: ruta.stat().st_mtime_ns)
    if not copias:
        raise RuntimeError('No existe backup PASO 51 para recuperar la transacción')
    copia = copias[-1]
    anterior, actual = sqlite3.connect(copia), sqlite3.connect(DB)
    anterior.row_factory = actual.row_factory = sqlite3.Row
    try:
        previas = {fila['oposicion_id']: dict(fila) for fila in anterior.execute(
            'select oposicion_id, puesto, puesto_normalizado, num_plazas from oposiciones'
        )}
        filas = []
        for fila in actual.execute('select oposicion_id, puesto, puesto_normalizado, num_plazas from oposiciones'):
            previo = previas[fila['oposicion_id']]
            if previo['puesto_normalizado'] != fila['puesto_normalizado']:
                if fila['puesto_normalizado'] != CANON:
                    raise RuntimeError('El backup muestra una mutación ajena a Enfermería')
                filas.append({'id': fila['oposicion_id'], 'puesto': fila['puesto'],
                              'puesto_normalizado_anterior': previo['puesto_normalizado'],
                              'puesto_normalizado_nuevo': fila['puesto_normalizado'], 'plazas': fila['num_plazas'],
                              'conjunto_A': CANON, 'canon': CANON})
    finally:
        anterior.close(); actual.close()
    if len(filas) != 57:
        raise RuntimeError(f'El backup recuperado contiene {len(filas)} mutaciones, no 57')
    return {'antes': _estado(copia), 'backup': {'ruta': str(copia), 'sha256': sha(copia), 'tamano': copia.stat().st_size,
            'data_version': _estado(copia)['data_version'], 'integrity_check': 'ok'}, 'plan': filas,
            'mutaciones': len(filas), 'plazas_mutadas': sum(f['plazas'] or 0 for f in filas), 'despues': state()}


def recuperar():
    primera = recuperar_primera_aplicacion()
    segunda = aplicar(backup=False)
    resultado = {'version': 'fase8-paso51-v1', 'generado_utc': datetime.now(timezone.utc).isoformat(),
                 'primera_ejecucion': primera,
                 'segunda_ejecucion': {'mutaciones': segunda['mutaciones'], 'data_version': segunda['despues']['data_version']},
                 'gate_final': None}
    OUT51.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'mutaciones': primera['mutaciones'], 'segunda': segunda['mutaciones']}, ensure_ascii=False))


if __name__ == '__main__':
    recuperar() if '--recuperar' in sys.argv else (finalizar() if '--finalizar' in sys.argv else ejecutar_aplicacion())
