"""Compone la auditoría de coherencia e idempotencia del Paso 2B."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from scripts.audit.validar_normalizacion_puestos_dry_run import ejecutar_dry_run


def generar_informe(ruta_bd="datos/boe.db", *, diagnostico_inicial=None):
    """Ejecuta sólo lecturas SQLite y devuelve el informe consolidado."""
    dry_run = ejecutar_dry_run(ruta_bd)

    inicial = {}
    if diagnostico_inicial:
        inicial = json.loads(Path(diagnostico_inicial).read_text(encoding="utf-8"))
    return {
        "version": "fase4-paso2b-v1",
        "generado_utc": datetime.now(timezone.utc).isoformat(),
        "modo_dry_run": True,
        "diagnostico_idempotencia_inicial": inicial,
        "correcciones_aplicadas": [
            "preprocesado ortotipográfico común antes de clasificar",
            "pipeline de normalización hasta punto fijo",
            "preservación de exclusiones semánticas de titulaciones durante el punto fijo",
        ],
        "resultado_idempotencia_final": {
            "fallos": dry_run["idempotencia_fallos"],
            "universo": "todas las denominaciones distintas de puesto",
        },
        "dry_run": dry_run,
        "cambios_fuera_objetivo_explicados": {
            "total": dry_run["cambios_fuera_objetivo"],
            "por_causa": dry_run["cambios_fuera_objetivo_por_causa"],
            "ejemplos": dry_run["ejemplos"].get("fuera_objetivo", []),
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bd", default="datos/boe.db")
    parser.add_argument("--diagnostico-inicial")
    parser.add_argument("--salida", default="informes/normalizacion_puestos_paso_2b.json")
    args = parser.parse_args(argv)
    informe = generar_informe(args.bd, diagnostico_inicial=args.diagnostico_inicial)
    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "fallos_idempotencia": informe["resultado_idempotencia_final"]["fallos"],
        "cambios_totales": informe["dry_run"]["cambios_totales"],
        "cambios_fuera_objetivo": informe["dry_run"]["cambios_fuera_objetivo"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
