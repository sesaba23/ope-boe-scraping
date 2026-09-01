"""Identificación exacta y propagación segura de universidades."""
import json
from pathlib import Path
from mapa_plazas import normalizar_nombre_municipal

RUTA = Path(__file__).resolve().parent / "datos" / "universidades.v1.json"

def catalogo(ruta=RUTA):
    datos=json.loads(Path(ruta).read_text())
    indice={}
    for fila in datos['universidades']:
        for nombre in [fila['nombre'],*fila.get('aliases',[])]: indice[normalizar_nombre_municipal(nombre)]=fila['nombre']
    return datos,indice

def detectar(texto, indice=None):
    _,indice=catalogo() if indice is None else (None,indice)
    valor=normalizar_nombre_municipal(texto or '')
    encontrados={canon for clave,canon in indice.items() if clave in valor}
    return next(iter(encontrados)) if len(encontrados)==1 else None
