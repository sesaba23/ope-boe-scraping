"""Dry-run y reparación transaccional de los 879 registros pre-FASE 9.

La reextracción se hace contra el XML oficial del BOE y se contrasta con los
IDs auditados antes de permitir cualquier escritura en SQLite.  Sin ``--apply``
el script es estrictamente de sólo lectura.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sqlite3
import sys
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import extraer_tablas_xml_boe as extractor
from normalizacion_puestos import normalizar_puesto


DB = ROOT / "datos" / "boe.db"
OUT = ROOT / "informes" / "auditoria_extraccion"
NUMERIC_CSV = OUT / "auditoria_puestos_numericos.csv"
TOTAL_CSV = OUT / "auditoria_filas_totales.csv"
OTHER_CSV = OUT / "auditoria_otros_candidatos.csv"
XML_CACHE = Path(tempfile.gettempdir()) / "boe_xml_pre9"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split()).strip()


def is_numeric(value: object) -> bool:
    return extractor._entero_positivo(clean(value)) is not None


def load_ids(path: Path, key: str = "id") -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def download_xml(boe: str) -> bytes:
    XML_CACHE.mkdir(parents=True, exist_ok=True)
    path = XML_CACHE / f"{boe}.xml"
    if not path.exists():
        response = requests.get(f"https://www.boe.es/diario_boe/xml.php?id={boe}", timeout=40)
        response.raise_for_status()
        path.write_bytes(response.content)
    return path.read_bytes()


def source_candidates(boe: str) -> list[dict]:
    """Flatten XML rows while retaining stable document coordinates."""
    candidates = []
    ordinal = 0
    for table_index, table in enumerate(extractor.parsear_tablas_xml(download_xml(boe))):
        columns = extractor.identificar_columnas(table["encabezados"])
        puesto_index = columns.get("Puesto")
        plazas_index = columns.get("Num_plazas")
        if puesto_index is None or plazas_index is None:
            continue
        for row_index, row in enumerate(table["filas"]):
            if plazas_index >= len(row):
                continue
            plazas = extractor._entero_positivo(row[plazas_index])
            if plazas is None:
                continue
            denominacion = clean(row[puesto_index]) if puesto_index < len(row) else ""
            if not denominacion:
                continue
            candidates.append({
                "ordinal": ordinal,
                "table": table_index,
                "row": row_index,
                "puesto": denominacion,
                "plazas": plazas,
                "encabezado": table["encabezados"][puesto_index],
                "fila": row,
            })
            ordinal += 1
    return candidates


def map_numeric_rows(con: sqlite3.Connection, numeric_rows: list[dict]) -> list[dict]:
    by_boe: dict[str, list[sqlite3.Row]] = {}
    con.row_factory = sqlite3.Row
    for item in numeric_rows:
        row = con.execute("SELECT * FROM oposiciones WHERE oposicion_id=?", (int(item["id"]),)).fetchone()
        if row is None:
            raise RuntimeError(f"No existe el ID auditado {item['id']}")
        by_boe.setdefault(row["publicacion_id"], []).append(row)

    mapped = []
    for boe, rows in sorted(by_boe.items()):
        candidates = source_candidates(boe)
        previous = -1
        for row in sorted(rows, key=lambda value: value["oposicion_id"]):
            old = clean(row["puesto"])
            plazas = row["num_plazas"]
            all_matches = [candidate for candidate in candidates
                           if old in {clean(cell) for cell in candidate["fila"]}
                           and candidate["plazas"] == plazas]
            forward = [candidate for candidate in all_matches if candidate["ordinal"] > previous]
            if not forward:
                raise RuntimeError(f"No hay correspondencia XML para {row['oposicion_id']} ({boe}, {old}, {plazas})")
            # El orden de aparición, después de fijar código y plazas, es la
            # clave estable del extractor histórico.  Se registra la
            # multiplicidad para que nunca quede oculta en el artefacto.
            selected = forward[0]
            previous = selected["ordinal"]
            if is_numeric(selected["puesto"]):
                raise RuntimeError(f"La reextracción sigue siendo numérica para {row['oposicion_id']}")
            mapped.append({
                "id": row["oposicion_id"], "boe": boe,
                "puesto_antes": row["puesto"], "puesto_despues": selected["puesto"],
                "puesto_normalizado_antes": row["puesto_normalizado"],
                "puesto_normalizado_despues": normalizar_puesto(selected["puesto"]),
                "plazas_antes": row["num_plazas"], "plazas_despues": selected["plazas"],
                "campos_adicionales_modificados": "puesto,puesto_normalizado",
                "clave_correspondencia": f"{boe}:tabla={selected['table']}:fila={selected['row']}:codigo/plazas={old}/{plazas}",
                "evidencia": f"https://www.boe.es/diario_boe/txt.php?id={boe}",
                "candidatos_clave": len(forward),
                "confianza": "ALTA" if len(forward) == 1 else "ALTA_ESTRUCTURAL_ORDEN",
            })
    if len(mapped) != len(numeric_rows):
        raise RuntimeError(f"Correspondencias incompletas: {len(mapped)}/{len(numeric_rows)}")
    return sorted(mapped, key=lambda item: item["id"])


def stats(con: sqlite3.Connection) -> dict:
    count, plazas = con.execute("SELECT count(*), COALESCE(sum(num_plazas),0) FROM oposiciones").fetchone()
    return {"filas": count, "plazas": int(plazas)}


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_dry_run(con: sqlite3.Connection) -> dict:
    numeric_rows = load_ids(NUMERIC_CSV)
    total_rows = load_ids(TOTAL_CSV)
    other_rows = [row for row in load_ids(OTHER_CSV) if row["clasificacion"] != "PUESTO_LEGITIMO"]
    if len(numeric_rows) != 863 or len(total_rows) != 13 or len(other_rows) != 3:
        raise RuntimeError("El universo auditado no coincide con 863 + 13 + 3")
    ids = [int(row["id"]) for row in numeric_rows + total_rows + other_rows]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Hay solapamiento entre las categorías auditadas")
    existing_numeric = [row["id"] for row in numeric_rows
                        if (db_row := con.execute("SELECT puesto FROM oposiciones WHERE oposicion_id=?", (int(row["id"]),)).fetchone())
                        and clean(db_row[0]) == clean(row["puesto_persistido"])]
    existing_espurios = [row["id"] for row in total_rows + other_rows if con.execute("SELECT 1 FROM oposiciones WHERE oposicion_id=?", (int(row["id"]),)).fetchone()]
    if existing_numeric and len(existing_numeric) != len(numeric_rows):
        raise RuntimeError("Estado parcial: sólo parte de los numéricos existe")
    if existing_espurios and len(existing_espurios) != len(total_rows) + len(other_rows):
        raise RuntimeError("Estado parcial: sólo parte de los espurios existe")
    idempotent = not existing_numeric and not existing_espurios
    numeric = map_numeric_rows(con, numeric_rows) if not idempotent else []
    if not idempotent and sum(int(row["plazas_antes"]) for row in numeric) != 1123:
        raise RuntimeError("La suma de plazas numéricas no coincide con 1.123")
    if sum(int(row["plazas_persistidas"]) for row in total_rows) != 6611:
        raise RuntimeError("La suma de filas total no coincide con 6.611")
    if sum(int(row["plazas"]) for row in other_rows) != 24:
        raise RuntimeError("La suma narrativa no coincide con 24")
    espurios = []
    for row in total_rows:
        espurios.append({"id": int(row["id"]), "boe": row["boe"], "texto": row["texto_persistido"], "plazas": int(row["plazas_persistidas"]), "tipo": "TOTAL_ROWS", "duplicacion": "SI", "motivo_eliminacion": "Fila agregada; sus componentes ya están persistidos"})
    for row in other_rows:
        espurios.append({"id": int(row["id"]), "boe": row["boe"], "texto": row["puesto"], "plazas": int(row["plazas"]), "tipo": "NARRATIVE_ROW", "duplicacion": "NO", "motivo_eliminacion": "Narrativa capturada como puesto; no es denominación profesional"})
    initial = stats(con)
    after = initial if idempotent else {"filas": initial["filas"] - 16, "plazas": initial["plazas"] - 6611 - 24}
    return {"numeric": numeric, "espurios": espurios, "initial": initial, "after": after,
            "numeric_plazas": 1123, "total_plazas": 6611, "narrative_plazas": 24,
            "exceso_estadistico_totales": 6611, "filas_reextraidas": 25,
            "numeric_reconstructed": len(numeric), "espurios_absent": len(espurios),
            "idempotente": idempotent,
            "legitimate_id": 102427}


def apply_repair(dry: dict) -> dict:
    if dry.get("idempotente"):
        return {"no_op": True, "data_version": 63}
    backup_dir = ROOT / "backups" / "sqlite"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = backup_dir / f"boe_pre_fase9_puestos_invalidos_{stamp}.db"
    original_sha = sha256(DB)
    shutil.copy2(DB, backup)
    backup_sha = sha256(backup)
    if original_sha != backup_sha:
        raise RuntimeError("El backup no coincide con SQLite original")

    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys=ON")
    try:
        con.execute("BEGIN IMMEDIATE")
        version = int(con.execute("SELECT valor FROM metadata WHERE clave='data_version'").fetchone()[0])
        if version != 62:
            raise RuntimeError(f"data_version inesperada: {version}")
        for row in dry["numeric"]:
            con.execute("UPDATE oposiciones SET puesto=?, puesto_normalizado=? WHERE oposicion_id=?",
                        (row["puesto_despues"], row["puesto_normalizado_despues"], row["id"]))
        for row in dry["espurios"]:
            con.execute("DELETE FROM oposiciones WHERE oposicion_id=?", (row["id"],))
        con.execute("UPDATE metadata SET valor='63' WHERE clave='data_version'")
        remaining_numeric = con.execute("SELECT count(*) FROM oposiciones WHERE puesto GLOB '[0-9]*' AND puesto NOT GLOB '*[^0-9 ./+-]*'").fetchone()[0]
        remaining_total = con.execute("SELECT count(*) FROM oposiciones WHERE lower(trim(puesto)) IN ('n.º total de plazas.','nº total de plazas','n.° total de plazas','número total de plazas','total de plazas','total plazas')").fetchone()[0]
        remaining_narrative = con.execute("SELECT count(*) FROM oposiciones WHERE lower(trim(puesto)) IN ('del total de las plazas','del total de la convocatoria')").fetchone()[0]
        if (remaining_numeric, remaining_total, remaining_narrative) != (0, 0, 0):
            raise RuntimeError("Quedan patrones inválidos dentro de la transacción")
        if con.execute("SELECT count(*) FROM oposiciones WHERE oposicion_id=102427 AND puesto=?", ("Técnico/a Medio de Gestión Plazas Generales",)).fetchone()[0] != 1:
            raise RuntimeError("Se alteró el candidato legítimo")
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or list(con.execute("PRAGMA foreign_key_check")):
            raise RuntimeError("Fallo de integridad/FK; rollback")
        con.commit()
    except Exception:
        con.rollback()
        con.close()
        raise
    con.close()
    return {"backup": str(backup), "sha_original": original_sha, "sha_backup": backup_sha, "data_version_antes": 62, "data_version_despues": 63}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="aplica la transacción después del dry-run")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    dry = build_dry_run(con)
    con.close()
    fields_numeric = ["id", "boe", "puesto_antes", "puesto_despues", "puesto_normalizado_antes", "puesto_normalizado_despues", "plazas_antes", "plazas_despues", "campos_adicionales_modificados", "clave_correspondencia", "evidencia", "candidatos_clave", "confianza"]
    if not dry.get("idempotente"):
        write_csv(OUT / "reparacion_puestos_numericos.csv", dry["numeric"], fields_numeric)
        write_csv(OUT / "reparacion_filas_espurias.csv", dry["espurios"], ["id", "boe", "texto", "plazas", "tipo", "duplicacion", "motivo_eliminacion"])
        write_csv(OUT / "reparacion_dry_run.csv", dry["numeric"] + dry["espurios"], ["id", "boe", "puesto_antes", "puesto_despues", "plazas_antes", "plazas_despues", "tipo", "duplicacion", "clave_correspondencia"])
    result = {"modo": "apply" if args.apply else "dry-run", **{k: v for k, v in dry.items() if k not in {"numeric", "espurios"}}}
    if args.apply and not dry.get("idempotente"):
        result["aplicacion"] = apply_repair(dry)
    elif args.apply:
        result["aplicacion"] = apply_repair(dry)
    (OUT / "reparacion_puestos_invalidos_resumen.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
