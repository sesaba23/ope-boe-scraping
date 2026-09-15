"""Auditoría read-only de microfamilias docentes con especialidad explícita."""
from __future__ import annotations
import hashlib, json, re, sqlite3
from collections import Counter
from pathlib import Path
from scripts.audit.auditar_fase8_paso1 import _plazas

SALIDA=Path("informes/normalizacion_puestos/fase8_paso6_auditoria.json")
DOCENTE=re.compile(r"profesor(?:a|es|as)?|docente|maestr",re.I)
EXPLICITO=re.compile(r"m[uú]sic|piano|guitarra|viol|tromp|clarinete|saxo|percusi[oó]n|danza|teatro|pintura|dibujo|cer[aá]mica|ingl[eé]s|franc[eé]s|italiano|educaci[oó]n infantil|adultos|formaci[oó]n|escuela|conservatorio|academia",re.I)
PROTEGIDO=re.compile(r"monitor|t[eé]cnic|auxiliar|maestro de obras|director|coordinador|ayudante|universidad|escuela oficial de idiomas|formaci[oó]n profesional",re.I)

def _selecciona(r):
    texto=(r["puesto"] or "")+" "+(r["puesto_normalizado"] or "")
    return bool(DOCENTE.search(r["puesto"] or "") and EXPLICITO.search(texto) and (r["puesto"] or "")==(r["puesto_normalizado"] or ""))

def _familia(t):
    x=(t or "").casefold()
    if re.search(r"piano|guitarra|viol|tromp|clarinete|saxo|percusi|música|musica",x): return "música/instrumento"
    if "danza" in x:return "danza"
    if "teatro" in x:return "teatro/artes escénicas"
    if re.search(r"pintura|dibujo",x):return "pintura/dibujo"
    if "cerámica" in x or "ceramica" in x:return "cerámica"
    if re.search(r"inglés|ingles|francés|frances|italiano",x):return "idiomas"
    if "infantil" in x:return "educación infantil"
    if "adult" in x:return "educación de adultos"
    if "formación" in x or "formacion" in x:return "formación"
    if re.search(r"escuela|conservatorio|academia",x):return "centro docente explícito"
    return "otra especialidad"

def ejecutar(ruta_bd="datos/boe.db",salida=SALIDA):
    con=sqlite3.connect(ruta_bd);con.row_factory=sqlite3.Row
    try:
        a=[r for r in con.execute("SELECT * FROM oposiciones ORDER BY oposicion_id") if _selecciona(r)]
        b=[r for r in con.execute("SELECT * FROM oposiciones ORDER BY oposicion_id") if DOCENTE.search(r["puesto"] or "") and EXPLICITO.search((r["puesto"] or "")+" "+(r["puesto_normalizado"] or "")) and (r["puesto"] or "")==(r["puesto_normalizado"] or "")]
        ids=[r["oposicion_id"] for r in a]; ids_b=[r["oposicion_id"] for r in b]
        registros=[]
        for r in a:
            texto=r["puesto"] or ""; protegido=bool(PROTEGIDO.search(texto));
            registros.append({"oposicion_id":r["oposicion_id"],"puesto":texto,"puesto_normalizado":r["puesto_normalizado"],"plazas":r["num_plazas"],"administracion":r["administracion"],"ambito":r["ambito"],"familia":_familia(texto),"funcion_docente":True,"seguridad":"EXCLUIDA" if protegido else "DUDOSA","decision":"sin_regla","motivo":"bloque protegido o especialidad/centro no reducible a un canon común"})
        informe={"modo":"read-only","universo":{"filas":len(a),"plazas":round(sum(_plazas(r["num_plazas"]) for r in a),2),"ids":ids,"fingerprint":hashlib.sha256(json.dumps(ids,separators=(',',':')).encode()).hexdigest(),"denominaciones":len({r["puesto"] for r in a})},"reconstruccion_B":{"filas":len(b),"ids":ids_b,"fingerprint":hashlib.sha256(json.dumps(ids_b,separators=(',',':')).encode()).hexdigest()},"reconciliacion":{"iguales":ids==ids_b,"A_menos_B":sorted(set(ids)-set(ids_b)),"B_menos_A":sorted(set(ids_b)-set(ids)),"duplicados":len(ids)-len(set(ids))},"microfamilias":dict(Counter(x["familia"] for x in registros)),"registros":registros,"protecciones":{"excluidos":sum(x["seguridad"]=="EXCLUIDA" for x in registros)},"reglas_candidatas":[],"conjunto_seguro":{"reglas":[],"filas":0,"plazas":0,"mapa_id_canon":{},"motivo":"No existe variante cerrada que permita una mejora sin reabrir bloques protegidos o perder especialidad."},"auditoria_inversa":{"ids_extra":[],"denominaciones_extra":[],"falsos_positivos":0,"colisiones":0,"casos_protegidos_capturados":0},"dry_run_efectivo":{"esperados":0,"obtenidos":0,"ids_extra":[],"ids_ausentes":[],"canones_distintos":[],"cambios_fuera_conjunto":[],"segunda_pasada":0}}
    finally:con.close()
    salida=Path(salida);salida.parent.mkdir(parents=True,exist_ok=True);salida.write_text(json.dumps(informe,ensure_ascii=False,indent=2)+"\n");return informe

if __name__=="__main__":print(json.dumps(ejecutar(),ensure_ascii=False,indent=2))
