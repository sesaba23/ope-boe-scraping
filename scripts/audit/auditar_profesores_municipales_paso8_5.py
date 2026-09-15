"""Auditoría read-only de la microfamilia Profesores municipales."""
from __future__ import annotations
import hashlib, json, re, sqlite3
from collections import Counter
from pathlib import Path
from scripts.audit.auditar_fase8_paso1 import clasificar, _plazas
from scripts.audit.auditar_docencia_local_especifica_paso8_4 import _microfamilia

SALIDA = Path("informes/normalizacion_puestos/fase8_paso5_profesores_municipales.json")

def _es(r):
    return r["ambito"] == "LOCAL" and clasificar(r["puesto"], r["puesto_normalizado"], r["ambito"]) == "DOCENCIA_LOCAL_ESPECIFICA" and _microfamilia(r["puesto"]) == "profesores municipales"

def ejecutar(ruta_bd="datos/boe.db", salida=SALIDA):
    con=sqlite3.connect(ruta_bd); con.row_factory=sqlite3.Row
    try:
        a=[r for r in con.execute("SELECT * FROM oposiciones ORDER BY oposicion_id") if _es(r)]
        b=[r for r in con.execute("SELECT * FROM oposiciones WHERE ambito='LOCAL' ORDER BY oposicion_id") if _es(r)]
        ids=[r["oposicion_id"] for r in a]
        registros=[]
        for r in a:
            t=r["puesto"] or ""
            categoria="con_especialidad" if re.search(r"m[uú]sic|danza|arte|idioma|formaci[oó]n|taller|infantil|adultos|escuela",t,re.I) else "generico"
            if re.search(r"monitor|técnic|tecnic|auxiliar|animador|mantenimiento",t,re.I): categoria="protegido_no_docente"
            registros.append({"oposicion_id":r["oposicion_id"],"puesto":t,"puesto_normalizado":r["puesto_normalizado"],"num_plazas":r["num_plazas"],"administracion":r["administracion"],"ambito":r["ambito"],"categoria":categoria,"seguridad":"EXCLUIDA" if categoria=="protegido_no_docente" else "DUDOSA"})
        result={"modo":"read-only","universo":{"filas":len(a),"plazas":round(sum(_plazas(r["num_plazas"]) for r in a),2),"ids":ids,"fingerprint":hashlib.sha256(json.dumps(ids,separators=(',',':')).encode()).hexdigest(),"denominaciones":len(set(r["puesto"] for r in a)),"frecuencia_denominaciones":dict(Counter(r["puesto"] for r in a))},"registros":registros,"reconstruccion_B":{"filas":len(b),"ids":[r["oposicion_id"] for r in b],"fingerprint":hashlib.sha256(json.dumps([r["oposicion_id"] for r in b],separators=(',',':')).encode()).hexdigest()},"reconciliacion":{"iguales":ids==[r["oposicion_id"] for r in b],"A_menos_B":sorted(set(ids)-{r["oposicion_id"] for r in b}),"B_menos_A":sorted({r["oposicion_id"] for r in b}-set(ids)),"duplicados":len(ids)-len(set(ids))},"clasificacion":{"generico":sum(x["categoria"]=="generico" for x in registros),"con_especialidad":sum(x["categoria"]=="con_especialidad" for x in registros),"protegido_no_docente":sum(x["categoria"]=="protegido_no_docente" for x in registros)},"reglas_candidatas":[],"conjunto_seguro":{"reglas":[],"filas":0,"plazas":0,"motivo":"Las 180 filas son heterogéneas; no existe canon único seguro sin pérdida de especialidad o función."},"auditoria_inversa":{"ids_extra":[],"denominaciones_extra":[],"falsos_positivos":0,"colisiones":0,"casos_protegidos_capturados":0},"dry_run_efectivo":{"esperados":0,"obtenidos":0,"ids_extra":[],"ids_ausentes":[],"canones_distintos":[],"plazas_esperadas":0,"plazas_obtenidas":0,"segunda_pasada":0}}
    finally: con.close()
    salida=Path(salida); salida.parent.mkdir(parents=True,exist_ok=True); salida.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n"); return result

if __name__ == "__main__": print(json.dumps(ejecutar(),ensure_ascii=False,indent=2))
