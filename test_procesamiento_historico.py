import json
import pytest
from procesamiento_historico import *

def _estado(tmp_path):
    e=crear_estado("2004-01-01","2004-01-31",[{"Publicacion_ID":"A"},{"Publicacion_ID":"B"}], {"dias": 31})
    r=ruta_estado("2004-01-01","2004-01-31",tmp_path); guardar_estado(r,e); return e,r

def test_estado_atomico_reanudable_y_limite(tmp_path):
    e,r=_estado(tmp_path); assert len(pendientes(cargar_estado(r,"2004-01-01","2004-01-31"))[:1])==1
    registrar_resultado(e,"A","NO_CONVOCATORIA"); guardar_estado(r,e)
    assert [x["Publicacion_ID"] for x in pendientes(cargar_estado(r,"2004-01-01","2004-01-31"))]==["B"]

def test_estado_nuevo_conserva_metadatos_sumario_al_finalizar():
    e = crear_estado("2030-01-01", "2030-01-01", [{
        "Publicacion_ID": "A", "titulo": "Resolución del Ayuntamiento de X",
        "departamento": "Administración Local",
    }], [])
    registrar_resultado(e, "A", "NO_CONVOCATORIA", metadatos={
        "titulo": "Resolución del Ayuntamiento de X", "departamento": "Administración Local",
    })
    assert e["resultados"]["A"]["titulo"] == e["resultados"]["A"]["metadatos"]["titulo"]
    assert e["resultados"]["A"]["departamento"] == e["resultados"]["A"]["metadatos"]["departamento"]

def test_estado_antiguo_sin_metadatos_sigue_reanudable(tmp_path):
    e, r = _estado(tmp_path)
    e["resultados"]["A"].pop("titulo", None); e["resultados"]["A"].pop("departamento", None)
    guardar_estado(r, e)
    assert cargar_estado(r, "2004-01-01", "2004-01-31")["resultados"]["A"]["estado"] == "PENDIENTE"

def test_error_e_indeterminado_bloquean_escritura(tmp_path):
    e,_=_estado(tmp_path); registrar_resultado(e,"A","ERROR",error="x"); registrar_resultado(e,"B","INDETERMINADO")
    assert not puede_escribir_excel(e); assert pendientes(e,True)[0]["Publicacion_ID"]=="A"

def test_completado_solo_sin_bloqueos(tmp_path):
    e,_=_estado(tmp_path); registrar_resultado(e,"A","NO_CONVOCATORIA"); registrar_resultado(e,"B","CONVOCATORIA",[{"Puesto":"A","Num_plazas":1}])
    assert puede_escribir_excel(e); assert marcar_completado(e)["excel_escrito"]

def test_simulacion_498_reanuda_y_escribe_una_vez(tmp_path):
    publicaciones=[{"Publicacion_ID":str(i)} for i in range(498)]; llamadas=[]; vistos=[]
    descubrir=lambda:(publicaciones,{"dias":31})
    procesar=lambda p:(vistos.append(p["Publicacion_ID"]) or {"clasificacion":"NO_CONVOCATORIA"})
    e,_=ejecutar_intervalo("2004-01-01","2004-01-31",descubrir,procesar,lambda e:llamadas.append(1),directorio=tmp_path,limite=100)
    assert e["publicaciones_procesadas"]==100 and not llamadas
    e,_=ejecutar_intervalo("2004-01-01","2004-01-31",lambda:pytest.fail(),procesar,lambda e:llamadas.append(1),directorio=tmp_path,limite=100)
    assert e["publicaciones_procesadas"]==200 and len(set(vistos))==200
    e,escrito=ejecutar_intervalo("2004-01-01","2004-01-31",lambda:pytest.fail(),procesar,lambda e:llamadas.append(1),directorio=tmp_path)
    assert escrito and e["estado"]=="COMPLETADO" and llamadas==[1]
