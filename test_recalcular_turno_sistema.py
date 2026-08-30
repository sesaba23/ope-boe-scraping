import sqlite3

import base_datos
import recalcular_turno_sistema as modulo

def _base(tmp_path):
    ruta=tmp_path/'boe.db'; con=base_datos.conectar(ruta); base_datos.crear_esquema(con)
    con.execute("INSERT INTO publicaciones VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",("B","x","2026-01-01","x",None,None,"1","x",0,None,None,None,None,None,None,None))
    for turno,sistema in (("Turno libre.","Concurso oposición"),("--","--")):
        con.execute("INSERT INTO oposiciones(puesto,administracion,escala,subescala,clase,sistema,turno,fecha_boe,fecha_boe_original,enlace,publicacion_id,version_extractor) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",("X",None,"--","--","--",sistema,turno,"2026-01-01","x","x","B","1"))
    base_datos.guardar_metadata(con,data_version=6); con.commit(); con.close(); return ruta

def test_recalculo_dry_run_e_idempotencia(tmp_path):
    ruta=_base(tmp_path)
    seco=modulo.recalcular(ruta,tmp_path/'b',dry_run=True)
    assert seco['filas_cambiadas']==1 and seco['backup'] is None and seco['data_version']=='6'
    hecho=modulo.recalcular(ruta,tmp_path/'b')
    assert hecho['filas_cambiadas']==1 and hecho['data_version']=='7'
    assert modulo.recalcular(ruta,tmp_path/'b2')['filas_cambiadas']==0
    con=sqlite3.connect(ruta); assert con.execute('select turno,sistema from oposiciones where oposicion_id=1').fetchone()==('Turno Libre','Concurso-Oposición')
