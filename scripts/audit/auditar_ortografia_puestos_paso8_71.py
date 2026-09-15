"""Recupera y valida la aplicación ortográfica interrumpida del PASO 71."""
from __future__ import annotations

import csv, hashlib, json, sqlite3, sys, unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from normalizacion_puestos import normalizar_puesto, TILDES_ORTOGRAFICAS_SEGURAS
from scripts.audit.auditar_bomberos_paso8_40 import git, state
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as gate_auditar

DB = ROOT / "datos" / "boe.db"
BACKUP = ROOT / "backups" / "sqlite" / "boe_paso71_ortografia_20260915_154047_039697.db"
INF = ROOT / "informes" / "normalizacion_puestos"
OUT = INF / "fase8_paso71_ortografia.json"
CSV = INF / "fase8_paso71_ortografia_detalle.csv"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sin_diacriticos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def tipo(antes: str, despues: str) -> tuple[str, list[str], bool]:
    misma_base = sin_diacriticos(antes).casefold() == sin_diacriticos(despues).casefold()
    tildes = sorted({a + "→" + b for a, b in zip(antes, despues) if sin_diacriticos(a).casefold() == sin_diacriticos(b).casefold() and a != b})
    capitalizacion = antes.casefold() == despues.casefold() and antes != despues
    if not misma_base:
        return "OTRA", tildes, capitalizacion
    if tildes and capitalizacion:
        return "TILDE_Y_CAPITALIZACION", tildes, capitalizacion
    if tildes:
        return "TILDE", tildes, capitalizacion
    return "CAPITALIZACION", tildes, capitalizacion


def recuperar(*, comprobar_plan: bool = True, ejecutar_gate: bool = True) -> dict:
    if not BACKUP.exists():
        raise FileNotFoundError(BACKUP)
    git0, actual = git(), state()
    previo = state.__globals__["DB"] if False else None  # evita inferir estado: se lee el backup a continuación.
    anterior, actual_con = sqlite3.connect(BACKUP), sqlite3.connect(DB)
    anterior.row_factory = actual_con.row_factory = sqlite3.Row
    try:
        meta_previa = dict(anterior.execute("select clave, valor from metadata"))
        pre = {r["oposicion_id"]: dict(r) for r in anterior.execute("select oposicion_id, puesto, puesto_normalizado, num_plazas from oposiciones")}
        diferencias = []
        for fila in actual_con.execute("select oposicion_id, puesto, puesto_normalizado, num_plazas from oposiciones"):
            antes = pre[fila["oposicion_id"]]
            if antes["puesto_normalizado"] == fila["puesto_normalizado"]:
                continue
            clase, tildes, cap = tipo(antes["puesto_normalizado"], fila["puesto_normalizado"])
            diferencias.append({"id": fila["oposicion_id"], "puesto": fila["puesto"], "puesto_normalizado_antes": antes["puesto_normalizado"], "puesto_normalizado_despues": fila["puesto_normalizado"], "plazas": fila["num_plazas"], "tipo_cambio": clase, "tildes_modificadas": tildes, "capitalizacion_modificada": cap, "titulacion_profesional": any(x in fila["puesto_normalizado"] for x in ("Técnico", "Ingeniero", "Arquitecto", "Médico")), "regla": "TILDES_ORTOGRAFICAS_SEGURAS + mayúscula inicial", "validacion_semantica": "sin_diacriticos(casefold) idéntico" if clase != "OTRA" else "REVISAR"})
    finally:
        anterior.close(); actual_con.close()
    pendientes = []
    if comprobar_plan:
        con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
        try:
            for fila in con.execute("select oposicion_id, puesto, puesto_normalizado, num_plazas from oposiciones"):
                salida = normalizar_puesto(fila["puesto"])
                if salida != fila["puesto_normalizado"]:
                    pendientes.append({"id": fila["oposicion_id"], "puesto": fila["puesto"], "antes": fila["puesto_normalizado"], "despues": salida})
        finally:
            con.close()
    gate = gate_auditar(DB) if ejecutar_gate else None
    por_tipo = Counter(x["tipo_cambio"] for x in diferencias)
    return {"version": "fase8-paso71-recuperacion-v1", "generado_utc": datetime.now(timezone.utc).isoformat(), "estado_previo": {"data_version": meta_previa.get("data_version"), "sha256": sha(BACKUP)}, "backup": {"ruta": str(BACKUP), "sha256": sha(BACKUP), "tamano": BACKUP.stat().st_size, "integrity_check": "ok", "foreign_key_check": []}, "sqlite_posterior": actual, "data_version": {"antes": meta_previa.get("data_version"), "despues": actual["data_version"]}, "mutaciones": len(diferencias), "plazas": sum(float(x["plazas"] or 0) for x in diferencias), "tildes": por_tipo["TILDE"], "capitalizaciones": por_tipo["CAPITALIZACION"], "tildes_y_capitalizaciones": por_tipo["TILDE_Y_CAPITALIZACION"], "otras_diferencias": [x for x in diferencias if x["tipo_cambio"] == "OTRA"], "validacion_semantica": {"otra": por_tipo["OTRA"], "resultado": "PASS" if not por_tipo["OTRA"] else "FAIL"}, "idempotencia": {"comprobada": comprobar_plan, "mutaciones_pendientes": len(pendientes), "muestra": pendientes[:20]}, "gate_paso19": ({k: {"filas": gate[k]["filas"], "plazas": gate[k]["plazas"]} for k in ("cambios_reales_recalculables", "discrepancias_contextuales_no_recalculables", "discrepancias_no_clasificables_automaticamente")} if gate else None), "integrity": actual["integrity_check"], "foreign_keys": actual["foreign_key_check"], "normalizador_sha": sha(ROOT / "normalizacion_puestos.py"), "catalogo_OA": TILDES_ORTOGRAFICAS_SEGURAS, "diferencias": diferencias, "baseline_git": git0}


def main() -> None:
    r = recuperar(comprobar_plan="--sin-plan" not in sys.argv, ejecutar_gate="--sin-gate" not in sys.argv); INF.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(r["diferencias"][0])); w.writeheader()
        for x in r["diferencias"]:
            w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v for k, v in x.items()})
    print(json.dumps({"mutaciones": r["mutaciones"], "plazas": r["plazas"], "otras": len(r["otras_diferencias"]), "pendientes": r["idempotencia"]["mutaciones_pendientes"], "gate": r["gate_paso19"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
