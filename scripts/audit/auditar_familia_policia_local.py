"""Auditoría read-only y dry-run aislado de la familia Policía Local.

No forma parte del normalizador productivo: sus propuestas se guardan sólo en
un informe para revisión humana antes de aprobar reglas de producción.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import time

from normalizacion_puestos import _clave, _preparar_texto, clasificar_policia_local


VERSION = "fase7-paso1-policia-local-v1"
def es_candidato_policia(texto: str | None) -> bool:
    """Delimita el universo amplio de la auditoría, no una regla productiva."""
    clave = _clave(_preparar_texto(texto) or "")
    return "polic" in clave or "guardia urbana" in clave


def proponer_normalizacion_experimental(puesto, contextos=()):
    """Clasifica una denominación sin modificar el normalizador productivo.

    ``contextos`` contiene pares ``(ambito, tipo_entidad)`` y sólo se usa para
    el literal aislado ``Policía``: evita asumir que cualquier policía pertenece
    al cuerpo local.
    """
    clase, canon, categoria, motivo = clasificar_policia_local(puesto)
    if clase == "SEGURA":
        return "SEGURA_TEXTUAL", canon, categoria, motivo
    # La auditoría registra este hallazgo, pero no lo entrega al motor:
    # normalizar_puesto() deliberadamente sólo recibe texto.
    if clase == "DUDOSA" and _clave(_preparar_texto(puesto) or "") == "policia":
        if set(contextos) and set(contextos) <= {("LOCAL", "MUNICIPAL")}:
            return "SEGURA_CONTEXTUAL", "Policía Local", "Policía Local", "requiere contexto local/municipal, no automatizable por texto"
    return clase or "EXCLUIDA", canon, categoria, motivo or "fuera del universo de Policía Local"


def _estado_sqlite(ruta: Path):
    stat = ruta.stat()
    with sqlite3.connect(f"file:{ruta}?mode=ro", uri=True) as con:
        metadata = dict(con.execute("SELECT clave, valor FROM metadata WHERE clave IN ('schema_version', 'data_version')"))
        schema = int(metadata["schema_version"])
        data = int(metadata["data_version"])
        oposiciones, plazas = con.execute("SELECT COUNT(*), COALESCE(SUM(num_plazas), 0) FROM oposiciones").fetchone()
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
    return {
        "sha256": hashlib.sha256(ruta.read_bytes()).hexdigest(), "tamano": stat.st_size,
        "mtime_ns": stat.st_mtime_ns, "schema_version": schema, "data_version": data,
        "oposiciones": oposiciones, "plazas": plazas, "integrity_check": integrity,
        "foreign_key_check": fk, "wal_existe": ruta.with_name(ruta.name + "-wal").exists(),
        "shm_existe": ruta.with_name(ruta.name + "-shm").exists(),
    }


def _git(orden):
    return subprocess.run(orden, text=True, capture_output=True, check=False).stdout.strip()


def auditar(ruta_bd="datos/boe.db", *, limite_ejemplos=5):
    """Ejecuta clasificación y dry-run en una conexión SQLite de sólo lectura."""
    inicio = time.perf_counter(); ruta = Path(ruta_bd).resolve(); estado_inicial = _estado_sqlite(ruta)
    with sqlite3.connect(f"file:{ruta}?mode=ro", uri=True) as con:
        con.row_factory = sqlite3.Row
        filas = con.execute(
            "SELECT oposicion_id, puesto, puesto_normalizado, ambito, tipo_entidad "
            "FROM oposiciones"
        ).fetchall()
    grupos = defaultdict(list)
    for fila in filas:
        if es_candidato_policia(fila["puesto"]):
            grupos[fila["puesto"]].append(dict(fila))

    variantes = []; clases = Counter(); categorias = Counter(); cambios = Counter(); cambios_dudosos = Counter(); ejemplos = defaultdict(list)
    for puesto, entradas in sorted(grupos.items(), key=lambda item: (-len(item[1]), item[0])):
        contextos = {(fila["ambito"], fila["tipo_entidad"]) for fila in entradas}
        clase, propuesto, categoria, motivo = proponer_normalizacion_experimental(puesto, contextos)
        actuales = Counter(fila["puesto_normalizado"] for fila in entradas)
        cambiaria = sum(n for actual, n in actuales.items() if propuesto is not None and actual != propuesto)
        registro = {
            "puesto": puesto, "puesto_normalizado_actual": dict(actuales), "registros": len(entradas),
            "contextos": [{"ambito": a, "tipo_entidad": t, "registros": sum(1 for f in entradas if (f["ambito"], f["tipo_entidad"]) == (a, t))} for a, t in sorted(contextos, key=str)],
            "clasificacion": clase, "normalizacion_propuesta": propuesto, "categoria_detectada": categoria,
            "motivo": motivo, "patron_candidato": "experimental, sólo auditoría", "filas_que_cambiarian": cambiaria,
        }
        variantes.append(registro); clases[clase] += len(entradas); categorias[categoria or "Sin categoría"] += len(entradas)
        if cambiaria:
            (cambios if clase == "SEGURA_TEXTUAL" else cambios_dudosos)[categoria or "Sin categoría"] += cambiaria
        if len(ejemplos[clase]) < limite_ejemplos:
            ejemplos[clase].append({"oposicion_id": entradas[0]["oposicion_id"], **registro})

    def resumen_patron(patron):
        seleccion = [v for v in variantes if re.search(patron, _clave(v["puesto"]))]
        return {"denominaciones": len(seleccion), "filas": sum(v["registros"] for v in seleccion), "ejemplos": [v["puesto"] for v in seleccion[:10]]}

    sufijos = Counter()
    for variante in variantes:
        clave = _clave(variante["puesto"])
        if variante["clasificacion"] != "SEGURA_TEXTUAL":
            continue
        for etiqueta, patron in {
            "vacante/plaza": r"\b(?:vacante|plaza|plazas)\b", "plantilla": r"\bplantilla\b",
            "funcionario": r"\bfuncionari", "ayuntamiento": r"\bayuntamiento\b",
            "escala/administración": r"\b(?:escala|administracion)\b", "provisión/convocatoria": r"\b(?:provision|convocatoria|proceso selectivo)\b",
            "turno/estabilización": r"\b(?:turno|estabilizacion)\b", "unidad/destino": r"\b(?:unidad|destino|departamento)\b",
        }.items():
            if re.search(patron, clave):
                sufijos[etiqueta] += variante["registros"]
    policia_aislada = [v for v in variantes if _clave(v["puesto"]) == "policia"]

    # Idempotencia de la propuesta: sólo se comprueba donde existe un canon.
    fallos_idempotencia = []
    for variante in variantes:
        propuesto = variante["normalizacion_propuesta"]
        if propuesto is None:
            continue
        segunda = proponer_normalizacion_experimental(propuesto, {("LOCAL", "MUNICIPAL")})[1]
        if segunda != propuesto:
            fallos_idempotencia.append({"puesto": variante["puesto"], "propuesto": propuesto, "segunda_pasada": segunda})
    estado_final = _estado_sqlite(ruta)
    return {
        "version": VERSION, "generado_utc": datetime.now(timezone.utc).isoformat(), "base_datos": str(ruta),
        "git": {"rama": _git(["git", "branch", "--show-current"]), "head": _git(["git", "rev-parse", "HEAD"]), "origin_main": _git(["git", "rev-parse", "origin/main"]), "ultimo_tag": _git(["git", "describe", "--tags", "--abbrev=0"]), "status": _git(["git", "status", "--short"])},
        "sqlite_inicial": estado_inicial, "sqlite_final": estado_final,
        "implementacion_actual_auditada": {
            "preprocesado": "_preparar_texto() y _clave(): NFKC/NFKD, espacios y tildes tolerantes",
            "regla_actual": "Sólo reconoce Policía Local y Agente de Policía Local de forma exacta; excluye inspector, subinspector, oficial, jefe, comisario, intendente, técnico y coordinador.",
            "limitacion": "No reconoce Policía Municipal, Policía aislada, Cabo, Sargento, Suboficial ni sufijos descriptivos; las categorías específicas quedan sin canon.",
            "idempotencia_productiva": "normalizar_puesto aplica punto fijo; no se modifica en esta auditoría.",
        },
        "criterios": {"universo": "puesto contiene polic- o Guardia Urbana", "produccion": "sin cambios", "clasificador_compartido": "normalizacion_puestos.clasificar_policia_local"},
        "universo": {"filas_examinadas": len(filas), "filas_relacionadas": sum(len(v) for v in grupos.values()), "denominaciones_distintas": len(grupos)},
        "variantes": variantes, "clasificacion_filas": dict(clases), "categorias_filas": dict(categorias),
        "familias_de_variantes": {
            "policia_local": resumen_patron(r"\bpolicia(?:s)? local(?:es)?\b"),
            "policia_municipal": resumen_patron(r"\bpolicia(?:s)? municipal(?:es)?\b"),
            "agente": resumen_patron(r"\bagente(?:s)?\b"), "oficial": resumen_patron(r"\boficial(?:/a)?\b"),
            "cabo": resumen_patron(r"\bcabo\b"), "sargento": resumen_patron(r"\bsargento\b"),
            "subinspector": resumen_patron(r"\bsubinspector"), "inspector": resumen_patron(r"\binspector"),
            "intendente": resumen_patron(r"\bintendente"), "policia_aislada": policia_aislada,
        },
        "sufijos_descriptivos_en_casos_seguros": dict(sufijos),
        "particulas_detectadas": {"de": sum(1 for v in variantes if " de " in f" {_clave(v['puesto'])} "), "de_la": sum(1 for v in variantes if " de la " in f" {_clave(v['puesto'])} "), "del": sum(1 for v in variantes if " del " in f" {_clave(v['puesto'])} ")},
        "dry_run": {"filas_que_cambiarian_seguras_textuales": sum(cambios.values()), "por_categoria_segura_textual": dict(cambios), "filas_seguras_contextuales": clases["SEGURA_CONTEXTUAL"], "filas_con_propuesta_no_textual": sum(cambios_dudosos.values()), "por_categoria_no_textual": dict(cambios_dudosos), "ejemplos": dict(ejemplos), "no_clasificadas": clases["DUDOSA"]},
        "idempotencia": {"correcta": not fallos_idempotencia, "fallos": fallos_idempotencia},
        "precedencia_propuesta": ["exclusiones semánticas", "categorías específicas", "Policía Local básica"],
        "regresiones_potenciales": "Las exclusiones y los casos DUDOSA quedan fuera de cualquier futura regla automática.",
        "rendimiento_segundos": round(time.perf_counter() - inicio, 3),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bd", default="datos/boe.db")
    parser.add_argument("--salida", default="informes/normalizacion_puestos/fase7_policia_local_auditoria.json")
    args = parser.parse_args(argv)
    informe = auditar(args.bd); salida = Path(args.salida); salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"universo": informe["universo"], "clasificacion_filas": informe["clasificacion_filas"], "dry_run": informe["dry_run"], "idempotencia": informe["idempotencia"], "salida": str(salida)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
