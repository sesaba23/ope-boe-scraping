"""Auditoría contextual read-only de pendientes de la familia Policía (Fase 7)."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from normalizacion_puestos import _clave, _preparar_texto, clasificar_policia_local


def clasificar_policia_aislada(fila):
    """Hipótesis contextual para auditoría; nunca se usa en producción."""
    if (fila["ambito"], fila["tipo_entidad"], fila["administracion"], fila["escala"], fila["sistema"]) == (
        "ESTATAL", "ESTATAL", "Ministerio del Interior", "Básica", "Oposición"
    ):
        return "SEGURA_POLICIA_NACIONAL", "Policía Nacional", "Ministerio del Interior + escala Básica + oposición"
    admin = (fila["administracion"] or "").casefold()
    if fila["ambito"] == "LOCAL" and fila["tipo_entidad"] == "MUNICIPAL" and admin.startswith(("ayuntamiento de", "concello de", "ajuntament de", "udal")):
        return "SEGURA_POLICIA_LOCAL", "Policía Local", "administración municipal identificada"
    if fila["administracion"] == "Administración Local" and fila["ambito"] == "INDETERMINADO":
        if fila["escala"] == "Administración Especial" and fila["subescala"] == "Servicios Especiales":
            return "PROBABLE_POLICIA_LOCAL", "Policía Local", "estructura municipal compatible, sin municipio ni cuerpo explícito"
    return "DUDOSA", None, "sin evidencia contextual suficiente"


def _estado(ruta):
    stat = ruta.stat()
    with sqlite3.connect(f"file:{ruta}?mode=ro", uri=True) as con:
        metadata = dict(con.execute("SELECT clave,valor FROM metadata WHERE clave IN ('schema_version','data_version')"))
        total, plazas = con.execute("SELECT COUNT(*),COALESCE(SUM(num_plazas),0) FROM oposiciones").fetchone()
        return {"sha256": hashlib.sha256(ruta.read_bytes()).hexdigest(), "tamano": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                "schema_version": int(metadata["schema_version"]), "data_version": int(metadata["data_version"]),
                "oposiciones": total, "plazas": plazas, "integrity_check": con.execute("PRAGMA integrity_check").fetchone()[0],
                "foreign_key_check": con.execute("PRAGMA foreign_key_check").fetchall(), "wal_existe": ruta.with_name(ruta.name + "-wal").exists(), "shm_existe": ruta.with_name(ruta.name + "-shm").exists()}


def _policial(texto):
    clave = _clave(_preparar_texto(texto) or "")
    return "polic" in clave or "guardia urbana" in clave


def auditar(ruta_bd="datos/boe.db"):
    ruta = Path(ruta_bd).resolve(); inicial = _estado(ruta)
    with sqlite3.connect(f"file:{ruta}?mode=ro", uri=True) as con:
        con.row_factory = sqlite3.Row
        filas = [dict(fila) for fila in con.execute(
            "SELECT o.*, p.titulo_original, p.departamento_boe, p.administracion_resuelta, p.familia_administrativa "
            "FROM oposiciones o LEFT JOIN publicaciones p ON p.publicacion_id=o.publicacion_id"
        )]
    policiales = [f for f in filas if _policial(f["puesto"])]
    aislados = [f for f in policiales if _clave(_preparar_texto(f["puesto"]) or "") == "policia"]
    for fila in aislados:
        fila["clasificacion_contextual"], fila["propuesta_contextual"], fila["justificacion"] = clasificar_policia_aislada(fila)
        fila["año"] = (fila["fecha_boe"] or "")[:4]
    guardia = [f for f in policiales if "guardia urbana" in _clave(_preparar_texto(f["puesto"]) or "")]
    pendientes = []
    for fila in policiales:
        clase, _, categoria, motivo = clasificar_policia_local(fila["puesto"])
        if clase != "SEGURA":
            pendientes.append({"oposicion_id": fila["oposicion_id"], "puesto": fila["puesto"], "puesto_normalizado": fila["puesto_normalizado"], "plazas": fila["num_plazas"], "administracion": fila["administracion"], "ambito": fila["ambito"], "tipo_entidad": fila["tipo_entidad"], "categoria": categoria, "clasificacion_textual": clase, "motivo": motivo})
    def resumen(grupo, campo):
        contador = Counter((f.get(campo) if f.get(campo) not in (None, "") else "∅") for f in grupo)
        return dict(contador.most_common())
    indeterminados = [f for f in policiales if f["ambito"] == "INDETERMINADO" and f["administracion"] == "Administración Local"]
    grupos_dudosos = defaultdict(lambda: {"filas": 0, "plazas": 0, "ejemplos": []})
    for fila in pendientes:
        clave = f"{fila['clasificacion_textual']}: {fila['motivo']}"
        grupo = grupos_dudosos[clave]; grupo["filas"] += 1; grupo["plazas"] += fila["plazas"] or 0
        if len(grupo["ejemplos"]) < 5: grupo["ejemplos"].append(fila["puesto"])
    final = _estado(ruta)
    return {"version": "fase7-paso4-v1", "generado_utc": datetime.now(timezone.utc).isoformat(), "sqlite_inicial": inicial, "sqlite_final": final,
            "universo": {"filas_policiales": len(policiales), "plazas_policiales": sum(f["num_plazas"] or 0 for f in policiales), "pendientes_textuales": len(pendientes), "plazas_pendientes": sum(f["plazas"] or 0 for f in pendientes)},
            "policia_aislada": {"filas": len(aislados), "plazas": sum(f["num_plazas"] or 0 for f in aislados), "por_ambito": resumen(aislados, "ambito"), "por_clasificacion": resumen(aislados, "clasificacion_contextual"), "detalle": aislados},
            "estatales": [f for f in aislados if f["ambito"] == "ESTATAL"],
            "locales_indeterminados": {"filas": len(indeterminados), "plazas": sum(f["num_plazas"] or 0 for f in indeterminados), "aislados": [f for f in aislados if f["ambito"] == "INDETERMINADO"], "por_puesto": resumen(indeterminados, "puesto")},
            "guardia_urbana": {"filas": len(guardia), "plazas": sum(f["num_plazas"] or 0 for f in guardia), "denominaciones": [{"puesto": p, "filas": n, "plazas": sum(f["num_plazas"] or 0 for f in guardia if f["puesto"] == p)} for p,n in Counter(f["puesto"] for f in guardia).most_common()], "administraciones": resumen(guardia, "administracion"), "municipios": resumen(guardia, "municipio"), "recomendacion": "Mantener Guardia Urbana como cuerpo/canon propio en una fase posterior; no equipararlo automáticamente a Policía Local."},
            "pendientes": pendientes, "grupos_pendientes": dict(grupos_dudosos),
            "recomendacion_contextual": "Crear en una fase posterior una capa normalizar_puesto_contextual(fila), separada del normalizador textual, con reglas auditables y evidencia explícita."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--bd", default="datos/boe.db"); parser.add_argument("--salida", default="informes/normalizacion_puestos/fase7_policia_pendientes_paso4.json")
    args = parser.parse_args(argv); informe = auditar(args.bd); salida = Path(args.salida); salida.parent.mkdir(parents=True, exist_ok=True); salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"universo": informe["universo"], "aislada": informe["policia_aislada"]["por_clasificacion"], "indeterminados": informe["locales_indeterminados"]["filas"], "guardia_urbana": informe["guardia_urbana"]["filas"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
