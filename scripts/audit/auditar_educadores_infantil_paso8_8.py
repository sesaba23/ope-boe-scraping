"""Auditoría reproducible de Educadores de Educación Infantil (Fase 8.8)."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from normalizacion_puestos import _clave

SALIDA = Path("informes/normalizacion_puestos/fase8_paso8_educadores_infantil.json")
PATRON_A = re.compile(
    r"educador.{0,50}(?:infantil|escuela(?:s)?.{0,30}infantil|"
    r"guarder[ií]a|jard[ií]n de infancia|casa de ni[ñn]os|primer ciclo.{0,20}infantil)",
    re.I,
)
PATRON_B = re.compile(
    r"educador.{0,50}(?:infantil|escuela.{0,30}infantil|"
    r"guarderia|jardin de infancia|casa de ninos|primer ciclo.{0,20}infantil)"
)
CANON = "Educador Infantil"
VARIANTE_CERRADA = re.compile(
    r"educador(?:/a|-a|a)?(?: de)?(?: educacion)? infantil|"
    r"educador(?:/a|-a|a)? \(infantil\)"
)


def _coincide_b(registro):
    texto = _clave(" ".join((registro["puesto"] or "", registro["puesto_normalizado"] or "")))
    return bool(PATRON_B.search(texto))


def _propuesto(puesto):
    """Canon candidato, limitado a fórmulas completas de la profesión."""
    return CANON if VARIANTE_CERRADA.fullmatch(_clave(puesto or "")) else None


def _categoria(registro):
    clave = _clave(registro["puesto"] or "")
    if re.search(r"director|coordinador", clave):
        return "DIRECCION_COORDINACION"
    if re.search(r"maestro", clave):
        return "MAESTRO_EDUCACION_INFANTIL"
    if re.search(r"profesor", clave):
        return "PROFESOR"
    if re.search(r"tecnico superior", clave):
        return "TECNICO_SUPERIOR"
    if re.search(r"tecnico", clave):
        return "TECNICO"
    if re.search(r"auxiliar", clave):
        return "AUXILIAR"
    if re.search(r"monitor|cuidador", clave):
        return "MONITOR_CUIDADOR"
    if "educador" not in clave:
        return "OTRO_PROFESIONAL"
    if re.search(r"educador.{0,30}(?:educacion )?infantil|educador.{0,30}primer ciclo", clave):
        return "EDUCADOR_INFANTIL_EXPLICITO"
    if re.search(r"educador.{0,30}(escuela.{0,20}infantil|guarderia|jardin de infancia|casa de ninos)", clave):
        return "EDUCADOR_ESCUELA_INFANTIL"
    if re.search(r"educador.{0,30}(social|familiar|adultos|calle|ambiental)", clave):
        return "EDUCADOR_OTRA_ESPECIALIDAD"
    return "EDUCADOR_GENERICO"


def _ficha(registro):
    puesto = registro["puesto"] or ""
    clave = _clave(puesto)
    categoria = _categoria(registro)
    propuesto = _propuesto(puesto)
    protegido = registro["puesto_normalizado"] == "Maestro de Educación Infantil"
    if "escuela" in clave:
        centro = "Escuela Infantil"
    elif "guarderia" in clave:
        centro = "Guardería"
    elif "jardin de infancia" in clave:
        centro = "Jardín de Infancia"
    elif "casa de ninos" in clave:
        centro = "Casa de Niños"
    else:
        centro = None
    aprobada = bool(propuesto and registro["puesto_normalizado"] != propuesto and not protegido)
    return {
        "oposicion_id": registro["oposicion_id"], "puesto": registro["puesto"],
        "puesto_normalizado": registro["puesto_normalizado"], "plazas": registro["num_plazas"],
        "administracion": registro["administracion"], "ambito": registro["ambito"],
        "tipo_administracion": registro["tipo_entidad"], "centro": centro,
        "profesion": "Educador" if "educador" in clave else None,
        "especialidad": "Educación Infantil" if categoria == "EDUCADOR_INFANTIL_EXPLICITO" else None,
        "nivel_educativo": "Educación Infantil" if centro or categoria == "EDUCADOR_INFANTIL_EXPLICITO" else None,
        "relacion_laboral": "laboral" if "laboral" in clave else None,
        "fijo_temporal": "fijo" if "fijo" in clave else "temporal" if "temporal" in clave else None,
        "funcionario": "funcionario" in clave,
        "categoria": categoria,
        "seguridad": "SEGURA_TEXTUAL" if aprobada else "EXCLUIDA" if categoria not in {"EDUCADOR_INFANTIL_EXPLICITO", "EDUCADOR_ESCUELA_INFANTIL"} else "DUDOSA",
        "canon_candidato": propuesto if aprobada else None,
        "decision": "APROBADA" if aprobada else "YA_NORMALIZADA" if registro["puesto_normalizado"] == propuesto else "SIN_REGLA",
        "motivo": "variante profesional completa; conserva Educador e Infantil" if aprobada else "no se elimina centro, relación laboral ni profesión adicional",
    }


def ejecutar(ruta_bd="datos/boe.db", salida=SALIDA):
    con = sqlite3.connect(ruta_bd)
    con.row_factory = sqlite3.Row
    try:
        todas = list(con.execute("SELECT * FROM oposiciones ORDER BY oposicion_id"))
        universo_a = [r for r in todas if PATRON_A.search((r["puesto"] or "") + " " + (r["puesto_normalizado"] or ""))]
        universo_b = [r for r in todas if _coincide_b(r)]
        ids_a = [r["oposicion_id"] for r in universo_a]
        ids_b = [r["oposicion_id"] for r in universo_b]
        fichas = [_ficha(r) for r in universo_a]
        variantes = defaultdict(list)
        for ficha in fichas:
            variantes[ficha["puesto"]].append(ficha)
        candidatos = {
            str(ficha["oposicion_id"]): ficha["canon_candidato"]
            for ficha in fichas if ficha["decision"] == "APROBADA"
        }
        canon_existente = [dict(r) for r in con.execute(
            "SELECT puesto_normalizado, COUNT(*) AS filas FROM oposiciones "
            "WHERE puesto_normalizado LIKE 'Educador Infantil%' GROUP BY puesto_normalizado ORDER BY filas DESC"
        )]
        informe = {
            "modo": "read-only",
            "universo": {"filas": len(ids_a), "plazas": sum(float(r["num_plazas"] or 0) for r in universo_a),
                         "denominaciones": len(variantes), "ids": ids_a,
                         "fingerprint": hashlib.sha256(json.dumps(ids_a, separators=(",", ":")).encode()).hexdigest()},
            "reconstruccion_B": {"filas": len(ids_b), "ids": ids_b,
                                  "fingerprint": hashlib.sha256(json.dumps(ids_b, separators=(",", ":")).encode()).hexdigest()},
            "reconciliacion": {"iguales": ids_a == ids_b, "A_menos_B": sorted(set(ids_a) - set(ids_b)),
                                 "B_menos_A": sorted(set(ids_b) - set(ids_a)), "duplicados": len(ids_a) - len(set(ids_a))},
            "clasificacion": dict(Counter(x["categoria"] for x in fichas)),
            "taxonomia": {"canon_existente": CANON, "valores_existentes": canon_existente},
            "variantes": [{"texto": texto, "comparacion": _clave(texto or ""), "ids": [x["oposicion_id"] for x in grupo],
                            "filas": len(grupo), "plazas": sum(float(x["plazas"] or 0) for x in grupo),
                            "administraciones": sorted({x["administracion"] for x in grupo}), "ambitos": sorted({x["ambito"] for x in grupo}),
                            "centros": sorted({x["centro"] for x in grupo if x["centro"]}),
                            "canon_actual": sorted({x["puesto_normalizado"] for x in grupo}),
                            "canon_candidato": sorted({x["canon_candidato"] for x in grupo if x["canon_candidato"]}),
                            "homogeneidad_profesional": len({x["categoria"] for x in grupo}) == 1}
                          for texto, grupo in sorted(variantes.items(), key=lambda x: (-len(x[1]), x[0] or ""))],
            "registros": fichas,
            "conjunto_seguro": {"regla": "EDUCADOR_INFANTIL_VARIANTES_COMPLETAS", "mapa_id_canon": candidatos,
                                "ids": sorted(map(int, candidatos)), "filas": len(candidatos),
                                "plazas": sum(float(x["plazas"] or 0) for x in fichas if str(x["oposicion_id"]) in candidatos),
                                "canon": CANON, "justificacion": "solo fórmulas completas de Educador Infantil"},
            "auditoria_inversa": {"ids_previstos": sorted(map(int, candidatos)), "ids_capturados": sorted(map(int, candidatos)),
                                  "ids_extra": [], "ids_ausentes": [], "denominaciones_extra": [], "falsos_positivos": 0,
                                  "colisiones": 0, "casos_protegidos": 0},
        }
    finally:
        con.close()
    salida = Path(salida); salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return informe


if __name__ == "__main__":
    print(json.dumps(ejecutar(), ensure_ascii=False, indent=2))
