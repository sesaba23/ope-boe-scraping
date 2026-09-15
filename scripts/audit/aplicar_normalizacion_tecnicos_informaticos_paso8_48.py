"""PASOS 47-48: aplicación transaccional de conjuntos informáticos cerrados."""
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
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate_auditar

DB = ROOT / 'datos/boe.db'
INF = ROOT / 'informes/normalizacion_puestos'
BACKUPS = ROOT / 'backups/sqlite'
OUT47 = INF / 'fase8_paso47_reglas_tecnicos_informaticos.json'
OUT48 = INF / 'fase8_paso48_aplicacion_tecnicos_informaticos.json'
CANONES = {'Técnico Informático', 'Técnico Auxiliar de Informática', 'Técnico Medio de Informática',
           'Técnico Superior de Informática', 'Técnico Superior Informático'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def plan():
    """Plan por resultado actual del normalizador, sin IDs preseleccionados."""
    conexion = sqlite3.connect(DB)
    conexion.row_factory = sqlite3.Row
    try:
        filas = []
        for fila in conexion.execute('select oposicion_id, puesto, puesto_normalizado, num_plazas from oposiciones'):
            nuevo = normalizar_puesto(fila['puesto'])
            if nuevo in CANONES and nuevo != fila['puesto_normalizado']:
                filas.append({'id': fila['oposicion_id'], 'puesto': fila['puesto'],
                              'puesto_normalizado_anterior': fila['puesto_normalizado'],
                              'puesto_normalizado_nuevo': nuevo, 'plazas': fila['num_plazas'],
                              'conjunto_A': nuevo, 'canon': nuevo})
        return filas
    finally:
        conexion.close()


def aplicar(*, backup=True, esperado=None):
    antes, filas = state(), plan()
    if esperado is not None and filas and len(filas) != esperado:
        raise RuntimeError(f'Plan {len(filas)} distinto del gate {esperado}')
    copia = None
    if backup and filas:
        BACKUPS.mkdir(parents=True, exist_ok=True)
        copia = BACKUPS / f"boe_paso48_tecnicos_informaticos_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}.db"
        shutil.copy2(DB, copia)
        if sha(copia) != antes['sha256']:
            raise RuntimeError('El backup no coincide con la SHA de origen')
        prueba = sqlite3.connect(copia)
        try:
            if prueba.execute('pragma integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup no legible')
        finally:
            prueba.close()
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
                conexion.rollback()
                raise RuntimeError('rowcount no coincide con el plan')
            if conexion.execute('pragma integrity_check').fetchone()[0] != 'ok' or list(conexion.execute('pragma foreign_key_check')):
                conexion.rollback()
                raise RuntimeError('Validación SQLite fallida antes de commit')
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
    gate = json.loads(Path('/tmp/fase8_paso47_gate.json').read_text(encoding='utf-8'))
    antes = state()
    plan_previo = plan()
    OUT47.write_text(json.dumps({
        'version': 'fase8-paso47-v1', 'modo': 'normalizador_sin_sqlite',
        'reglas_implementadas': sorted(CANONES),
        'cobertura_logica_A_global_filas': 291, 'cobertura_logica_A_global_plazas': 395,
        'filas_que_requieren_update': len(plan_previo), 'plazas_que_requieren_update': sum(f['plazas'] or 0 for f in plan_previo),
        'gate_pre_sqlite': gate, 'sqlite_antes': antes,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    primera = aplicar(esperado=gate['cambios_reales_recalculables']['filas'])
    segunda = aplicar(backup=False)
    resultado = {'version': 'fase8-paso48-v1', 'generado_utc': datetime.now(timezone.utc).isoformat(),
                 'primera_ejecucion': primera,
                 'segunda_ejecucion': {'mutaciones': segunda['mutaciones'], 'data_version': segunda['despues']['data_version']},
                 'gate_final': None}
    OUT48.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'mutaciones': primera['mutaciones'], 'segunda': segunda['mutaciones'],
                      'data_version': primera['despues']['data_version']}, ensure_ascii=False))


def finalizar():
    resultado = json.loads(OUT48.read_text(encoding='utf-8'))
    gate = gate_auditar(DB)
    resultado['gate_final'] = {k: {'filas': gate[k]['filas'], 'plazas': gate[k]['plazas']} for k in (
        'cambios_reales_recalculables', 'discrepancias_contextuales_no_recalculables', 'discrepancias_no_clasificables_automaticamente')}
    OUT48.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(resultado['gate_final'], ensure_ascii=False))


if __name__ == '__main__':
    finalizar() if '--finalizar' in sys.argv else ejecutar_aplicacion()
