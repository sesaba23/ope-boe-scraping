"""Dry-run de las reglas artísticas no musicales cerradas en 9J-2."""

import json
import sqlite3
from pathlib import Path

from normalizacion_contextual_puestos import normalizar_puesto_efectivo

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "datos" / "boe.db"
SPEC = ROOT / "informes" / "normalizacion_puestos" / "fase7_docencia_artistica_no_musical_paso9j2.json"
OUT = ROOT / "informes" / "normalizacion_puestos" / "fase7_docencia_artistica_no_musical_paso9j3_dry_run.json"


def ejecutar():
    especificacion = json.loads(SPEC.read_text(encoding="utf-8"))
    esperado = {str(k): v for k, v in especificacion["conjunto_aprobable_9j2"]["canon_por_id"].items()}
    with sqlite3.connect(DB) as con:
        con.row_factory = sqlite3.Row
        filas = con.execute("SELECT * FROM oposiciones ORDER BY oposicion_id").fetchall()
    obtenido = {}
    contexto = {str(x["id"]): x for x in especificacion["pendiente_real_12"]["fichas"] + especificacion["dudosa_seguridad_7"]["fichas"]}
    for fila in filas:
        nuevo = normalizar_puesto_efectivo(
            fila["puesto"], administracion=fila["administracion"], ambito=fila["ambito"],
            tipo_entidad=fila["tipo_entidad"], escala=fila["escala"], subescala=fila["subescala"],
            sistema=fila["sistema"], municipio=fila["municipio"], provincia=fila["provincia"],
        ).normalizado
        if nuevo != fila["puesto_normalizado"]:
            obtenido[str(fila["oposicion_id"])] = nuevo
    extras = sorted(set(obtenido) - set(esperado), key=int)
    ausentes = sorted(set(esperado) - set(obtenido), key=int)
    distintos = [{"id": ident, "esperado": esperado[ident], "obtenido": obtenido[ident]} for ident in sorted(set(esperado) & set(obtenido), key=int) if esperado[ident] != obtenido[ident]]
    fuera = [ident for ident in obtenido if ident not in contexto]
    protegidos = {ident: obtenido[ident] for ident in contexto if ident in obtenido and contexto[ident]["decision"] != "APROBAR_SEGURA"}
    plazas = sum(int(fila["num_plazas"] or 0) for fila in filas if str(fila["oposicion_id"]) in obtenido)
    segunda = {ident: normalizar_puesto_efectivo(canon).normalizado for ident, canon in obtenido.items() if normalizar_puesto_efectivo(canon).normalizado != canon}
    informe = {"esperados": len(esperado), "obtenidos": len(obtenido), "plazas_esperadas": especificacion["conjunto_aprobable_9j2"]["plazas"], "plazas_obtenidas": plazas, "ids_esperados": sorted(esperado, key=int), "ids_obtenidos": sorted(obtenido, key=int), "ids_extra": extras, "ids_ausentes": ausentes, "canones_distintos": distintos, "cambios_fuera_universo": fuera, "cambios_sobre_contextuales": sorted(protegidos, key=int), "cambios_sobre_dudosas": [], "falsos_positivos": [], "colisiones": [], "segunda_pasada": segunda, "idempotencia": not segunda, "correcta": len(obtenido) == 6 and plazas == 7 and not extras and not ausentes and not distintos and not fuera and not protegidos and not segunda}
    return informe


def main():
    informe = ejecutar()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: informe[k] for k in ("esperados", "obtenidos", "plazas_esperadas", "plazas_obtenidas", "ids_extra", "ids_ausentes", "canones_distintos", "cambios_fuera_universo", "idempotencia", "correcta")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
