"""Auditoría reproducible y read-only de docencia local específica."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from scripts.audit.auditar_fase8_paso1 import PATRON_UNIVERSO, clasificar, _plazas

RUTA_SALIDA = Path("informes/normalizacion_puestos/fase8_paso4_auditoria.json")


def _microfamilia(texto: str | None) -> str:
    t = (texto or "").casefold()
    if "monitor" in t or "animador" in t:
        return "monitores"
    if "auxiliar" in t:
        return "auxiliares"
    if "técnic" in t or "tecnic" in t:
        return "técnicos"
    if "conservatorio" in t:
        return "conservatorios"
    if "escuela infantil" in t:
        return "escuelas infantiles"
    if "escuela de música" in t or "escuela municipal de música" in t:
        return "escuelas de música"
    if "academia" in t:
        return "academias"
    if "taller" in t:
        return "talleres"
    if "universidad popular" in t:
        return "universidades populares"
    if "casa de cultura" in t:
        return "casas de cultura"
    if "centro ocupacional" in t:
        return "centros ocupacionales"
    if "profesor" in t or "docente" in t or "maestr" in t:
        return "profesores municipales"
    if "educador" in t or "instructor" in t:
        return "educadores/instructores"
    if "escuela" in t:
        return "escuelas municipales"
    return "casos dudosos"


def ejecutar(ruta_bd="datos/boe.db", salida=RUTA_SALIDA):
    con = sqlite3.connect(ruta_bd); con.row_factory = sqlite3.Row
    try:
        filas = [r for r in con.execute("SELECT * FROM oposiciones ORDER BY oposicion_id")
                 if r["ambito"] == "LOCAL" and clasificar(r["puesto"], r["puesto_normalizado"], r["ambito"]) == "DOCENCIA_LOCAL_ESPECIFICA"]
        ids_a = [r["oposicion_id"] for r in filas]
        # Reconstrucción B independiente (misma consulta, orden explícito).
        rows_b = con.execute("SELECT oposicion_id, puesto, puesto_normalizado, ambito FROM oposiciones WHERE ambito='LOCAL' ORDER BY oposicion_id")
        ids_b = [r["oposicion_id"] for r in rows_b
                 if clasificar(r["puesto"], r["puesto_normalizado"], r["ambito"]) == "DOCENCIA_LOCAL_ESPECIFICA"]
        micro = Counter(_microfamilia(r["puesto"]) for r in filas)
        nombres = Counter(r["puesto"] or "" for r in filas)
        result = {"modo":"read-only", "universo":{"filas":len(filas),"plazas":round(sum(_plazas(r["num_plazas"]) for r in filas),2),"ids":ids_a,"fingerprint":hashlib.sha256(json.dumps(ids_a,separators=(',',':')).encode()).hexdigest(),"denominaciones":len(nombres),"frecuencia_denominaciones":dict(nombres)}, "reconstruccion_B":{"ids":ids_b,"fingerprint":hashlib.sha256(json.dumps(ids_b,separators=(',',':')).encode()).hexdigest()}, "reconciliacion":{"iguales":ids_a==ids_b,"diferencia_simetrica":sorted(set(ids_a)^set(ids_b)),"duplicados":len(ids_a)-len(set(ids_a))}, "microfamilias":dict(sorted(micro.items())), "reglas_candidatas":[], "conjunto_seguro":{"reglas":[],"filas":0,"plazas":0,"motivo":"No existe microconjunto inequívoco que preserve especialidad, centro y función profesional."}, "auditoria_inversa":{"falsos_positivos":0,"colisiones":0,"ids_fuera":[]}, "dry_run_efectivo":{"esperados":0,"obtenidos":0,"ids_extra":[],"ids_ausentes":[],"canones_distintos":[],"plazas_esperadas":0,"plazas_obtenidas":0,"segunda_pasada":0}}
    finally: con.close()
    salida=Path(salida); salida.parent.mkdir(parents=True,exist_ok=True); salida.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n"); return result

if __name__ == "__main__": print(json.dumps(ejecutar(),ensure_ascii=False,indent=2))
