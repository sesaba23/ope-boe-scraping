"""Dry-run read-only de normalización contextual policial de Fase 7."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from normalizacion_contextual_puestos import normalizar_puesto_contextual


def _estado(ruta):
    stat = ruta.stat()
    with sqlite3.connect(f"file:{ruta}?mode=ro", uri=True) as con:
        m = dict(con.execute("SELECT clave,valor FROM metadata WHERE clave IN ('schema_version','data_version')"))
        n, plazas = con.execute("SELECT COUNT(*),COALESCE(SUM(num_plazas),0) FROM oposiciones").fetchone()
        return {"sha256": hashlib.sha256(ruta.read_bytes()).hexdigest(), "tamano": stat.st_size, "mtime_ns": stat.st_mtime_ns, "schema_version": int(m['schema_version']), "data_version": int(m['data_version']), "oposiciones": n, "plazas": plazas, "integrity_check": con.execute("PRAGMA integrity_check").fetchone()[0], "foreign_key_check": con.execute("PRAGMA foreign_key_check").fetchall(), "wal_existe": ruta.with_name(ruta.name+'-wal').exists(), "shm_existe": ruta.with_name(ruta.name+'-shm').exists()}


def ejecutar(ruta_bd="datos/boe.db"):
    ruta = Path(ruta_bd).resolve(); inicial = _estado(ruta)
    with sqlite3.connect(f"file:{ruta}?mode=ro", uri=True) as con:
        con.row_factory = sqlite3.Row; filas = con.execute("SELECT * FROM oposiciones ORDER BY oposicion_id").fetchall()
    propuestas = []; inversa = defaultdict(list); idempotencia = []
    for fila in filas:
        r = normalizar_puesto_contextual(fila['puesto'], administracion=fila['administracion'], ambito=fila['ambito'], tipo_entidad=fila['tipo_entidad'], escala=fila['escala'], subescala=fila['subescala'], sistema=fila['sistema'], municipio=fila['municipio'], provincia=fila['provincia'])
        # El dry-run informa exclusivamente de propuestas pendientes; tras una
        # aplicación correcta la misma regla puede seguir ser aplicable, pero
        # no debe contarse si el valor persistido ya es el canónico.
        if r.regla and r.normalizado != fila['puesto_normalizado']:
            entrada = {"oposicion_id": fila['oposicion_id'], "puesto": fila['puesto'], "puesto_normalizado_actual": fila['puesto_normalizado'], "propuesta": r.normalizado, "regla": r.regla, "evidencia": r.evidencia, "confianza": r.confianza, "plazas": fila['num_plazas'], "administracion": fila['administracion'], "ambito": fila['ambito'], "tipo_entidad": fila['tipo_entidad'], "escala": fila['escala'], "subescala": fila['subescala'], "clase": fila['clase'], "municipio": fila['municipio'], "provincia": fila['provincia']}
            propuestas.append(entrada); inversa[r.regla].append(entrada)
            segunda = normalizar_puesto_contextual(r.normalizado, administracion=fila['administracion'], ambito=fila['ambito'], tipo_entidad=fila['tipo_entidad'], escala=fila['escala'], subescala=fila['subescala'], sistema=fila['sistema'], municipio=fila['municipio'], provincia=fila['provincia'])
            if segunda.normalizado != r.normalizado: idempotencia.append(entrada)
    final = _estado(ruta)
    resumen_reglas = {regla: {"filas": len(items), "plazas": sum(i['plazas'] or 0 for i in items), "puestos_distintos": sorted({i['puesto'] for i in items}), "administraciones_distintas": len({i['administracion'] for i in items}), "ambitos": sorted({i['ambito'] for i in items}), "tipos_entidad": sorted({i['tipo_entidad'] for i in items})} for regla, items in inversa.items()}
    return {"version": "fase7-paso5-v1", "generado_utc": datetime.now(timezone.utc).isoformat(), "diseno_api": "normalizar_puesto_contextual(puesto, *, administracion, ambito, tipo_entidad, escala, subescala, sistema, municipio, provincia) -> ResultadoNormalizacionContextual", "precedencia": ["normalización textual", "puesto policial aislado", "reglas contextuales de evidencia positiva", "sin cambio"], "sqlite_inicial": inicial, "sqlite_final": final, "propuestas": propuestas, "resumen_reglas": resumen_reglas, "total_propuestas": len(propuestas), "plazas_propuestas": sum(i['plazas'] or 0 for i in propuestas), "auditoria_inversa": resumen_reglas, "idempotencia_fallos": idempotencia, "casos_rechazados": [27123,27694,28254], "conclusion": "apto" if len(propuestas) <= 329 and not idempotencia and inicial == final else "requiere_revision"}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bd',default='datos/boe.db');p.add_argument('--salida',default='informes/normalizacion_puestos/fase7_policia_contextual_paso5.json');a=p.parse_args(argv)
    r=ejecutar(a.bd);s=Path(a.salida);s.parent.mkdir(parents=True,exist_ok=True);s.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps({'total_propuestas':r['total_propuestas'],'plazas_propuestas':r['plazas_propuestas'],'resumen_reglas':r['resumen_reglas'],'idempotencia_fallos':len(r['idempotencia_fallos']),'conclusion':r['conclusion']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
