"""Auditoría read-only del universo docente pendiente tras 9D y 9H-6."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "datos" / "boe.db"
INFORME_9H6 = ROOT / "informes" / "normalizacion_puestos" / "fase7_docencia_musical_paso9h6_aplicacion.json"
OUT = ROOT / "informes" / "normalizacion_puestos" / "fase7_universo_docente_pendiente_paso9i.json"

PATRON_CANDIDATO = re.compile(
    r"\b(docente|profesor(?:a|es|as)?|maestr(?:o|a|os|as)|catedr[áa]tic(?:o|a|os|as)|"
    r"titular de universidad|enseñanza|educación|escuela|instituto|universidad|"
    r"conservatorio|m[uú]sica|musical|piano|guitarra|viol[ií]n|viola|violonchelo|"
    r"contrabajo|flauta|clarinete|oboe|fagot|saxof[oó]n|trompeta|tromb[oó]n|"
    r"percusi[oó]n|danza|baile|dibujo|pintura|artes?|diseño|teatro|idiomas|"
    r"formaci[oó]n profesional|secundaria)\b",
    re.IGNORECASE,
)
PATRON_DOCENTE = re.compile(r"\b(docente|profesor(?:a|es|as)?|maestr(?:o|a|os|as)|catedr[áa]tic(?:o|a|os|as))\b", re.I)
PATRON_MUSICA = re.compile(
    r"m[uú]sica|musical|conservatorio|banda|piano|guitarra|viol[ií]n|viola|"
    r"violonchelo|contrabajo|flauta|clarinete|oboe|fagot|saxof[oó]n|trompeta|"
    r"tromb[oó]n|trompa|tuba|percusi[oó]n|bater[ií]a|acorde[oó]n|arpa|canto|solfeo",
    re.I,
)
PATRON_ARTISTICA = re.compile(r"danza|baile|dibujo|pintura|artes? pl[aá]sticas|diseño|teatro|artes esc[eé]nicas", re.I)
PATRON_EXCLUIDA = re.compile(
    r"maestro(?:s)? de obras|maestro industrial|maestro jardinero|maestro electricista|"
    r"\bmonitor(?:a|es|as)?\b|\bt[eé]cnico\b|\bauxiliar\b|\banimador(?:a|es|as)?\b|"
    r"\bm[uú]sico(?:s)?\b|\binstrumentista(?:s)?\b|\bdirector(?:a|es)?\b|"
    r"restaurador(?:a|es)?|conservador(?:a|es)?|arquitect(?:o|a|os|as)|"
    r"delineante|administrativ(?:o|a|os|as)|mantenimiento",
    re.I,
)
CANONES_9D = {
    "Maestros", "Profesores de Enseñanza Secundaria",
    "Profesores Técnicos de Formación Profesional",
    "Profesores de Escuelas Oficiales de Idiomas",
    "Catedráticos de Universidad", "Profesores Titulares de Universidad",
}


def _plazas(valor) -> int:
    try:
        return int(valor or 0)
    except (TypeError, ValueError):
        return 0


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def estado_sqlite(path: Path = DB) -> dict:
    with sqlite3.connect(path) as con:
        return {
            "sha256": _sha256(path), "tamano": path.stat().st_size,
            "mtime_ns": path.stat().st_mtime_ns,
            "versiones": dict(con.execute(
                "SELECT clave, valor FROM metadata WHERE clave IN ('schema_version', 'data_version')"
            )),
            "oposiciones": con.execute("SELECT COUNT(*) FROM oposiciones").fetchone()[0],
            "plazas": con.execute("SELECT COALESCE(SUM(num_plazas), 0) FROM oposiciones").fetchone()[0],
            "integrity_check": [x[0] for x in con.execute("PRAGMA integrity_check")],
            "foreign_key_check": [tuple(x) for x in con.execute("PRAGMA foreign_key_check")],
            "wal_existe": path.with_name(path.name + "-wal").exists(),
            "shm_existe": path.with_name(path.name + "-shm").exists(),
        }


def familia_normalizada(canon: str | None) -> str | None:
    if canon in CANONES_9D:
        return {
            "Maestros": "Maestros", "Profesores de Enseñanza Secundaria": "Enseñanza Secundaria",
            "Profesores Técnicos de Formación Profesional": "Formación Profesional",
            "Profesores de Escuelas Oficiales de Idiomas": "Escuelas Oficiales de Idiomas",
            "Catedráticos de Universidad": "Universidad funcionarial",
            "Profesores Titulares de Universidad": "Universidad funcionarial",
        }[canon]
    if (canon or "").startswith("Profesor de Conservatorio") or (canon or "").startswith("Profesor de Escuela de Música") or (canon or "").startswith("Profesor de Música"):
        return "Música normalizada"
    return None


def clasificar_fila(fila: dict, ids_9h6: set[int] | None = None) -> tuple[str, str, str | None, str]:
    """Clasifica un candidato de forma excluyente; no propone normalizaciones."""
    texto = fila.get("puesto") or ""
    canon = fila.get("puesto_normalizado")
    familia = familia_normalizada(canon)
    if familia:
        return "YA_NORMALIZADA", familia, None, "canon persistido reconocido"
    # Estos patrones describen una ocupación no docente aunque contengan el
    # lexema ``maestro`` (por ejemplo, Maestro de obras).
    if PATRON_EXCLUIDA.search(texto):
        return "FALSO_POSITIVO", "Falsos positivos / no docentes", "EXCLUIDA", "función no docente explícita"
    if re.search(r"universidad|universitario", texto, re.I):
        if re.search(r"contratad[oa] doctor|ayudante doctor|asociad[oa]|sustitut[oa]|laboral", texto, re.I):
            return "PENDIENTE_REAL", "Universidad laboral/contractual", "DUDOSA", "figura contractual; no es cuerpo funcionarial"
        if re.search(r"catedr[áa]tic|titular de universidad", texto, re.I):
            return "PENDIENTE_REAL", "Universidad funcionarial pendiente", "SEGURA_TEXTUAL", "cuerpo funcionarial explícito no reconocido"
        if PATRON_DOCENTE.search(texto):
            return "PENDIENTE_REAL", "Universidad indeterminada", "PROBABLE", "docencia universitaria sin figura inequívoca"
        return "FALSO_POSITIVO", "Falsos positivos / no docentes", "EXCLUIDA", "universidad como entidad sin función docente"
    if PATRON_MUSICA.search(texto):
        if PATRON_DOCENTE.search(texto):
            return "PENDIENTE_REAL", "Música pendiente tras 9H-6", "DUDOSA", "evidencia docente sin canon seguro aprobado"
        return "FALSO_POSITIVO", "Música no docente", "EXCLUIDA", "referencia musical sin función docente"
    if PATRON_ARTISTICA.search(texto):
        if PATRON_DOCENTE.search(texto):
            return "PENDIENTE_REAL", "Docencia artística no musical", "SEGURA_CON_ESPECIALIDAD", "especialidad artística explícita"
        return "FALSO_POSITIVO", "Falsos positivos / no docentes", "EXCLUIDA", "disciplina artística sin función docente"
    if re.search(r"formaci[oó]n profesional|profesor(?:a|es|as)? t[eé]cnico", texto, re.I):
        return "PENDIENTE_REAL", "Formación Profesional", "PROBABLE", "denominación docente pendiente"
    if re.search(r"enseñanza secundaria|educación secundaria", texto, re.I):
        return "PENDIENTE_REAL", "Enseñanza Secundaria", "PROBABLE", "denominación docente pendiente"
    if re.search(r"escuela(?:s)? oficial(?:es)? de idiomas|idiomas", texto, re.I) and PATRON_DOCENTE.search(texto):
        return "PENDIENTE_REAL", "Escuelas Oficiales de Idiomas", "PROBABLE", "denominación docente pendiente"
    if re.search(r"\bmaestr", texto, re.I):
        return "PENDIENTE_REAL", "Maestros", "PROBABLE", "denominación docente pendiente"
    if PATRON_DOCENTE.search(texto):
        if (fila.get("ambito") or "").upper() == "LOCAL":
            return "PENDIENTE_REAL", "Docencia local específica", "DUDOSA", "función docente local sin cuerpo inferible"
        return "DUDOSA", "Profesor/docente genérico", "DUDOSA", "sin cuerpo, centro o especialidad suficiente"
    return "FALSO_POSITIVO", "Falsos positivos / no docentes", "EXCLUIDA", "coincidencia institucional o léxica no docente"


def _registro(fila: sqlite3.Row, ids_9h6: set[int]) -> dict:
    raw = dict(fila)
    estado, familia, seguridad, motivo = clasificar_fila(raw, ids_9h6)
    return {
        "id": raw["oposicion_id"], "puesto": raw["puesto"],
        "puesto_normalizado": raw["puesto_normalizado"], "plazas": _plazas(raw["num_plazas"]),
        "fecha": raw.get("fecha_boe"), "administracion": raw.get("administracion"),
        "ambito": raw.get("ambito"), "tipo_entidad": raw.get("tipo_entidad"),
        "provincia": raw.get("provincia"), "comunidad_autonoma": raw.get("comunidad_autonoma"),
        "municipio": raw.get("municipio"), "estado": estado, "familia": familia,
        "seguridad": seguridad, "motivo": motivo,
    }


def _resumen(grupo: list[dict]) -> dict:
    puestos = Counter(x["puesto"] for x in grupo)
    admins = Counter(x["administracion"] or "(sin administración)" for x in grupo)
    ambitos = Counter(x["ambito"] or "(sin ámbito)" for x in grupo)
    territorios = Counter(x["comunidad_autonoma"] or "(sin comunidad)" for x in grupo)
    return {
        "filas": len(grupo), "plazas": sum(x["plazas"] for x in grupo),
        "denominaciones_distintas": len(puestos),
        "principales_denominaciones": [{"puesto": k, "filas": v} for k, v in puestos.most_common(10)],
        "principales_administraciones": [{"administracion": k, "filas": v} for k, v in admins.most_common(10)],
        "ambitos": dict(ambitos), "comunidades": dict(territorios),
    }


def auditar(ruta_bd: Path = DB) -> dict:
    estado_inicial = estado_sqlite(ruta_bd)
    ids_9h6 = set()
    if INFORME_9H6.exists():
        aplicado = json.loads(INFORME_9H6.read_text(encoding="utf-8"))
        ids_9h6 = {int(ident) for ident in aplicado.get("campos_diferentes", {})}
    with sqlite3.connect(ruta_bd) as con:
        con.row_factory = sqlite3.Row
        filas = con.execute("SELECT * FROM oposiciones ORDER BY oposicion_id").fetchall()
    candidatos = [_registro(fila, ids_9h6) for fila in filas if PATRON_CANDIDATO.search(fila["puesto"] or "")]
    por_estado = defaultdict(list)
    por_familia = defaultdict(list)
    for candidato in candidatos:
        por_estado[candidato["estado"]].append(candidato)
        por_familia[candidato["familia"]].append(candidato)
    pendientes = por_estado["PENDIENTE_REAL"]
    musica = [x for x in candidatos if PATRON_MUSICA.search(x["puesto"] or "")]
    universidad = [x for x in candidatos if re.search(r"universidad|universitario", x["puesto"] or "", re.I)]
    artistica = [x for x in candidatos if PATRON_ARTISTICA.search(x["puesto"] or "", re.I)]
    local = [x for x in candidatos if (x["ambito"] or "").upper() == "LOCAL" and x["estado"] == "PENDIENTE_REAL"]
    cruzadas_9h6 = [x for x in candidatos if x["id"] in ids_9h6]
    contradicciones = [x for x in cruzadas_9h6 if x["estado"] != "YA_NORMALIZADA"]
    nuevos_casos_post31 = [x for x in contradicciones if "fotocompos" in (x["puesto"] or "").casefold()]
    contradicciones_historicas = [x for x in contradicciones if x not in nuevos_casos_post31]
    seguridad = {clave: _resumen([x for x in pendientes if x["seguridad"] == clave]) for clave in (
        "SEGURA_TEXTUAL", "SEGURA_CONTEXTUAL", "SEGURA_CON_ESPECIALIDAD", "PROBABLE", "DUDOSA", "EXCLUIDA"
    )}
    prioridades = [
        {"prioridad": 1, "familia": "Docencia artística no musical", "seguridad": "SEGURA_CON_ESPECIALIDAD", "tipo_regla": "textual conservando especialidad", "recomendacion": "auditar por subfamilias antes de aplicar"},
        {"prioridad": 2, "familia": "Universidad funcionarial pendiente", "seguridad": "SEGURA_TEXTUAL", "tipo_regla": "cuerpo explícito", "recomendacion": "validar variantes formales"},
        {"prioridad": 3, "familia": "Universidad laboral/contractual", "seguridad": "DUDOSA", "tipo_regla": "canon laboral específico", "recomendacion": "no fusionar con cuerpos funcionariales"},
        {"prioridad": 4, "familia": "Música pendiente tras 9H-6", "seguridad": "DUDOSA", "tipo_regla": "contextual/especialidad", "recomendacion": "mantener exclusiones actuales"},
        {"prioridad": 5, "familia": "Docencia local específica", "seguridad": "DUDOSA", "tipo_regla": "contextual", "recomendacion": "no inferir cuerpos nacionales"},
    ]
    for prioridad in prioridades:
        datos = _resumen(por_familia[prioridad["familia"]])
        prioridad.update({"filas": datos["filas"], "plazas": datos["plazas"]})
    musica_por_estado = {estado: _resumen([x for x in musica if x["estado"] == estado]) for estado in por_estado}
    universidad_por_familia = {
        familia: _resumen([x for x in universidad if x["familia"] == familia])
        for familia in sorted({x["familia"] for x in universidad})
    }
    artistica_por_estado = {estado: _resumen([x for x in artistica if x["estado"] == estado]) for estado in por_estado}
    informe = {
        "estado_inicial": estado_inicial,
        "universo_candidato": _resumen(candidatos),
        "ya_normalizados": _resumen(por_estado["YA_NORMALIZADA"]),
        "pendiente_real": _resumen(pendientes),
        "dudoso": _resumen(por_estado["DUDOSA"]),
        "falsos_positivos": _resumen(por_estado["FALSO_POSITIVO"]),
        "familias": {familia: _resumen(grupo) for familia, grupo in sorted(por_familia.items())},
        "universidad": {"universo": _resumen(universidad), "familias": universidad_por_familia},
        "musica_pendiente": {"universo": _resumen(musica), "por_estado": musica_por_estado},
        "docencia_artistica": {"universo": _resumen(artistica), "por_estado": artistica_por_estado},
        "docencia_local": _resumen(local),
        "clasificacion_seguridad": seguridad,
        "cruce_paso9d": _resumen([x for x in candidatos if x["puesto_normalizado"] in CANONES_9D]),
        "cruce_paso9h6": {"filas_esperadas": 1363, "filas_detectadas": len(cruzadas_9h6), "contradicciones": contradicciones_historicas, "nuevos_casos_post31": nuevos_casos_post31},
        "contradicciones": contradicciones,
        "reconciliacion_filas": {"universo": len(candidatos), **{k: len(v) for k, v in por_estado.items()}, "suma_estados": sum(len(v) for v in por_estado.values())},
        "reconciliacion_plazas": {"universo": sum(x["plazas"] for x in candidatos), **{k: sum(x["plazas"] for x in v) for k, v in por_estado.items()}},
        "prioridades_siguientes": prioridades,
        "ejemplos": {estado: grupo[:10] for estado, grupo in por_estado.items()},
        "conclusiones": "Auditoría experimental: no se han aplicado reglas ni modificado SQLite.",
        "candidatos": candidatos,
    }
    informe["estado_final"] = estado_sqlite(ruta_bd)
    return informe


def main() -> None:
    informe = auditar()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "universo": informe["universo_candidato"]["filas"],
        "normalizados": informe["ya_normalizados"]["filas"],
        "pendientes": informe["pendiente_real"]["filas"],
        "dudosos": informe["dudoso"]["filas"],
        "falsos": informe["falsos_positivos"]["filas"],
        "salida": str(OUT),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
