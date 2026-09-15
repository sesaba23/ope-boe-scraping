"""Auditoría read-only del personal técnico/auxiliar de escuela infantil (Fase 8.10)."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from normalizacion_puestos import _clave

SALIDA = Path("informes/normalizacion_puestos/fase8_paso10_personal_escuela_infantil.json")

_PROF = re.compile(r"\b(?:t[eé]cnico(?:/a)?|auxiliar(?:/a)?|educador(?:/a)?|maestro(?:/a)?|monitor(?:/a)?|cuidador(?:/a)?|director(?:/a)?|profesor(?:/a)?)\b", re.I)
_INF = re.compile(r"\b(?:escuela|escuelas|educaci[oó]n|educador|auxiliar|t[eé]cnico|jard[ií]n|guarder[ií]a|infantil|infantiles)\b", re.I)


def _texto(r):
    return " ".join(str(r[k] or "") for k in ("puesto", "puesto_normalizado"))


def _incluye(r):
    t = _texto(r)
    return bool(re.search(r"\binfantil(?:es)?\b", t, re.I))


def _clasifica(puesto):
    k = _clave(puesto or "")
    if "escuela infantil" in k or "escuelas infantiles" in k:
        if "tecnico superior" in k: return "TECNICO_SUPERIOR_ESCUELA_INFANTIL"
        if "tecnico especialista" in k: return "TECNICO_ESPECIALISTA_ESCUELA_INFANTIL"
        if re.search(r"\btecnico\b", k): return "TECNICO_ESCUELA_INFANTIL"
        if re.search(r"\bauxiliar\b", k): return "AUXILIAR_ESCUELA_INFANTIL"
        if re.search(r"\b(educador|maestro|monitor|cuidador|director|profesor)\b", k):
            return "CENTRO_SIN_CATEGORIA_PROFESIONAL" if k.startswith("escuela") else "DIRECCION_COORDINACION" if re.search(r"director|coordinador", k) else "OTRO_TECNICO"
        return "CENTRO_SIN_CATEGORIA_PROFESIONAL"
    if re.search(r"auxiliar tecnico", k): return "AUXILIAR_TECNICO_INFANTIL"
    if re.search(r"auxiliar", k): return "AUXILIAR_EDUCACION_INFANTIL"
    if re.search(r"tecnico superior", k): return "TECNICO_SUPERIOR_EDUCACION_INFANTIL"
    if re.search(r"tecnico especialista", k): return "TECNICO_ESPECIALISTA_EDUCACION_INFANTIL"
    if re.search(r"tecnico", k): return "TECNICO_EDUCACION_INFANTIL"
    if re.search(r"educador", k): return "EDUCADOR_INFANTIL"
    if re.search(r"maestro", k): return "MAESTRO_EDUCACION_INFANTIL"
    if re.search(r"monitor|cuidador", k): return "MONITOR_CUIDADOR"
    if re.search(r"director|coordinador", k): return "DIRECCION_COORDINACION"
    return "DUDOSA"


def _profesion_centro(puesto):
    k = _clave(puesto or "")
    if "escuela infantil" in k and re.search(r"\b(tecnico|auxiliar|educador|maestro)\b", k):
        return "ESCUELA_INFANTIL_PARTE_PROFESION"
    if "escuela infantil" in k: return "ESCUELA_INFANTIL_SOLO_CENTRO"
    return "AMBIGUO"


def _ficha(r):
    cat = _clasifica(r["puesto"])
    protegido = r["puesto_normalizado"] in {"Maestro de Educación Infantil", "Educador Infantil"} or (r["puesto_normalizado"] or "").startswith("Técnico") and "Educación Infantil" in (r["puesto_normalizado"] or "")
    k = _clave(r["puesto"] or "")
    return {"oposicion_id": r["oposicion_id"], "puesto": r["puesto"], "puesto_normalizado": r["puesto_normalizado"], "plazas": r["num_plazas"], "administracion": r["administracion"], "ambito": r["ambito"], "centro": r["puesto"] if "escuela" in k else None, "especialidad": "Educación Infantil" if "educacion infantil" in k else None, "categoria": cat, "profesion_centro": _profesion_centro(r["puesto"]), "escala": r["escala"], "subescala": r["subescala"], "clase": r["clase"], "grupo_subgrupo": next((x for x in ("A1", "A2", "B", "C1", "C2") if x in (r["puesto"] or "")), None), "titulacion": "Superior" if "superior" in k else "Especialista" if "especialista" in k else None, "relacion_laboral": "laboral" if "laboral" in k else None, "funcionario": "funcionario" in k, "seguridad": "EXCLUIDA" if protegido or cat in {"DIRECCION_COORDINACION", "CENTRO_SIN_CATEGORIA_PROFESIONAL", "AUXILIAR_ESCUELA_INFANTIL", "MONITOR_CUIDADOR"} else "DUDOSA", "canon_candidato": None, "decision": "EXCLUIDA" if protegido else "SIN_REGLA", "motivo": "No se equipara Escuela Infantil con Educación Infantil ni se fusionan categorías."}


def _fp(ids):
    return hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode()).hexdigest()


def ejecutar(ruta_bd="datos/boe.db", salida=SALIDA):
    con = sqlite3.connect(ruta_bd); con.row_factory = sqlite3.Row
    try:
        todas = list(con.execute("SELECT * FROM oposiciones ORDER BY oposicion_id"))
        # A: predicado SQL amplio; B: recorrido independiente en Python.
        a = list(con.execute("SELECT * FROM oposiciones WHERE (lower(coalesce(puesto,'')) LIKE '%infantil%' OR lower(coalesce(puesto_normalizado,'')) LIKE '%infantil%') ORDER BY oposicion_id"))
        b = [r for r in todas if _incluye(r)]
        ids_a = [r["oposicion_id"] for r in a]; ids_b = [r["oposicion_id"] for r in b]
        fichas = [_ficha(r) for r in a]
        grupos = defaultdict(list)
        for f in fichas: grupos[f["puesto"]].append(f)
        # El universo no genera reglas: todas las posibles equivalencias entre Escuela/Educación son no demostrables.
        informe = {
            "modo": "read-only", "universo": {"filas": len(a), "plazas": sum(float(r["num_plazas"] or 0) for r in a), "denominaciones": len(grupos), "ids": ids_a, "fingerprint": _fp(ids_a)},
            "reconstruccion_B": {"filas": len(b), "plazas": sum(float(r["num_plazas"] or 0) for r in b), "ids": ids_b, "fingerprint": _fp(ids_b)},
            "reconciliacion": {"iguales": ids_a == ids_b, "A_menos_B": sorted(set(ids_a)-set(ids_b)), "B_menos_A": sorted(set(ids_b)-set(ids_a)), "diferencia_simetrica": sorted(set(ids_a)^set(ids_b)), "duplicados_A": len(ids_a)-len(set(ids_a)), "duplicados_B": len(ids_b)-len(set(ids_b))},
            "clasificacion": dict(Counter(_clasifica(r["puesto"]) for r in a)),
            "profesion_frente_centro": dict(Counter(_profesion_centro(r["puesto"]) for r in a)),
            "registros": fichas,
            "variantes": [{"texto": t, "ids": [x["oposicion_id"] for x in g], "filas": len(g), "plazas": sum(float(x["plazas"] or 0) for x in g), "administraciones": sorted({x["administracion"] for x in g}), "canon_actual": sorted({x["puesto_normalizado"] for x in g}), "homogeneidad": len({x["categoria"] for x in g}) == 1} for t, g in sorted(grupos.items(), key=lambda z: (-len(z[1]), z[0] or ""))],
            "taxonomia": {"canones": {c: con.execute("SELECT COUNT(*) FROM oposiciones WHERE puesto_normalizado=?", (c,)).fetchone()[0] for c in ("Maestro de Educación Infantil", "Educador Infantil", "Técnico de Educación Infantil", "Técnico Superior de Educación Infantil", "Técnico Especialista en Educación Infantil")}, "protecciones": {"paso7": 65, "paso8": 12, "paso9": 17}},
            "equivalencias": {"tecnico_escuela_vs_educacion": "NO_DEMOSTRABLE", "auxiliar_escuela_vs_educacion": "NO_DEMOSTRABLE", "auxiliar_vs_tecnico": "NO_EQUIVALENTES", "tecnico_educador_vs_educador": "NO_EQUIVALENTES"},
            "conjunto_seguro": {"reglas": [], "ids": [], "filas": 0, "plazas": 0, "fingerprint": _fp([]), "justificacion": "No hay equivalencias seguras; Escuela Infantil puede ser centro y las categorías/niveles no se fusionan."},
            "auditoria_inversa": {"ids_previstos": [], "ids_capturados": [], "ids_extra": [], "ids_ausentes": [], "falsos_positivos": 0, "colisiones": 0, "capturas_paso7": 0, "capturas_paso8": 0, "capturas_paso9": 0},
        }
    finally: con.close()
    salida = Path(salida); salida.parent.mkdir(parents=True, exist_ok=True); salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"); return informe


if __name__ == "__main__":
    print(json.dumps(ejecutar(), ensure_ascii=False, indent=2))
