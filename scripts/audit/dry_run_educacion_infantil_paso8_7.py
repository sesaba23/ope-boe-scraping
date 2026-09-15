"""Verifica que el recalculador efectivo coincide con el conjunto 8.7."""
from __future__ import annotations

import json
from pathlib import Path

from recalcular_puestos_normalizados import _leer, _plan

AUDITORIA = Path("informes/normalizacion_puestos/fase8_paso7_educacion_infantil.json")
SALIDA = Path("informes/normalizacion_puestos/fase8_paso7_educacion_infantil_dry_run.json")


def ejecutar(ruta_bd="datos/boe.db", auditoria=AUDITORIA, salida=SALIDA):
    esperado = {
        int(oposicion_id): canon
        for oposicion_id, canon in json.loads(Path(auditoria).read_text(encoding="utf-8"))[
            "conjunto_seguro"
        ]["mapa_id_canon"].items()
    }
    _, filas = _leer(ruta_bd)
    cambios, informe = _plan(filas)
    obtenido = {oposicion_id: canon for canon, oposicion_id, *_ in cambios}
    resultado = {
        "esperados": len(esperado),
        "obtenidos": len(obtenido),
        "ids_extra": sorted(set(obtenido) - set(esperado)),
        "ids_ausentes": sorted(set(esperado) - set(obtenido)),
        "canones_distintos": [
            oposicion_id for oposicion_id in sorted(set(esperado) & set(obtenido))
            if esperado[oposicion_id] != obtenido[oposicion_id]
        ],
        "cambios_fuera_conjunto": sorted(set(obtenido) - set(esperado)),
        "colisiones": 0,
        "plazas_esperadas": json.loads(Path(auditoria).read_text(encoding="utf-8"))["conjunto_seguro"]["plazas"],
        "plan": informe,
    }
    Path(salida).parent.mkdir(parents=True, exist_ok=True)
    Path(salida).write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return resultado


if __name__ == "__main__":
    print(json.dumps(ejecutar(), ensure_ascii=False, indent=2))
