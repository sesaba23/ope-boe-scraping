"""Analiza puestos read-only y genera el informe previo de normalización."""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sqlite3
import unicodedata

from normalizacion_puestos import normalizar_puesto


TERMINOS_FAMILIAS = (
    "ingenier", "tecnic", "arquitect", "administrativ", "auxiliar",
    "facultativ", "inspector", "profesor", "trabajador", "educador",
)
CASOS_AMBIGUOS = (
    ("Ingeniero Industrial", "Ingeniero Técnico Industrial"),
    ("Técnico Industrial", "Ingeniero Técnico Industrial"),
    ("Ingeniero", "Ingeniero Industrial"),
    ("Arquitecto", "Arquitecto Técnico"),
)


def _clave_auxiliar(texto):
    texto = unicodedata.normalize("NFKD", texto.casefold())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip()


def analizar(ruta_bd="datos/boe.db"):
    ruta = Path(ruta_bd).resolve()
    conexion = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        total = conexion.execute("SELECT count(*) FROM oposiciones").fetchone()[0]
        nulos = conexion.execute("SELECT count(*) FROM oposiciones WHERE puesto IS NULL").fetchone()[0]
        blancos = conexion.execute(
            "SELECT count(*) FROM oposiciones WHERE puesto IS NOT NULL AND trim(puesto)=''"
        ).fetchone()[0]
        frecuencias = conexion.execute(
            "SELECT puesto, count(*) FROM oposiciones GROUP BY puesto ORDER BY count(*) DESC, puesto"
        ).fetchall()
    finally:
        conexion.close()

    normalizadas = Counter()
    originales_por_canon = defaultdict(list)
    filas_cambiadas = 0
    for puesto, cantidad in frecuencias:
        canon = normalizar_puesto(puesto)
        normalizadas[canon] += cantidad
        originales_por_canon[canon].append({"puesto": puesto, "frecuencia": cantidad})
        if canon != puesto:
            filas_cambiadas += cantidad

    patrones = {
        "barra_a": r"/\s*a\b", "barra_as": r"/\s*as\b",
        "barra_o": r"/\s*o\b", "barra_os": r"/\s*os\b",
        "parentesis_a": r"\(\s*a\s*\)", "parentesis_as": r"\(\s*as\s*\)",
        "guiones": r"[-–—]", "dobles_espacios": r" {2,}",
        "espacios_extremos": r"^\s|\s$", "puntuacion": r"[,;:.]",
    }
    ocurrencias = {
        nombre: sum(cantidad for puesto, cantidad in frecuencias if puesto and re.search(patron, puesto, re.I))
        for nombre, patron in patrones.items()
    }
    grupos_auxiliares = defaultdict(list)
    for puesto, cantidad in frecuencias:
        if puesto:
            grupos_auxiliares[_clave_auxiliar(puesto)].append(
                {"puesto": puesto, "frecuencia": cantidad}
            )
    solo_case_acentos_espacios = [
        grupo for grupo in grupos_auxiliares.values() if len(grupo) > 1
    ]
    solo_case_acentos_espacios.sort(
        key=lambda grupo: -sum(item["frecuencia"] for item in grupo)
    )
    familias = {}
    for termino in TERMINOS_FAMILIAS:
        candidatas = [
            {"puesto": puesto, "frecuencia": cantidad,
             "propuesto": normalizar_puesto(puesto)}
            for puesto, cantidad in frecuencias
            if puesto and termino in _clave_auxiliar(puesto)
        ]
        familias[termino] = candidatas[:30]
    ambiguos = [
        {
            "valores": list(par),
            "frecuencias": {
                valor: next((cantidad for puesto, cantidad in frecuencias if puesto == valor), 0)
                for valor in par
            },
            "fusionados": False,
        }
        for par in CASOS_AMBIGUOS
    ]
    fusionados = [
        {"canon": canon, "total": sum(v["frecuencia"] for v in variantes),
         "variantes": variantes}
        for canon, variantes in originales_por_canon.items() if len(variantes) > 1
    ]
    fusionados.sort(key=lambda grupo: -grupo["total"])
    canon_iti = "Ingeniero Técnico Industrial"
    variantes_iti = originales_por_canon.get(canon_iti, [])
    return {
        "ruta": str(ruta),
        "metricas": {
            "total": total, "puesto_null": nulos, "puesto_blanco": blancos,
            "puestos_distintos_antes": len(frecuencias),
            "puestos_distintos_estimados_despues": len(normalizadas),
            "filas_cambiadas_logicamente": filas_cambiadas,
            "grupos_fusionados": len(fusionados),
            "todo_mayusculas": sum(c for p, c in frecuencias if p and p.isupper()),
            "todo_minusculas": sum(c for p, c in frecuencias if p and p.islower()),
            "patrones": ocurrencias,
        },
        "top_100_antes": [{"puesto": p, "frecuencia": c} for p, c in frecuencias[:100]],
        "top_50_despues": [
            {"puesto": puesto, "frecuencia": cantidad}
            for puesto, cantidad in normalizadas.most_common(50)
        ],
        "grupos_case_acentos_espacios": solo_case_acentos_espacios[:50],
        "familias_candidatas": familias,
        "casos_ambiguos": ambiguos,
        "mayores_grupos_fusionados": fusionados[:50],
        "ingeniero_tecnico_industrial": {
            "canon": canon_iti,
            "variantes": variantes_iti,
            "total": sum(item["frecuencia"] for item in variantes_iti),
        },
    }


def _markdown(informe):
    m = informe["metricas"]
    lineas = [
        "# Análisis de normalización de puestos", "",
        "## Métricas", "",
        f"- Filas: {m['total']}", f"- NULL: {m['puesto_null']}",
        f"- Blancos: {m['puesto_blanco']}",
        f"- Distintos antes: {m['puestos_distintos_antes']}",
        f"- Distintos estimados después: {m['puestos_distintos_estimados_despues']}",
        f"- Filas con cambio lógico: {m['filas_cambiadas_logicamente']}",
        f"- Grupos fusionados: {m['grupos_fusionados']}", "",
        "## Ingeniero Técnico Industrial", "",
    ]
    iti = informe["ingeniero_tecnico_industrial"]
    for variante in iti["variantes"]:
        lineas.append(f"- {variante['puesto']}: {variante['frecuencia']} → {iti['canon']}")
    lineas += [f"- Total: {iti['total']}", "", "## Principales puestos", ""]
    lineas += [f"- {item['puesto']}: {item['frecuencia']}" for item in informe["top_100_antes"]]
    lineas += ["", "## Mayores grupos fusionados", ""]
    for grupo in informe["mayores_grupos_fusionados"][:20]:
        variantes = "; ".join(f"{v['puesto']} ({v['frecuencia']})" for v in grupo["variantes"])
        lineas.append(f"- **{grupo['canon']}** [{grupo['total']}]: {variantes}")
    lineas += ["", "## Casos ambiguos no fusionados", ""]
    for caso in informe["casos_ambiguos"]:
        lineas.append("- " + " ≠ ".join(caso["valores"]))
    return "\n".join(lineas) + "\n"


def generar(ruta_bd="datos/boe.db", directorio="informes/normalizacion_puestos"):
    informe = analizar(ruta_bd)
    destino = Path(directorio)
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "analisis_puestos.json").write_text(
        json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (destino / "analisis_puestos.md").write_text(_markdown(informe), encoding="utf-8")
    return informe


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-datos", default="datos/boe.db")
    parser.add_argument("--directorio", default="informes/normalizacion_puestos")
    args = parser.parse_args(argv)
    print(json.dumps(generar(args.base_datos, args.directorio)["metricas"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
