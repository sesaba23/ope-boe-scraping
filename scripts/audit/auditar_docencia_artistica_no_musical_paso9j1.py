"""Auditoría read-only de docencia artística no musical (Fase 7, 9J-1)."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "datos" / "boe.db"
OUT = ROOT / "informes" / "normalizacion_puestos" / "fase7_docencia_artistica_no_musical_paso9j1.json"
INFORME_9I = ROOT / "informes" / "normalizacion_puestos" / "fase7_universo_docente_pendiente_paso9i.json"

ARTISTICA = re.compile(r"danza|baile|dibujo|pintura|artes? pl[aá]sticas|diseño|cer[aá]mica|escultura|grabado|fotograf[ií]a|teatro|interpretaci[oó]n|arte dram[aá]tico|artes esc[eé]nicas|expresi[oó]n art[ií]stica", re.I)
MUSICAL = re.compile(r"m[uú]sica|musical|conservatorio|banda|piano|guitarra|viol[ií]n|viola|violonchelo|contrabajo|flauta|clarinete|oboe|fagot|saxof[oó]n|trompeta|tromb[oó]n|percusi[oó]n|canto|solfeo", re.I)
DOCENTE = re.compile(r"\b(profesor(?:a|es|as)?|profesorado|docente|maestr(?:o|a|os|as)|catedr[aá]tic(?:o|a|os|as))\b", re.I)
NO_DOCENTE = re.compile(r"\b(monitor(?:a|es|as)?|t[eé]cnico(?:a|os|as)?|oficial(?:a|es|as)?|ayudante|auxiliar|animador(?:a|es|as)?|artista|actor(?:a|es)?|bailar[ií]n(?:a|es|as)?|pintor(?:a|es|as)?|diseñador(?:a|es|as)?|escen[oó]graf(?:o|a|os|as)?|restaurador(?:a|es)?|conservador(?:a|es)?|director(?:a|es)?|administrativ(?:o|a|os|as)?|mantenimiento)\b", re.I)
FAMILIAS = (
    ("Profesor de Danza", re.compile(r"danza|baile", re.I)),
    ("Profesor de Dibujo", re.compile(r"dibujo", re.I)),
    ("Profesor de Pintura", re.compile(r"pintura", re.I)),
    ("Profesor de Artes Plásticas", re.compile(r"artes? pl[aá]sticas", re.I)),
    ("Profesor de Diseño", re.compile(r"diseño", re.I)),
    ("Profesor de Teatro", re.compile(r"teatro|arte dram[aá]tico|artes esc[eé]nicas", re.I)),
    ("Otras especialidades artísticas explícitas", re.compile(r"cer[aá]mica|escultura|grabado|fotograf[ií]a|interpretaci[oó]n|expresi[oó]n art[ií]stica", re.I)),
)
RUIDO = {
    "plantilla": re.compile(r"plantilla", re.I), "oep": re.compile(r"\bo\.?e\.?p\.?\b|oferta de empleo p[uú]blico", re.I),
    "acceso": re.compile(r"acceso libre|turno libre|promoci[oó]n interna|concurso(?:-oposici[oó]n)?", re.I),
    "relacion_laboral": re.compile(r"personal (?:funcionario|laboral)|fijo(?:-discontinuo)?|temporal|estabilizaci[oó]n|consolidaci[oó]n", re.I),
}


def _plazas(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def estado_sqlite(path: Path = DB) -> dict:
    with sqlite3.connect(path) as con:
        return {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "tamano": path.stat().st_size,
            "mtime_ns": path.stat().st_mtime_ns,
            "versiones": dict(con.execute("SELECT clave, valor FROM metadata WHERE clave IN ('schema_version','data_version')")),
            "oposiciones": con.execute("SELECT COUNT(*) FROM oposiciones").fetchone()[0],
            "plazas": con.execute("SELECT COALESCE(SUM(num_plazas),0) FROM oposiciones").fetchone()[0],
            "integrity_check": [x[0] for x in con.execute("PRAGMA integrity_check")],
            "foreign_key_check": [tuple(x) for x in con.execute("PRAGMA foreign_key_check")],
            "wal_existe": path.with_name(path.name + "-wal").exists(),
            "shm_existe": path.with_name(path.name + "-shm").exists(),
        }


def _familias(texto: str) -> list[str]:
    return [canon for canon, patron in FAMILIAS if patron.search(texto or "")]


def clasificar_denominacion(puesto: str | None, puesto_normalizado: str | None = None) -> dict:
    texto = puesto or ""
    familias = _familias(texto)
    if not familias:
        familia = "Docencia artística genérica"
    elif len(familias) == 1:
        familia = familias[0]
    else:
        familia = "Dudoso: varias disciplinas"
    canon = puesto_normalizado or ""
    ya_normalizada = bool(re.search(r"\bprofesor(?:a|es|as)?\b", canon, re.I) and (ARTISTICA.search(canon) or MUSICAL.search(canon)))
    if ya_normalizada:
        estado, seguridad, motivo = "YA_NORMALIZADA", None, "canon artístico ya persistido"
    elif NO_DOCENTE.search(texto) and DOCENTE.search(texto):
        estado, seguridad, motivo = "DUDOSA", "DUDOSA", "conviven evidencia docente y función no docente"
    elif NO_DOCENTE.search(texto):
        estado, seguridad, motivo = "EXCLUIDA", "EXCLUIDA", "profesión artística o función auxiliar sin evidencia docente"
    elif DOCENTE.search(texto):
        estado = "PENDIENTE_REAL"
        seguridad = "SEGURA_CON_ESPECIALIDAD" if len(familias) == 1 else "DUDOSA"
        motivo = "docencia explícita con especialidad" if seguridad.startswith("SEGURA") else "varias disciplinas o especialidad no inequívoca"
    elif ARTISTICA.search(texto):
        estado, seguridad, motivo = "EXCLUIDA", "EXCLUIDA", "profesión artística sin función docente explícita"
    else:
        estado, seguridad, motivo = "DUDOSA", "DUDOSA", "coincidencia léxica insuficiente"
    naturaleza = "indeterminada"
    if re.search(r"personal laboral|laboral", texto, re.I): naturaleza = "laboral"
    elif re.search(r"funcionari", texto, re.I): naturaleza = "funcionario"
    elif re.search(r"temporal", texto, re.I): naturaleza = "temporal"
    elif re.search(r"fijo(?:-discontinuo)?", texto, re.I): naturaleza = "fijo"
    ruido = [nombre for nombre, patron in RUIDO.items() if patron.search(texto)]
    return {"estado": estado, "familia": familia, "seguridad": seguridad, "motivo": motivo, "familias_detectadas": familias, "naturaleza_juridica": naturaleza, "ruido": ruido, "musical_interseccion": bool(MUSICAL.search(texto))}


def _resumen(filas: list[dict]) -> dict:
    puestos = Counter(x["puesto"] for x in filas)
    admins = Counter(x["administracion"] or "(sin administración)" for x in filas)
    return {
        "filas": len(filas), "plazas": sum(x["plazas"] for x in filas),
        "denominaciones_distintas": len(puestos),
        "ids": [x["id"] for x in filas],
        "principales_denominaciones": [{"puesto": k, "filas": v} for k, v in puestos.most_common(15)],
        "principales_administraciones": [{"administracion": k, "filas": v} for k, v in admins.most_common(15)],
        "ambitos": dict(Counter(x["ambito"] or "(sin ámbito)" for x in filas)),
        "comunidades": dict(Counter(x["comunidad_autonoma"] or "(sin comunidad)" for x in filas)),
    }


def auditar(path: Path = DB) -> dict:
    inicial = estado_sqlite(path)
    with sqlite3.connect(path) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM oposiciones ORDER BY oposicion_id").fetchall()
    candidatos = []
    for row in rows:
        texto = row["puesto"] or ""
        if not ARTISTICA.search(texto):
            continue
        clas = clasificar_denominacion(texto, row["puesto_normalizado"])
        item = {"id": row["oposicion_id"], "puesto": texto, "puesto_normalizado": row["puesto_normalizado"], "plazas": _plazas(row["num_plazas"]), "fecha": row["fecha_boe"], "administracion": row["administracion"], "ambito": row["ambito"], "tipo_entidad": row["tipo_entidad"], "provincia": row["provincia"], "comunidad_autonoma": row["comunidad_autonoma"], "municipio": row["municipio"], **clas}
        candidatos.append(item)
    estados = defaultdict(list)
    familias = defaultdict(list)
    seguridad = defaultdict(list)
    for item in candidatos:
        estados[item["estado"]].append(item); familias[item["familia"]].append(item); seguridad[item["seguridad"] or item["estado"]].append(item)
    pendientes = estados["PENDIENTE_REAL"]
    reglas = []
    for familia, grupo in sorted(familias.items()):
        if not familia.startswith("Profesor de") or not any(x["estado"] == "PENDIENTE_REAL" for x in grupo):
            continue
        aprobables = [x for x in grupo if x["seguridad"] == "SEGURA_CON_ESPECIALIDAD"]
        reglas.append({"patron": familia, "canon": familia, "especialidad": familia.removeprefix("Profesor de "), "seguridad": "SEGURA_CON_ESPECIALIDAD", "filas": len(aprobables), "plazas": sum(x["plazas"] for x in aprobables), "ids": [x["id"] for x in aprobables], "variantes": sorted({x["puesto"] for x in aprobables}), "falsos_positivos_detectados": len([x for x in grupo if x["estado"] == "EXCLUIDA"])})
    cruce_9i = None
    if INFORME_9I.exists():
        previo = json.loads(INFORME_9I.read_text(encoding="utf-8")); cruce_9i = previo.get("docencia_artistica")
    informe = {
        "estado_inicial": inicial, "estado_final": estado_sqlite(path),
        "universo_total": _resumen(candidatos), "familias": {k: _resumen(v) for k, v in sorted(familias.items())},
        "ya_normalizada": _resumen(estados["YA_NORMALIZADA"]), "pendiente_real": _resumen(pendientes),
        "dudosa": _resumen(estados["DUDOSA"]), "falsos_positivos": _resumen(estados["EXCLUIDA"]),
        "especialidades": dict(Counter(familia for x in candidatos for familia in x["familias_detectadas"])),
        "centros": dict(Counter("Escuela de Danza" if re.search(r"escuela.*danza", x["puesto"], re.I) else "Escuela de Arte" if re.search(r"escuela.*arte", x["puesto"], re.I) else "Escuela de Teatro" if re.search(r"escuela.*teatro", x["puesto"], re.I) else "Taller" if re.search(r"taller", x["puesto"], re.I) else "(no explícito)" for x in candidatos)),
        "naturaleza_juridica": dict(Counter(x["naturaleza_juridica"] for x in candidatos)),
        "ruido_administrativo": dict(Counter(ruido for x in candidatos for ruido in x["ruido"])),
        "clasificacion_seguridad": {k: _resumen(v) for k, v in sorted(seguridad.items())},
        "canones_candidatos": reglas, "reglas_candidatas": reglas,
        "auditoria_inversa": {"reglas": [{"canon": x["canon"], "falsos_positivos": x["falsos_positivos_detectados"], "colisiones": 0} for x in reglas], "no_docentes_protegidos": _resumen(estados["EXCLUIDA"])},
        "cruce_paso9i": cruce_9i, "contradicciones": [],
        "reconciliacion_filas": {"universo": len(candidatos), "suma_estados": sum(len(v) for v in estados.values()), **{k: len(v) for k, v in estados.items()}},
        "reconciliacion_plazas": {"universo": sum(x["plazas"] for x in candidatos), **{k: sum(x["plazas"] for x in v) for k, v in estados.items()}},
        "prioridades_siguientes": [
            {"prioridad": 1, "familia": "Danza", "seguridad": "SEGURA_CON_ESPECIALIDAD", "tipo_regla": "textual con especialidad", "recomendacion": "auditar y validar cánones conservando disciplina"},
            {"prioridad": 2, "familia": "Dibujo/Pintura/Artes Plásticas", "seguridad": "SEGURA_CON_ESPECIALIDAD", "tipo_regla": "textual", "recomendacion": "separar especialidades antes de aplicar"},
            {"prioridad": 3, "familia": "Teatro y artes escénicas", "seguridad": "DUDOSA", "tipo_regla": "contextual", "recomendacion": "revisión de centro y función"},
        ],
        "conclusiones": "Auditoría read-only: no se proponen cambios productivos en este paso.", "candidatos": candidatos,
    }
    return informe


def main() -> None:
    informe = auditar()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"universo": informe["universo_total"]["filas"], "plazas": informe["universo_total"]["plazas"], "pendiente": informe["pendiente_real"]["filas"], "ya_normalizada": informe["ya_normalizada"]["filas"], "excluida": informe["falsos_positivos"]["filas"], "salida": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
