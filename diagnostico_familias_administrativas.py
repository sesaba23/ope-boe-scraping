"""Diagnóstico de familias administrativas no cubiertas; no modifica datos productivos."""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
import re

from diagnostico_administraciones_historicas import cargar_historicos, diagnosticar


FAMILIAS_DESCUBIERTAS = (
    ("MINISTERIO", r"\bministerio\s+(?:de|del|para)\b", "MEDIA"),
    ("CONSEJERIA", r"\bconsejer[ií]a\s+(?:de|del)\b", "MEDIA"),
    ("SERVICIO_SALUD", r"\bservicio\b.*\bsalud\b", "MEDIA"),
    ("ORGANISMO_AUTONOMO", r"\borganismo\s+aut[oó]nomo\b", "MEDIA"),
    ("ADMINISTRACION_GENERAL_ESTADO", r"\badministraci[oó]n\s+general\s+del\s+estado\b", "MEDIA"),
    ("GOBIERNO", r"\bgobierno\s+(?:de|del)\b", "MEDIA"),
    ("JUNTA", r"\bjunta\s+(?:de|del)\b", "MEDIA"),
    ("GENERALITAT", r"\bgeneralitat\b", "MEDIA"),
    ("COMUNIDAD_AUTONOMA", r"\bcomunidad\s+(?:aut[oó]noma|foral)\b", "MEDIA"),
    ("CABILDO", r"\bcabildo\b", "ALTA"),
    ("CONSEJO_INSULAR", r"\b(?:consejo|consell)\s+insular\b", "ALTA"),
    ("MANCOMUNIDAD", r"\bmancomunidad\b", "BAJA"),
    ("CONSORCIO", r"\bconsorcio\b", "BAJA"),
    ("AGENCIA", r"\bagencia\b", "BAJA"),
    ("INSTITUTO", r"\binstituto\b", "BAJA"),
    ("EMPRESA_ENTIDAD_PUBLICA", r"\b(?:empresa|entidad)\s+p[uú]blica\b", "BAJA"),
    ("ADMINISTRACION_LOCAL_GENERICA", r"^administraci[oó]n\s+local$", "BAJA"),
)


def clasificar_familia(texto):
    texto = str(texto or "").strip()
    for nombre, patron, sede in FAMILIAS_DESCUBIERTAS:
        if re.search(patron, texto, flags=re.IGNORECASE):
            return nombre, sede
    return "SIN_CLASIFICAR", "BAJA"


