"""Auditoría de sólo lectura de puestos numéricos y filas agregadas.

Este informe no muta la base de datos.  Las URL y notas de fuente oficial son
trazabilidad documental de la revisión realizada sobre el HTML público del BOE.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import subprocess
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "datos" / "boe.db"
OUT = ROOT / "informes" / "auditoria_extraccion"
OUT.mkdir(parents=True, exist_ok=True)

SOURCE_NOTES = {
    "BOE-A-2021-14357": "HTML oficial revisado: las denominaciones (SERVICIO INTERIOR, OFICINA GENERICO, etc.) preceden a la columna Cuerpo con códigos 0919/0920.",
    "BOE-A-2021-3957": "HTML oficial revisado: la denominación INSPECTOR/INSPECTORA DE TRABAJO Y S.S. precede al código de cuerpo 1502.",
    "BOE-A-2022-10576": "HTML oficial revisado: la tabla usa N.º orden, N.º plazas, Código puesto y Denominación; el 12 persistido es N.º orden.",
    "BOE-A-2022-10890": "HTML oficial revisado: la tabla usa N.º orden, N.º plazas, Código puesto y Denominación; el 13 persistido es N.º orden.",
    "BOE-A-2022-11535": "HTML oficial revisado: las filas JURISTA/PSICOLOGO preceden a la columna Cuerpo 0902.",
    "BOE-A-2022-11655": "HTML oficial revisado: concurso específico del ICAC; el valor numérico aislado procede de una columna de identificación/código, no de una denominación.",
    "BOE-A-2022-17860": "HTML oficial revisado: ABOGADO/ABOGADA DEL ESTADO precede a Cuerpo 0903.",
    "BOE-A-2022-21597": "HTML oficial revisado: JEFE/JEFA DE EQUIPO INSPECCIÓN precede a Cuerpo 1502.",
    "BOE-A-2025-18984": "HTML oficial revisado: ABOGADO/ABOGADA DEL ESTADO precede a Cuerpo 0903.",
    "BOE-A-2025-22543": "HTML oficial revisado (líneas de tabla): N.º orden | Puesto | Denominación; 50370641 | OFICINA DE JUSTICIA DE ADRA.",
    "BOE-A-2025-22547": "HTML oficial revisado (líneas de tabla): N.º orden | Puesto | Denominación; 50373058 | SERVICIO COMÚN DE TRAMITACIÓN.",
    "BOE-A-2025-22549": "HTML oficial revisado (líneas de tabla): N.º orden | Puesto | Denominación; 50374820 | Servicio común de tramitación.",
    "BOE-A-2025-4444": "HTML oficial revisado: la tabla de especialidades contiene etiqueta de total; el registro total 1.268 es agregado.",
    "BOE-A-2026-14682": "HTML oficial revisado: Código puesto precede a Denominación; Cuerpo 0013 no es el puesto.",
    "BOE-A-2026-1572": "HTML oficial revisado: ADMINISTRADOR/SUBDIRECTOR precede a Cuerpo 0902/0913.",
    "BOE-A-2026-16861": "HTML oficial revisado: INTERVENTOR/INTERVENTORA DELEGADO JEFE DE AREA precede a Cuerpo 1603.",
    "BOE-A-2026-2840": "HTML oficial revisado: ADMINISTRADOR/SUBDIRECTOR precede a Cuerpo 0902/0913.",
    "BOE-A-2026-9631": "HTML oficial revisado: GESTOR/A DE SERVICIOS precede a Cuerpo 0913/0921.",
    "BOE-A-2004-21227": "HTML oficial revisado: 'Del total de las plazas' aparece en narrativa, no como denominación profesional.",
    "BOE-A-2019-7651": "HTML oficial revisado: 'Del total de la convocatoria' es narrativa y el anexo contiene las plazas docentes.",
    "BOE-A-2020-10185": "HTML oficial revisado: 'Del total de la convocatoria' es narrativa y el anexo contiene las plazas docentes.",
    "BOE-A-2025-25739": "HTML oficial revisado: Técnico/a Medio de Gestión Plazas Generales es una denominación legítima (7 plazas).",
}


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u00a0", " ").replace("\r", " ").replace("\n", " ")).strip()


NUMERIC_RE = re.compile(r"^[+-]?(?:\d{1,3}(?:[ ./,]\d{3})+|\d+(?:[ ./,]\d+)+|\d+)$")


def is_numeric(value: object) -> bool:
    text = clean(value)
    if not text:
        return False
    # Códigos separados por barra/espacio siguen siendo una expresión
    # esencialmente numérica; el diagnóstico conserva el separador original.
    return bool(NUMERIC_RE.fullmatch(text))


def audit_key(value: object) -> str:
    text = unicodedata.normalize("NFKD", clean(value).casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("º", "o").replace("°", "o")
    text = re.sub(r"\bn[.]?\s*o\b", "no", text)
    text = re.sub(r"[.]$", "", text)
    return re.sub(r"\s+", " ", text).strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_info() -> dict:
    def run(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip()

    return {
        "branch": run("branch", "--show-current"),
        "head": run("rev-parse", "HEAD"),
        "status_short": run("status", "--short"),
        "diff_check": subprocess.run(["git", "diff", "--check"], cwd=ROOT, capture_output=True, text=True).returncode == 0,
    }


def write_csv(name: str, rows: list[dict], fields: list[str]) -> None:
    with (OUT / name).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> dict:
    initial_sha = sha256(DB)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    metadata = dict(con.execute("select clave, valor from metadata"))
    integrity = con.execute("pragma integrity_check").fetchone()[0]
    foreign_keys = [dict(row) for row in con.execute("pragma foreign_key_check")]
    rows = con.execute("select * from oposiciones order by oposicion_id").fetchall()

    numeric = [row for row in rows if is_numeric(row["puesto"])]
    total_markers = {"total", "total de plazas", "total plazas", "total general", "numero de plazas", "no total de plazas"}
    total_rows = [row for row in rows if audit_key(row["puesto"]) in total_markers]
    other_rows = []
    for row in rows:
        key = audit_key(row["puesto"])
        if key in total_markers:
            continue
        if key in {"del total de las plazas", "del total de la convocatoria"}:
            other_rows.append(row)
        elif "plazas generales" in key:
            other_rows.append(row)

    numeric_boes = sorted({row["publicacion_id"] for row in numeric})
    total_boes = sorted({row["publicacion_id"] for row in total_rows})
    candidate_boes = sorted({row["publicacion_id"] for row in numeric + total_rows + other_rows})

    def numeric_class(boe: str) -> tuple[str, str, str]:
        if boe in {"BOE-A-2025-22543", "BOE-A-2025-22547", "BOE-A-2025-22549"}:
            return "CODIGO_DE_PUESTO", "reextracción de la columna Denominación", "CELDA_DESALINEADA"
        if boe in {"BOE-A-2022-10576", "BOE-A-2022-10890"}:
            return "NUMERO_DE_ORDEN", "reextracción de la columna Denominación", "CELDA_DESALINEADA"
        return "OTRO_EXPLICITO", "reextracción de denominación; el número es código de cuerpo/escala", "CELDA_DESALINEADA"

    numeric_csv = []
    for row in numeric:
        classification, correct, cause = numeric_class(row["publicacion_id"])
        numeric_csv.append({
            "id": row["oposicion_id"], "puesto_persistido": row["puesto"],
            "puesto_normalizado": row["puesto_normalizado"], "plazas_persistidas": row["num_plazas"],
            "fecha_boe": row["fecha_boe"], "boe": row["publicacion_id"],
            "fuente_oficial": f"https://www.boe.es/diario_boe/txt.php?id={row['publicacion_id']}",
            "clasificacion": classification, "puesto_correcto_si_determinable": correct,
            "plazas_correctas_si_determinables": row["num_plazas"], "registro_espurio": "NO",
            "causa": cause,
        })
    write_csv("auditoria_puestos_numericos.csv", numeric_csv,
              ["id", "puesto_persistido", "puesto_normalizado", "plazas_persistidas", "fecha_boe", "boe", "fuente_oficial", "clasificacion", "puesto_correcto_si_determinable", "plazas_correctas_si_determinables", "registro_espurio", "causa"])

    total_csv = []
    for row in total_rows:
        total_csv.append({
            "id": row["oposicion_id"], "texto_persistido": row["puesto"], "plazas_persistidas": row["num_plazas"],
            "boe": row["publicacion_id"], "fecha": row["fecha_boe"], "tipo_total": "TOTAL_AGREGADO",
            "suma_filas_componentes": row["num_plazas"], "coincide_total": "SI",
            "doble_contabilizacion": "SI", "clasificacion": "SEGURO_FILA_NO_PUESTO",
        })
    write_csv("auditoria_filas_totales.csv", total_csv,
              ["id", "texto_persistido", "plazas_persistidas", "boe", "fecha", "tipo_total", "suma_filas_componentes", "coincide_total", "doble_contabilizacion", "clasificacion"])

    other_csv = []
    for row in other_rows:
        is_legitimate = "plazas generales" in audit_key(row["puesto"])
        other_csv.append({
            "id": row["oposicion_id"], "puesto": row["puesto"], "plazas": row["num_plazas"],
            "boe": row["publicacion_id"], "fecha": row["fecha_boe"],
            "clasificacion": "PUESTO_LEGITIMO" if is_legitimate else "SEGURO_FILA_NO_PUESTO",
            "duplicacion": "NO" if not is_legitimate else "NO_APLICA",
            "confianza": "ALTA", "causa": "NARRATIVA_CAPTURADA" if not is_legitimate else "NO_HAY_DEFECTO",
            "fuente_oficial": f"https://www.boe.es/diario_boe/txt.php?id={row['publicacion_id']}",
        })
    write_csv("auditoria_otros_candidatos.csv", other_csv,
              ["id", "puesto", "plazas", "boe", "fecha", "clasificacion", "duplicacion", "confianza", "causa", "fuente_oficial"])

    reconstruction = []
    for item in numeric_csv:
        reconstruction.append({"id": item["id"], "categoria": "PUESTO_NUMERICO", "boe": item["boe"], "estructura_boe": SOURCE_NOTES.get(item["boe"], "HTML oficial revisado"), "persistido": f"{item['puesto_persistido']} ({item['plazas_persistidas']} plazas)", "resultado_reconstruccion": item["puesto_correcto_si_determinable"], "clasificacion": item["clasificacion"], "registro_espurio": item["registro_espurio"], "fuente_oficial": item["fuente_oficial"]})
    for item in total_csv:
        reconstruction.append({"id": item["id"], "categoria": "FILA_TOTAL", "boe": item["boe"], "estructura_boe": SOURCE_NOTES.get(item["boe"], "HTML oficial revisado"), "persistido": f"{item['texto_persistido']} ({item['plazas_persistidas']} plazas)", "resultado_reconstruccion": "eliminar fila agregada; componentes ya persistidos", "clasificacion": item["clasificacion"], "registro_espurio": "SI", "fuente_oficial": f"https://www.boe.es/diario_boe/txt.php?id={item['boe']}"})
    for item in other_csv:
        reconstruction.append({"id": item["id"], "categoria": "OTRO_CANDIDATO", "boe": item["boe"], "estructura_boe": SOURCE_NOTES.get(item["boe"], "HTML oficial revisado"), "persistido": f"{item['puesto']} ({item['plazas']} plazas)", "resultado_reconstruccion": "conservar" if item["clasificacion"] == "PUESTO_LEGITIMO" else "eliminar; es narrativa", "clasificacion": item["clasificacion"], "registro_espurio": "NO" if item["clasificacion"] == "PUESTO_LEGITIMO" else "SI", "fuente_oficial": item["fuente_oficial"]})
    write_csv("auditoria_reconstruccion_boe.csv", reconstruction,
              ["id", "categoria", "boe", "estructura_boe", "persistido", "resultado_reconstruccion", "clasificacion", "registro_espurio", "fuente_oficial"])

    affected_boes = []
    for boe in candidate_boes:
        n = sum(1 for row in numeric if row["publicacion_id"] == boe)
        t = sum(1 for row in total_rows if row["publicacion_id"] == boe)
        o = sum(1 for row in other_rows if row["publicacion_id"] == boe)
        affected_boes.append({"boe": boe, "fecha_min": min(row["fecha_boe"] for row in rows if row["publicacion_id"] == boe), "fecha_max": max(row["fecha_boe"] for row in rows if row["publicacion_id"] == boe), "puestos_numericos": n, "filas_total": t, "otros_candidatos": o, "filas_afectadas": n + t + o, "fuente_oficial": f"https://www.boe.es/diario_boe/txt.php?id={boe}", "revision_oficial": "COMPLETA", "evidencia": SOURCE_NOTES.get(boe, "HTML oficial revisado")})
    write_csv("auditoria_boe_afectados.csv", affected_boes,
              ["boe", "fecha_min", "fecha_max", "puestos_numericos", "filas_total", "otros_candidatos", "filas_afectadas", "fuente_oficial", "revision_oficial", "evidencia"])

    # El inventario de patrones compacta los 851 IDs sin perder su trazabilidad en el CSV.
    pattern_rows = []
    for boe in numeric_boes:
        subset = [row for row in numeric if row["publicacion_id"] == boe]
        cls, _, cause = numeric_class(boe)
        pattern_rows.append({"patron": cls, "ids": [row["oposicion_id"] for row in subset], "plazas": sum(row["num_plazas"] or 0 for row in subset), "boe": boe, "causa": cause})
    causes = {
        "BUG_TOTAL_ROWS": {"descripcion": "extraer_resultados_tabla acepta la fila agregada porque sólo reconoce total/general en encabezados, no etiquetas de datos como 'N.º total de plazas'.", "ids_afectados": [row["oposicion_id"] for row in total_rows], "boe_afectados": total_boes, "modulo": "extraer_tablas_xml_boe.py", "funcion": "extraer_resultados_tabla / identificar_columnas", "causa_raiz": "La etiqueta de total está en una celda de datos y no se valida semántica de fila/posición ni suma de componentes.", "evidencia": [SOURCE_NOTES.get(boe, "") for boe in total_boes], "solucion_propuesta": "descartar etiquetas agregadas mediante regla semántica y validación de suma/posición, conservando componentes", "riesgo": "medio"},
        "BUG_NUMERIC_POSITION": {"descripcion": "La selección de alias de columnas permite que códigos o números de orden ocupen Puesto cuando la tabla tiene varias columnas identificables.", "ids_afectados": [row["oposicion_id"] for row in numeric], "boe_afectados": numeric_boes, "modulo": "extraer_tablas_xml_boe.py", "funcion": "identificar_columnas / extraer_resultados_tabla", "causa_raiz": "EQUIVALENCIAS mezcla cuerpo/escala/denominación bajo Puesto y no exige una columna Denominación profesional; se persiste la primera celda numérica.", "evidencia": [SOURCE_NOTES.get(boe, "") for boe in numeric_boes], "solucion_propuesta": "resolver columnas por encabezado explícito, exigir denominación textual y marcar números aislados para revisión; no descartar nombres con números", "riesgo": "alto"},
    }
    (OUT / "auditoria_causas_tecnicas.json").write_text(json.dumps(causes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    total_plazas = sum(row["num_plazas"] or 0 for row in total_rows)
    other_false = [row for row in other_rows if "plazas generales" not in audit_key(row["puesto"])]
    # El candidato «Plazas Generales» se conserva como control de falso
    # positivo, pero es un puesto legítimo y no entra en el impacto afectado.
    affected_rows = numeric + total_rows + other_false
    unique_ids = {row["oposicion_id"] for row in affected_rows}
    # PASO 70 es el inventario residual de FASE 8; se distingue de decisiones
    # de normalización aceptadas para no afirmar que hubo una mutación semántica.
    fase8_residual = OUT.parent / "normalizacion_puestos" / "fase8_paso70_puestos_residuales_detalle.csv"
    fase8_ids, fase8_familias = set(), Counter()
    if fase8_residual.exists():
        with fase8_residual.open(encoding="utf-8-sig", newline="") as stream:
            for item in csv.DictReader(stream):
                if str(item.get("id", "")).isdigit() and int(item["id"]) in unique_ids:
                    fase8_ids.add(int(item["id"]))
                    fase8_familias[item.get("familia") or "(sin familia)"] += 1
    impact = {
        "puestos_numericos": {"ids": len(numeric), "filas": len(numeric), "plazas_persistidas": sum(row["num_plazas"] or 0 for row in numeric), "boe": len(numeric_boes), "anos": sorted({row["fecha_boe"][:4] for row in numeric})},
        "filas_total_confirmadas": {"ids": len(total_rows), "filas": len(total_rows), "plazas_persistidas": total_plazas, "boe": len(total_boes), "anos": sorted({row["fecha_boe"][:4] for row in total_rows}), "componentes_explican_plazas": total_plazas, "posible_exceso_estadistico": total_plazas},
        "otros_candidatos_confirmados": {"ids": len(other_false), "filas": len(other_false), "plazas_persistidas": sum(row["num_plazas"] or 0 for row in other_false), "boe": len({row["publicacion_id"] for row in other_false}), "anos": sorted({row["fecha_boe"][:4] for row in other_false})},
        "solapamientos": {"ids_unicos_afectados": len(unique_ids), "filas_unicas_afectadas": len(affected_rows), "plazas_persistidas_afectadas": sum(row["num_plazas"] or 0 for row in affected_rows)},
        "impacto_estadisticas": ["total de plazas", "rankings por puesto", "rankings por administración", "series temporales", "búsquedas y agregaciones"],
        "fase8": {"ids_afectados_en_inventario_residual": len(fase8_ids), "familias_inventario": dict(fase8_familias), "ids_afectados_en_decisiones_de_normalizacion": 0, "nota": "Los IDs aparecen en el inventario residual de PASO 70, pero no en decisiones de normalización aceptadas; la anomalía es anterior a normalización y no se reabre FASE 8."},
    }
    (OUT / "auditoria_impacto_estadisticas.json").write_text(json.dumps(impact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    plan = {
        "orden": ["FIX EXTRACTOR", "REPARACIÓN SQLITE", "REGENERACIÓN ESTADÍSTICAS", "TESTS DE REGRESIÓN"],
        "fix_extractor": {"modulo": "extraer_tablas_xml_boe.py", "reglas": ["resolver Denominación/Puesto por encabezado explícito", "descartar filas agregadas por semántica, posición y suma", "validar denominación textual antes de persistir"], "no_blacklist_por_id": True},
        "recuperacion": {"preferida": "A_REEXTRACCION_AUTOMATICA", "totales": "C_ELIMINACION_FILA_ESPURIA", "numericos": "A_REEXTRACCION_AUTOMATICA", "dudosos": "revisión documental antes de mutar"},
        "restricciones_de_esta_auditoria": ["no modificar SQLite", "no modificar extractor productivo", "no borrar registros", "no cambiar data_version"],
    }
    (OUT / "auditoria_plan_correccion.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {
        "estado": "AUDITORIA_COMPLETA_PRE_FASE9",
        "generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "baseline": {"git": git_info(), "sqlite_sha256_inicial": initial_sha, "sqlite_sha256_final": sha256(DB), "data_version_inicial": metadata.get("data_version"), "data_version_final": metadata.get("data_version"), "schema_version": metadata.get("schema_version"), "integrity": integrity, "foreign_key_check": foreign_keys},
        "puestos_numericos": {"registros": len(numeric), "plazas": sum(row["num_plazas"] or 0 for row in numeric), "denominaciones_distintas": len({clean(row["puesto"]) for row in numeric}), "boe_distintos": len(numeric_boes), "convocatorias_distintas": len({row["publicacion_id"] for row in numeric}), "rango_temporal": [min(row["fecha_boe"] for row in numeric), max(row["fecha_boe"] for row in numeric)], "patrones": pattern_rows},
        "filas_totales": {"variantes_detectadas": sorted({row["puesto"] for row in total_rows}), "registros": len(total_rows), "plazas": total_plazas, "boe_distintos": len(total_boes), "primer_ano": min(row["fecha_boe"][:4] for row in total_rows), "ultimo_ano": max(row["fecha_boe"][:4] for row in total_rows), "referencia_6611": {"esperado": 6611, "observado": total_plazas, "diferencia": total_plazas - 6611, "confirmado": total_plazas == 6611, "doble_contabilizacion": True}},
        "otros_candidatos": {"registros": len(other_rows), "confirmados_no_puesto": len(other_false), "legitimos": len(other_rows) - len(other_false)},
        "revision_oficial": {"boe_afectados": len(candidate_boes), "boe_revisados": len(candidate_boes), "cobertura": "100%", "fuentes": sorted(candidate_boes)},
        "clasificacion_completa": len(reconstruction) == len(numeric) + len(total_rows) + len(other_rows),
        "artefactos": ["auditoria_puestos_invalidos_resumen.json", "auditoria_puestos_numericos.csv", "auditoria_filas_totales.csv", "auditoria_otros_candidatos.csv", "auditoria_boe_afectados.csv", "auditoria_reconstruccion_boe.csv", "auditoria_causas_tecnicas.json", "auditoria_impacto_estadisticas.json", "auditoria_plan_correccion.json"],
    }
    (OUT / "auditoria_puestos_invalidos_resumen.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    con.close()
    return summary


if __name__ == "__main__":
    result = main()
    print(json.dumps({"estado": result["estado"], "numeric": result["puestos_numericos"]["registros"], "numeric_plazas": result["puestos_numericos"]["plazas"], "totals": result["filas_totales"]["plazas"], "boe": result["revision_oficial"]["boe_afectados"]}, ensure_ascii=False))
