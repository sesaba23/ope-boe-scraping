"""Auditoría read-only del comparador de puestos de estadísticas."""
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from consultas_boe import oposiciones
from estadisticas import calcular_comparacion_puestos_sqlite

DB = ROOT / "datos/boe.db"
INFORME = ROOT / "informes/normalizacion_puestos/fase8_paso29_comparador_puestos_estadisticas.json"

def auditar():
    antes = hashlib.sha256(DB.read_bytes()).hexdigest()
    opciones = sorted(oposiciones(DB, columnas=["Puesto_normalizado"])["Puesto_normalizado"].dropna().unique().tolist())
    comparadores = opciones[:5]
    principal = opciones[5] if len(opciones) > 5 else None
    modos = {
        "A_top5": calcular_comparacion_puestos_sqlite(DB),
        "B_principal": calcular_comparacion_puestos_sqlite(DB, puesto_principal=principal) if principal else None,
        "C_principal_comparadores": calcular_comparacion_puestos_sqlite(DB, puesto_principal=principal, comparadores=comparadores) if principal else None,
        "D_manual": calcular_comparacion_puestos_sqlite(DB, comparadores=comparadores),
    }
    despues = hashlib.sha256(DB.read_bytes()).hexdigest()
    checks = {
        "sqlite_inmutable": antes == despues,
        "cinco_comparadores": len(comparadores) == 5,
        "modo_a_top5": modos["A_top5"]["mode"] == "top5",
        "modo_d_manual": modos["D_manual"]["mode"] == "manual",
        "ejes_compartidos": all(not valor or all(len(serie["values"]) == len(valor["years"]) for serie in valor["series"]) for valor in modos.values()),
        "sin_duplicados": len({serie["label"] for serie in modos["D_manual"]["series"]}) == len(modos["D_manual"]["series"]),
    }
    return {"paso": "FASE 8 — PASO 29", "arquitectura": "Una consulta base sin filtro de puesto; agregación parametrizada en memoria para las series seleccionadas.", "api": {"parametro": "comparar" , "maximo": 5, "duplicados": "rechazados"}, "modos": {clave: (valor or {}) for clave, valor in modos.items()}, "ejemplo": {"principal": principal, "comparadores": comparadores}, "checks": checks, "ok": all(checks.values()), "sqlite_sha256": antes}

def main():
    informe = auditar(); INFORME.parent.mkdir(parents=True, exist_ok=True); INFORME.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"); print(json.dumps(informe, ensure_ascii=False, indent=2)); raise SystemExit(0 if informe["ok"] else 1)
if __name__ == "__main__": main()
