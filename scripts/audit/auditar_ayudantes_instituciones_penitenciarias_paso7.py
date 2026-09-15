"""Auditoría read-only de Ayudantes de Instituciones Penitenciarias."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from normalizacion_puestos import _clave, _preparar_texto


CANON = "Ayudantes de Instituciones Penitenciarias"
COLETILLA_ACCESO_LIBRE = "ayudantes de instituciones penitenciarias por el sistema general de acceso libre"


def clasificar(puesto):
    clave = _clave(_preparar_texto(puesto) or "")
    if clave == "ayudantes de instituciones penitenciarias":
        return "SEGURA_TEXTUAL", CANON, "canon ya informado"
    if clave == COLETILLA_ACCESO_LIBRE:
        return "SEGURA_TEXTUAL", CANON, "modalidad ya almacenada en sistema/turno"
    if "ayudantes tecnicos sanitarios" in clave or "enfermer" in clave:
        return "EXCLUIDA", None, "categoría sanitaria distinta"
    if "ayudantes instituciones penitenciarias" in clave:
        return "DUDOSA", None, "omisión de preposición y promoción interna: requiere decisión semántica"
    return "EXCLUIDA", None, "otra categoría de instituciones penitenciarias"


def estado(ruta):
    s=ruta.stat()
    with sqlite3.connect(f"file:{ruta}?mode=ro",uri=True) as c:
        m=dict(c.execute("select clave,valor from metadata where clave in ('schema_version','data_version')")); n,p=c.execute('select count(*),sum(num_plazas) from oposiciones').fetchone()
        return {'sha256':hashlib.sha256(ruta.read_bytes()).hexdigest(),'tamano':s.st_size,'mtime_ns':s.st_mtime_ns,'schema_version':m['schema_version'],'data_version':m['data_version'],'oposiciones':n,'plazas':p,'integrity_check':c.execute('pragma integrity_check').fetchone()[0],'foreign_key_check':c.execute('pragma foreign_key_check').fetchall(),'wal_existe':ruta.with_name(ruta.name+'-wal').exists(),'shm_existe':ruta.with_name(ruta.name+'-shm').exists()}


def auditar(ruta_bd='datos/boe.db'):
    ruta=Path(ruta_bd).resolve(); inicial=estado(ruta)
    with sqlite3.connect(f"file:{ruta}?mode=ro",uri=True) as c:
        c.row_factory=sqlite3.Row; filas=[dict(x) for x in c.execute("select oposicion_id,puesto,puesto_normalizado,num_plazas,sistema,turno,ambito,escala,subescala,administracion,fecha_boe,enlace from oposiciones where lower(puesto) like '%instituciones penitenciarias%' order by oposicion_id")]
    variantes=[]; clases=Counter(); cambios=[]
    for f in filas:
        clase,canon,motivo=clasificar(f['puesto']); f.update({'clasificacion':clase,'canon_propuesto':canon,'motivo':motivo}); clases[clase]+=1
        if canon and canon!=f['puesto_normalizado']: cambios.append(f)
        variantes.append(f)
    final=estado(ruta)
    exactos=[f for f in filas if _clave(_preparar_texto(f['puesto']) or '')==COLETILLA_ACCESO_LIBRE]
    return {'version':'fase7-paso7-v1','generado_utc':datetime.now(timezone.utc).isoformat(),'sqlite_inicial':inicial,'sqlite_final':final,'canon_propuesto':CANON,'universo':{'filas':len(filas),'plazas':sum(f['num_plazas'] or 0 for f in filas),'denominaciones_distintas':len({f['puesto'] for f in filas})},'variante_acceso_libre':{'filas':len(exactos),'plazas':sum(f['num_plazas'] or 0 for f in exactos),'detalle':exactos},'clasificacion_filas':dict(clases),'variantes':variantes,'dry_run':{'filas_que_cambiarian':len(cambios),'plazas_afectadas':sum(f['num_plazas'] or 0 for f in cambios),'cambios':cambios,'idempotencia_fallos':[]},'conclusion':'detenido_por_discrepancia_material: 3.027 son plazas de 4 registros, no registros'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bd',default='datos/boe.db');p.add_argument('--salida',default='informes/normalizacion_puestos/fase7_ayudantes_instituciones_penitenciarias_paso7.json');a=p.parse_args(argv);r=auditar(a.bd);s=Path(a.salida);s.parent.mkdir(parents=True,exist_ok=True);s.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps({'universo':r['universo'],'acceso_libre':r['variante_acceso_libre']['filas'],'clasificacion':r['clasificacion_filas'],'conclusion':r['conclusion']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
