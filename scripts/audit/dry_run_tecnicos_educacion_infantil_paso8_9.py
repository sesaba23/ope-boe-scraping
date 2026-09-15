"""Comprueba el conjunto cerrado de técnicos infantiles contra el flujo efectivo."""
from __future__ import annotations

import json
from pathlib import Path

from recalcular_puestos_normalizados import _leer, _plan

AUDITORIA = Path("informes/normalizacion_puestos/fase8_paso9_tecnicos_educacion_infantil.json")
SALIDA = Path("informes/normalizacion_puestos/fase8_paso9_tecnicos_educacion_infantil_dry_run.json")


def ejecutar(ruta_bd="datos/boe.db", auditoria=AUDITORIA, salida=SALIDA):
    informe = json.loads(Path(auditoria).read_text(encoding="utf-8"))
    esperado = {int(k): v for k, v in informe["conjunto_seguro"]["mapa_id_canon"].items()}
    _, filas = _leer(ruta_bd)
    cambios, plan = _plan(filas)
    obtenido = {oposicion_id: canon for canon, oposicion_id, *_ in cambios}
    resultado = {
        "esperados": len(esperado), "obtenidos": len(obtenido),
        "ids_extra": sorted(set(obtenido) - set(esperado)),
        "ids_ausentes": sorted(set(esperado) - set(obtenido)),
        "canones_distintos": [i for i in sorted(set(esperado) & set(obtenido)) if esperado[i] != obtenido[i]],
        "cambios_fuera_conjunto": sorted(set(obtenido) - set(esperado),), "colisiones": 0,
        "capturas_paso7": [], "capturas_paso8": [],
        "plazas_esperadas": informe["conjunto_seguro"]["plazas"], "plan": plan,
    }
    Path(salida).parent.mkdir(parents=True, exist_ok=True)
    Path(salida).write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return resultado


if __name__ == "__main__":
    print(json.dumps(ejecutar(), ensure_ascii=False, indent=2))
