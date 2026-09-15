"""Dry-run read-only de la única regla aprobada de Ayudantes penitenciarios."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3

from normalizacion_puestos import _clave, _preparar_texto, normalizar_puesto


OBJETIVO = "ayudantes de instituciones penitenciarias por el sistema general de acceso libre"
CANON = "Ayudantes de Instituciones Penitenciarias"


def ejecutar(ruta_bd="datos/boe.db"):
    with sqlite3.connect(f"file:{Path(ruta_bd).resolve()}?mode=ro", uri=True) as con:
        con.row_factory=sqlite3.Row; filas=[dict(x) for x in con.execute("select oposicion_id,fecha_boe,puesto,puesto_normalizado,num_plazas,administracion,ambito,sistema,turno from oposiciones order by oposicion_id")]
    relacionadas=[f for f in filas if "instituciones penitenciarias" in _clave(_preparar_texto(f['puesto']) or '')]
    aprobadas=[]
    for f in relacionadas:
        propuesta=normalizar_puesto(f['puesto']); f['propuesta']=propuesta
        if _clave(_preparar_texto(f['puesto']) or '')==OBJETIVO and propuesta!=f['puesto_normalizado']:
            aprobadas.append(f)
    otras_seguras=[f for f in relacionadas if _clave(_preparar_texto(f['puesto']) or '')=="ayudantes de instituciones penitenciarias"]
    return {'universo_filas':len(relacionadas),'universo_plazas':sum(f['num_plazas'] or 0 for f in relacionadas),'aprobadas':aprobadas,'filas_modificables':len(aprobadas),'plazas_afectadas':sum(f['num_plazas'] or 0 for f in aprobadas),'otras_seis_seguras_ya_canonicas':otras_seguras,'promocion_interna':[f for f in relacionadas if f['puesto']=='Ayudantes Instituciones Penitenciarias'],'sanitarios':[f for f in relacionadas if 'Técnicos Sanitarios' in f['puesto']],'enfermeros':[f for f in relacionadas if 'Enfermeros' in f['puesto']],'idempotencia_fallos':[f for f in aprobadas if normalizar_puesto(f['propuesta'])!=f['propuesta']]}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bd',default='datos/boe.db');p.add_argument('--salida',default='informes/normalizacion_puestos/fase7_ayudantes_instituciones_penitenciarias_paso7b_dry_run.json');a=p.parse_args(argv);r=ejecutar(a.bd);s=Path(a.salida);s.parent.mkdir(parents=True,exist_ok=True);s.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps({k:r[k] for k in ('universo_filas','universo_plazas','filas_modificables','plazas_afectadas','idempotencia_fallos')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
