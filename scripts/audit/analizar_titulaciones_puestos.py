"""Análisis read-only de titulaciones técnicas contenidas en Puesto."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata

from normalizacion_puestos import normalizar_puesto


FAMILIAS = {
    "Ingeniero Técnico Industrial": ("ingenier", "tecnic", "indust"),
    "Ingeniero Técnico de Obras Públicas": ("ingenier", "tecnic", "obras publicas"),
    "Ingeniero Técnico Agrícola": ("ingenier", "tecnic", "agricol"),
    "Ingeniero Técnico Forestal": ("ingenier", "tecnic", "forestal"),
    "Ingeniero Técnico de Minas": ("ingenier", "tecnic", "minas"),
    "Ingeniero Técnico de Telecomunicación": ("ingenier", "tecnic", "telecomunic"),
    "Ingeniero Técnico en Informática": ("ingenier", "tecnic", "informat"),
    "Ingeniero Técnico Aeronáutico": ("ingenier", "tecnic", "aeronaut"),
    "Ingeniero Técnico Topógrafo": ("ingenier", "tecnic", "topograf"),
    "Ingeniero Técnico Civil": ("ingenier", "tecnic", "civil"),
}

NUCLEOS = {
    "Ingeniero Técnico Industrial": r"\bingenieros? tecnicos? industrial(?:es)?\b",
    "Ingeniero Técnico de Obras Públicas": r"\bingenieros? tecnicos? de obras publicas\b",
    "Ingeniero Técnico Agrícola": r"\bingenieros? tecnicos? agricolas?\b",
    "Ingeniero Técnico Forestal": r"\bingenieros? tecnicos? forestal(?:es)?\b",
    "Ingeniero Técnico de Minas": r"\bingenieros? tecnicos? de minas\b",
    "Ingeniero Técnico de Telecomunicación": r"\bingenieros? tecnicos? (?:de )?telecomunicaciones?\b",
    "Ingeniero Técnico en Informática": r"\bingenieros? tecnicos? (?:en |de )?informatica\b",
    "Ingeniero Técnico Aeronáutico": r"\bingenieros? tecnicos? aeronauticos?\b",
    "Ingeniero Técnico Topógrafo": r"\bingenieros? tecnicos? topografos?\b",
    "Ingeniero Técnico Civil": r"\bingenieros? tecnicos? civiles?\b",
}

MARCADORES_COMPUESTOS = re.compile(
    r"\b(?:o|y|y/o|equivalente|grado en)\b|/(?:arquitect|aparejador|ingenier)|,\s*ingenier",
    re.I,
)
ESPECIALIDAD_INDUSTRIAL = re.compile(
    r"electric|mecan|quimic|prevencion|ruidos|instalacion|equipamiento|alumbrado|"
    r"obras y servicios|rama", re.I,
)
PREFIJO_ADMINISTRATIVO = re.compile(
    r"^(?:tmae|personal|consolidacion de trabajo temporal de|"
    r"tecnico(?: de)? grado medio|tecnico medio(?: de administracion especial)?|"
    r"tecnico medio administracion especial|tecnico de grado medio)$"
)
SUFIJO_ADMINISTRATIVO = re.compile(
    r"^(?:"
    r"de (?:la )?(?:plantilla|escala|subescala|esta universidad)\b|"
    r"perteneciente(?:s|/s)? a la escala\b|encuadradas en la escala\b|"
    r"como personal funcionario\b|para el ayuntamiento\b|en la concejalia\b|"
    r"a (?:jornada completa|tiempo parcial)\b|del ayuntamiento\b|"
    r"\(?(?:oep|personal funcionario|concurso oposicion libre|grupo/subgrupo|subgrupo)\b"
    r")"
)


def _clave(texto):
    texto = unicodedata.normalize("NFKD", texto.casefold())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", texto).strip()


def _sha256(ruta):
    digest = hashlib.sha256()
    with Path(ruta).open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def estado_base(ruta_bd):
    ruta = Path(ruta_bd).resolve()
    stat = ruta.stat()
    conexion = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        metadata = dict(conexion.execute("SELECT clave, valor FROM metadata"))
        conteos = {
            tabla: conexion.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0]
            for tabla in ("publicaciones", "oposiciones", "busquedas", "cobertura", "log_errores")
        }
        integridad = [fila[0] for fila in conexion.execute("PRAGMA integrity_check")]
        fk = conexion.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        conexion.close()
    return {
        "sha256": _sha256(ruta), "tamano": stat.st_size, "mtime_ns": stat.st_mtime_ns,
        "schema_version": metadata.get("schema_version"),
        "data_version": metadata.get("data_version"), "conteos": conteos,
        "integrity_check": integridad, "foreign_key_check": fk,
    }


def _es_candidato(texto, raices):
    clave = _clave(texto)
    return all(re.search(raiz, clave) for raiz in raices)


def _ruido_administrativo_seguro(clave, coincidencia):
    prefijo = clave[:coincidencia.start()].strip(" ()-")
    sufijo = clave[coincidencia.end():].strip(" -")
    prefijo_seguro = not prefijo or bool(PREFIJO_ADMINISTRATIVO.fullmatch(prefijo))
    sufijo_seguro = not sufijo or bool(SUFIJO_ADMINISTRATIVO.match(sufijo))
    return prefijo_seguro and sufijo_seguro


def _clasificar(texto, canon):
    clave = _clave(texto)
    actual = normalizar_puesto(texto)
    clave_actual = _clave(actual)
    nucleo = NUCLEOS[canon]
    if canon == "Ingeniero Técnico Industrial" and re.search(
        r"\bingenieri[oa]? tecnico industrial\b", clave
    ):
        return "ERRATA_PROBABLE", "Errata aparente en Ingeniero", canon
    if canon == "Ingeniero Técnico Industrial" and re.search(
        r"\bingenieros? tecnicos? de industria\b", clave
    ):
        return "AMBIGUO", "Variante 'de Industria': requiere equivalencia explícita", None
    if actual == canon:
        return "SEGURO", "Ya coincide con el canon actual", canon
    if canon == "Ingeniero Técnico Industrial" and re.search(
        r"ingeniera/ingeniero tecnica/tecnico industrial|"
        r"ingeniero o ingeniera tecnica industrial",
        clave,
    ):
        return "SEGURO", "Variación explícita de género del mismo núcleo", canon
    if MARCADORES_COMPUESTOS.search(clave):
        return "AMBIGUO", "Incluye titulaciones alternativas o una denominación compuesta", None
    if canon == "Ingeniero Técnico Industrial" and ESPECIALIDAD_INDUSTRIAL.search(clave):
        return "AMBIGUO", "Contiene especialidad o función que no debe descartarse", None
    coincidencia = re.search(nucleo, clave_actual)
    if not coincidencia:
        if re.search(r"ingenier[oa]? tecnico", clave_actual):
            return "AMBIGUO", "Orden, preposición o morfología no cubierta con seguridad", None
        return "NO_EQUIVALENTE", "Raíces relacionadas sin el núcleo profesional canónico", None
    if _ruido_administrativo_seguro(clave_actual, coincidencia):
        return "SEGURO", "Núcleo inequívoco con ruido administrativo acotado", canon
    if coincidencia.start() == 0 and coincidencia.end() == len(clave_actual):
        return "SEGURO", "Núcleo exacto, incluida flexión de número", canon
    return "AMBIGUO", "El texto sobrante no pertenece a la lista blanca administrativa", None


def analizar(ruta_bd="datos/boe.db"):
    ruta = Path(ruta_bd).resolve()
    estado_antes = estado_base(ruta)
    conexion = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        columnas = {fila[1].casefold() for fila in conexion.execute("PRAGMA table_info(oposiciones)")}
        tiene_normalizado = "puesto_normalizado" in columnas
        if tiene_normalizado:
            filas = conexion.execute(
                "SELECT puesto, puesto_normalizado, count(*) FROM oposiciones "
                "GROUP BY puesto, puesto_normalizado ORDER BY count(*) DESC, puesto"
            ).fetchall()
            frecuencias = [(puesto, cantidad) for puesto, _, cantidad in filas]
            actual_por_original = {puesto: normalizado for puesto, normalizado, _ in filas}
        else:
            frecuencias = conexion.execute(
                "SELECT puesto, count(*) FROM oposiciones GROUP BY puesto ORDER BY count(*) DESC, puesto"
            ).fetchall()
            actual_por_original = {puesto: normalizar_puesto(puesto) for puesto, _ in frecuencias}
    finally:
        conexion.close()
    actual = Counter()
    simulado = Counter()
    for puesto, cantidad in frecuencias:
        actual[actual_por_original[puesto]] += cantidad
        simulado[actual_por_original[puesto]] += cantidad

    familias = {}
    cambios_seguros = {}
    for canon, raices in FAMILIAS.items():
        candidatos = []
        for puesto, frecuencia in frecuencias:
            if not _es_candidato(puesto, raices):
                continue
            clasificacion, motivo, propuesto = _clasificar(puesto, canon)
            candidatos.append({
                "puesto": puesto, "puesto_normalizado_actual": actual_por_original[puesto],
                "frecuencia": frecuencia, "clasificacion": clasificacion,
                "motivo": motivo, "canon_propuesto": propuesto,
            })
            if clasificacion == "SEGURO" and propuesto != actual_por_original[puesto]:
                cambios_seguros[puesto] = propuesto
        resumen = Counter()
        for candidato in candidatos:
            resumen[candidato["clasificacion"]] += candidato["frecuencia"]
        familias[canon] = {
            "denominaciones_distintas": len(candidatos),
            "filas_totales": sum(c["frecuencia"] for c in candidatos),
            "ya_correctamente_normalizadas": sum(
                c["frecuencia"] for c in candidatos
                if c["puesto_normalizado_actual"] == canon
            ),
            "adicionales_seguras": sum(
                c["frecuencia"] for c in candidatos
                if c["clasificacion"] == "SEGURO" and c["puesto_normalizado_actual"] != canon
            ),
            "por_clasificacion": dict(resumen),
            "candidatos": candidatos,
        }
    for puesto, cantidad in frecuencias:
        propuesto = cambios_seguros.get(puesto)
        if propuesto:
            simulado[actual_por_original[puesto]] -= cantidad
            if not simulado[actual_por_original[puesto]]:
                del simulado[actual_por_original[puesto]]
            simulado[propuesto] += cantidad
    canon_iti = "Ingeniero Técnico Industrial"
    grupos_antes = len(actual)
    grupos_despues = len(simulado)
    estado_despues = estado_base(ruta)
    if estado_antes != estado_despues:
        raise RuntimeError("La base cambió durante el análisis; no se genera un informe inconsistente")
    return {
        "estado_base": estado_antes,
        "advertencia_schema": (
            "Se leyó Puesto_normalizado de la base v3; la Fase 2 se simuló solo en memoria."
            if tiene_normalizado else
            "La base no contiene Puesto_normalizado; el estado actual se simuló en memoria."
        ),
        "metodologia": {
            "descubrimiento": "Raíces morfológicas sin acentos; clasificación posterior individual",
            "sin_fuzzy": True, "conexion": "SQLite URI mode=ro",
        },
        "familias": familias,
        "ingeniero_tecnico_de_industria": [
            candidato for candidato in familias[canon_iti]["candidatos"]
            if "de industria" in _clave(candidato["puesto"])
        ],
        "simulacion": {
            "puestos_normalizados_distintos_actual": grupos_antes,
            "estimacion_despues": grupos_despues,
            "filas_adicionales_normalizadas": sum(
                frecuencia for puesto, frecuencia in frecuencias if puesto in cambios_seguros
            ),
            "grupos_adicionales_fusionados": grupos_antes - grupos_despues,
            "iti_frecuencia_actual": actual[canon_iti],
            "iti_frecuencia_simulada": simulado[canon_iti],
            "iti_posicion_actual": next(i for i, (p, _) in enumerate(actual.most_common(), 1) if p == canon_iti),
            "iti_posicion_simulada": next(i for i, (p, _) in enumerate(simulado.most_common(), 1) if p == canon_iti),
            "top_50_actual": [{"puesto": p, "frecuencia": n} for p, n in actual.most_common(50)],
            "top_50_simulado": [{"puesto": p, "frecuencia": n} for p, n in simulado.most_common(50)],
        },
        "reglas_propuestas": {
            "alta": [
                "Núcleo consecutivo exacto singular/plural con solo prefijo/sufijo administrativo en lista blanca",
                "Formas completas de género Ingeniera/Ingeniero Técnica/Técnico",
            ],
            "media_baja_no_automaticas": [
                "Ingeniero Técnico de Industria",
                "Cambios de orden o tokens separados",
                "Equivalencias con Grado en Ingeniería",
                "Denominaciones con especialidad o varias titulaciones",
                "Erratas sin entrada explícita de catálogo",
            ],
        },
    }


def _markdown(informe):
    s = informe["simulacion"]
    lineas = [
        "# Fase 2: titulaciones contenidas", "", f"> {informe['advertencia_schema']}", "",
        "## Simulación segura", "",
        f"- Distintos actuales: {s['puestos_normalizados_distintos_actual']}",
        f"- Estimación: {s['estimacion_despues']}",
        f"- Filas adicionales: {s['filas_adicionales_normalizadas']}",
        f"- Grupos adicionales fusionados: {s['grupos_adicionales_fusionados']}",
        f"- Ingeniero Técnico Industrial: {s['iti_frecuencia_actual']} → {s['iti_frecuencia_simulada']}",
        "", "## Familias", "",
    ]
    for canon, familia in sorted(
        informe["familias"].items(), key=lambda item: -item[1]["adicionales_seguras"]
    ):
        lineas += [
            f"### {canon}", "",
            f"- Denominaciones: {familia['denominaciones_distintas']}",
            f"- Filas: {familia['filas_totales']}",
            f"- Ya normalizadas: {familia['ya_correctamente_normalizadas']}",
            f"- Adicionales seguras: {familia['adicionales_seguras']}", "",
            "| Frecuencia | Clasificación | Original | Actual | Motivo |", "|---:|---|---|---|---|",
        ]
        for c in familia["candidatos"]:
            lineas.append(
                f"| {c['frecuencia']} | {c['clasificacion']} | {c['puesto']} | "
                f"{c['puesto_normalizado_actual']} | {c['motivo']} |"
            )
        lineas.append("")
    lineas += ["## Top 50 actual", ""]
    lineas += [f"- {x['puesto']}: {x['frecuencia']}" for x in s["top_50_actual"]]
    lineas += ["", "## Top 50 simulado", ""]
    lineas += [f"- {x['puesto']}: {x['frecuencia']}" for x in s["top_50_simulado"]]
    return "\n".join(lineas) + "\n"


def generar(ruta_bd="datos/boe.db", directorio="informes/normalizacion_puestos"):
    informe = analizar(ruta_bd)
    destino = Path(directorio); destino.mkdir(parents=True, exist_ok=True)
    (destino / "fase2_titulaciones.json").write_text(
        json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (destino / "fase2_titulaciones.md").write_text(_markdown(informe), encoding="utf-8")
    return informe


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-datos", default="datos/boe.db")
    parser.add_argument("--directorio", default="informes/normalizacion_puestos")
    args = parser.parse_args(argv)
    print(json.dumps(generar(args.base_datos, args.directorio)["simulacion"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