def diagnosticar_familias(excel="BOE-oposiciones.xlsx"):
    publicaciones, oposiciones = cargar_historicos(excel)
    base = diagnosticar(excel, publicaciones=publicaciones, oposiciones=oposiciones)
    detectados_titulo = {x["Publicacion_ID"] for x in base["resultados"] if x["metodo_fuente"].startswith("TITULO_BOE")}
    detectados_admin = {(x["Publicacion_ID"], x["administracion_detectada"])
                         for x in base["resultados"] if x["metodo_fuente"].startswith("ADMINISTRACION_EXISTENTE")}
    titulos = publicaciones.set_index("Publicacion_ID")["Titulo_original"].to_dict()
    grupos, ejemplos, admins, publicaciones_familia = defaultdict(int), defaultdict(list), defaultdict(Counter), defaultdict(set)
    fuente = Counter()
    for fila in oposiciones.to_dict(orient="records"):
        publicacion_id, administracion = fila.get("Publicacion_ID"), str(fila.get("Administración") or "")
        cubierta = publicacion_id in detectados_titulo or (publicacion_id, administracion) in detectados_admin
        if cubierta:
            continue
        titulo = titulos.get(publicacion_id)
        texto_titulo = titulo if isinstance(titulo, str) and titulo.strip() else ""
        familia_titulo, sede_titulo = clasificar_familia(texto_titulo)
        if familia_titulo != "SIN_CLASIFICAR":
            familia, sede, origen, texto_ejemplo = familia_titulo, sede_titulo, "TITULO_BOE", texto_titulo
        else:
            familia, sede = clasificar_familia(administracion)
            origen, texto_ejemplo = "ADMINISTRACION_EXISTENTE", administracion
        grupos[(familia, sede)] += 1
        publicaciones_familia[familia].add(publicacion_id)
        admins[familia][administracion] += 1
        fuente[origen] += 1
        if len(ejemplos[familia]) < 3:
            ejemplos[familia].append({"Publicacion_ID": publicacion_id, "titulo": texto_titulo,
                                      "administracion": administracion, "origen": origen,
                                      "texto_clasificado": texto_ejemplo})
    total = len(oposiciones)
    ranking, acumulado = [], base["resumen"]["filas_potencialmente_geolocalizables"]
    for (familia, sede), filas in sorted(grupos.items(), key=lambda x: -x[1]):
        acumulado += filas
        ranking.append({"familia": familia, "publicaciones": len(publicaciones_familia[familia]), "filas": filas,
                        "porcentaje_filas": round(100 * filas / total, 2),
                        "porcentaje_acumulado_con_cobertura_actual": round(100 * acumulado / total, 2),
                        "sede_estimable": sede, "ejemplos": ejemplos[familia],
                        "administraciones_frecuentes": [{"administracion": a, "filas": n} for a, n in admins[familia].most_common(10)]})
    # Publicaciones no conserva organismo/departamento/metadatos BOE: solo los ocho campos del esquema.
    campos_publicaciones = list(publicaciones.columns)
    metadatos = [c for c in campos_publicaciones if any(x in c.casefold() for x in ("organismo", "departamento", "metadato"))]
    recomendadas = [x["familia"] for x in ranking if x["familia"] not in {"SIN_CLASIFICAR", "ADMINISTRACION_LOCAL_GENERICA"}][:10]
    return {"resumen": {"filas_oposiciones": total, "filas_cubiertas_actualmente": base["resumen"]["filas_potencialmente_geolocalizables"],
                         "filas_no_cubiertas": total - base["resumen"]["filas_potencialmente_geolocalizables"],
                         "porcentaje_titulo_disponible": round(100 * base["resumen"]["titulos_disponibles"] / base["resumen"]["publicaciones_analizadas"], 2),
                         "filas_clasificadas_por_titulo": fuente["TITULO_BOE"],
                         "filas_clasificadas_por_administracion_existente": fuente["ADMINISTRACION_EXISTENTE"],
                         "campos_metadatos_boe_en_publicaciones": metadatos,
                         "filas_adicionales_por_metadatos_boe": 0,
                         "recomendadas": recomendadas}, "ranking": ranking}


def escribir_informes(datos, directorio="informes/diagnostico_administraciones_historicas"):
    destino = Path(directorio); destino.mkdir(parents=True, exist_ok=True)
    (destino / "diagnostico_familias_administrativas.json").write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    r = datos["resumen"]
    lineas = ["# Diagnóstico de familias administrativas", "", "## Resumen", ""]
    lineas += [f"- {k.replace('_', ' ')}: {v}" for k, v in r.items() if k != "recomendadas"]
    lineas += ["", "## Ranking", "", "| Familia | Publicaciones | Filas | % | % acumulado | Sede |", "|---|---:|---:|---:|---:|---|"]
    lineas += [f"| {x['familia']} | {x['publicaciones']} | {x['filas']} | {x['porcentaje_filas']} | {x['porcentaje_acumulado_con_cobertura_actual']} | {x['sede_estimable']} |" for x in datos["ranking"]]
    lineas += ["", "## Recomendación", "", "- " + ", ".join(r["recomendadas"])]
    (destino / "diagnostico_familias_administrativas.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--excel", default="BOE-oposiciones.xlsx")
    parser.add_argument("--salida", default="informes/diagnostico_administraciones_historicas")
    args = parser.parse_args(argv)
    datos = diagnosticar_familias(args.excel)
    escribir_informes(datos, args.salida)
    print(json.dumps(datos["resumen"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
