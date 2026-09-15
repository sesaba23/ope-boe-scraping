"""Audita las series históricas nuevas de estadísticas sin modificar SQLite."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from estadisticas import calcular_estadisticas_sqlite

INFORMES = ROOT / "informes/normalizacion_puestos"


def auditar():
    base = calcular_estadisticas_sqlite()
    meses = base["plazas_por_mes"]
    evolucion = base["evolucion_anual_puestos"]
    filtrada = calcular_estadisticas_sqlite(puesto="Maestro")
    vacia = calcular_estadisticas_sqlite(puesto="__puesto_inexistente_paso8_28__")
    checks = {
        "doce_meses_cronologicos": [fila["mes"] for fila in meses] == list(range(1, 13)),
        "meses_con_plazas_no_negativas": all(fila["plazas"] >= 0 for fila in meses),
        "top5_maximo": len(evolucion["series"]) <= 5,
        "anios_ordenados": evolucion["years"] == sorted(evolucion["years"]),
        "filtro_puesto_genera_serie": filtrada["evolucion_anual_puestos"]["mode"] == "selected",
        "filtro_vacio_sin_series": vacia["evolucion_anual_puestos"]["series"] == [],
    }
    return {"paso": "FASE 8 — PASO 28", "checks": checks, "ok": all(checks.values()),
            "base": {"total_plazas": base["total_plazas"], "total_registros": base["total_registros"]},
            "plazas_por_mes": meses, "evolucion_anual_puestos": evolucion,
            "generado_utc": datetime.now(timezone.utc).isoformat()}


def main():
    informe = auditar()
    INFORMES.mkdir(parents=True, exist_ok=True)
    destino = INFORMES / "fase8_paso28_graficas_estadisticas.json"
    destino.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(informe, ensure_ascii=False, indent=2))
    if not informe["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
