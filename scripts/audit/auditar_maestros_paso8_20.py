"""Inventario y propuestas de Maestros, sin aplicar reglas ni escribir SQLite.

Ejecutar desde la raíz: .venv/bin/python -m scripts.audit.auditar_maestros_paso8_20
Los IDs históricos sólo sirven para reconciliar; nunca seleccionan candidatos.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import normalizacion_puestos as textual
from normalizacion_contextual_puestos import normalizar_puesto_efectivo
from scripts.audit import auditar_criterio_dry_run_global_paso8_19 as paso19

ROOT = Path(__file__).resolve().parents[2]
INFORMES = ROOT / "informes/normalizacion_puestos"
SALIDA = INFORMES / "fase8_paso20_maestros.json"
PRECHECK = INFORMES / "fase8_paso20_precheck.json"
CAMPOS_UNIVERSO = ("puesto", "puesto_normalizado", "escala", "subescala", "clase", "titulo_original")
CONTEXTO = ("administracion", "ambito", "tipo_entidad", "escala", "subescala", "sistema", "municipio", "provincia")
MAESTROS = re.compile(r"\bmaestr(?:o|a|os|as)\b")
CODIGO_CUERPO = re.compile(r"\bcodigo\s+597\b")
CUERPO = re.compile(r"\bcuerpos? de maestros\b|\bcodigo\s+597\b")
OFICIOS = re.compile(
    r"industrial|\bobras?\b|mantenimiento|limpieza|jardiner|\bjardines\b|arsenal|capataz|conductor|"
    r"cementerio|albanil|fontan|electric|carpinter|herrero|montes|\bzoo\b|canter|"
    r"maquinista|alumbrado|potabiliz|compost|inspector|oficios|villa|herreria|"
    r"corrector|servicios|brigada|polideportivo|deportivas|carreteras|conserje|"
    r"recogida|ganader|vivero|pintor|cerraj|encargado|guardallaves|parque movil|"
    r"encuadernador|fotocomposicion|ribera"
)
CENTRO_INFANTIL = re.compile(
    r"escuela.*infantil|guarderia|jardin de infancia|bressol|llar|casa de ninos|"
    r"centro infantil|centro de educacion infantil|\bcei\b|\bpai\b|punto de atencion a la infancia"
)
COMPUESTA = re.compile(r"director|direccion|educador|\btecnic|\bauxiliar|\bprofesor|"
                      r"\bmonitor|\bjefe|\btraductor|\bomic\b|\by (?:una|cinco|de agente)\b")
LABORAL = re.compile(r"laboral|plantilla|jornada|tiempo parcial|personal fijo|funcionario interino|"
                    r"administracion especial|grupo |subgrupo|primer ciclo|0 ?[-a] ?3|municipal")
ESPECIALIDADES = (
    ("Educación Infantil", r"educacion infantil|eduacion infantil|especialidad infantil"),
    ("Educación Primaria", r"\bprimaria\b"),
    ("Pedagogía Terapéutica", r"pedagogia terapeutica"),
    ("Audición y Lenguaje", r"audicion y lenguaje"),
    ("Educación Física", r"educacion fisica"),
    ("Música", r"musica|musical|conservatorio|banda de"),
    ("Lengua Extranjera", r"lengua extranjera"),
    ("Inglés", r"\bingles\b"),
    ("Francés", r"\bfrances\b"),
    ("Educación Especial", r"educacion especial"),
    ("Educación de Adultos", r"adultos|adultas|\bepa\b"),
    ("Formación Profesional", r"formacion profesional"),
    ("Formación y Orientación Laboral", r"formacion y orientacion laboral"),
    ("Artes Plásticas y Diseño", r"artes plasticas y diseno"),
    ("Pintura", r"pintura"), ("Cerámica", r"ceramica"),
    ("Informática", r"informatica|informatico"),
    ("Piano", r"\bpiano\b"), ("Lenguaje Musical", r"lenguaje musical"),
    ("Guitarra", r"guitarra"), ("Violín", r"violin"),
    ("Violoncelo", r"violoncelo|violonchelo"), ("Saxofón", r"saxofon"),
    ("Acordeón diatónico", r"acordeon diatonico"), ("Gaita", r"gaita"),
    ("Tenora y tible", r"tenora y tible"), ("Bolillos", r"bolillos"),
    ("Bordado", r"bordado"), ("Telares y tejido", r"telares y tejido"),
    ("Reciclaje y papel artesanal", r"reciclaje y papel artesanal"),
)
ESTADOS = ("ya_normalizado_regla_previa", "pendiente_potencial", "especialidad_significativa",
           "denominacion_compuesta", "laboral_local_contextual", "dudoso", "fuera_de_familia")

# Hipótesis de auditoría sobre literales completos observados. No son reglas
# del normalizador: se muestran como propuestas y nunca sustituyen la salida.
HIPOTESIS_A = {
    "Maestro o Maestra de Educación Infantil": ("genero_infantil_completo", "Maestro de Educación Infantil"),
    "Maestro/maestra en educación infantil": ("genero_infantil_completo", "Maestro de Educación Infantil"),
    "Maestro-a de Educación Infantil": ("genero_infantil_completo", "Maestro de Educación Infantil"),
    "funcionarios docentes para el Cuerpo de Maestros": ("cuerpo_maestros_para", "Maestros"),
}


def sha(ruta):
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def estado_git():
    comandos = {"rama": ["branch", "--show-current"], "head": ["rev-parse", "HEAD"],
                "origin_main": ["rev-parse", "origin/main"], "status_short": ["status", "--short"],
                "diff_stat": ["diff", "--stat"]}
    datos = {k: subprocess.check_output(["git", *args], cwd=ROOT, text=True) for k, args in comandos.items()}
    datos["diff_sha256"] = hashlib.sha256(subprocess.check_output(["git", "diff", "--binary"], cwd=ROOT)).hexdigest()
    return datos


def fuentes_candidato(fila):
    return [k for k in CAMPOS_UNIVERSO if MAESTROS.search(textual._clave(fila.get(k) or ""))
            or CODIGO_CUERPO.search(textual._clave(fila.get(k) or ""))]


def candidato_por_tokens(fila):
    """Segunda reconstrucción exacta independiente de la expresión Maestros."""
    for campo in CAMPOS_UNIVERSO:
        tokens = re.findall(r"[a-z0-9]+", textual._clave(fila.get(campo) or ""))
        if {"maestro", "maestra", "maestros", "maestras"}.intersection(tokens):
            return True
        if any(a == "codigo" and b == "597" for a, b in zip(tokens, tokens[1:])):
            return True
    return False


def resumen(filas):
    return {"filas": len(filas), "plazas": sum(float(r["plazas"] or 0) for r in filas),
            "ids": sorted(r["oposicion_id"] for r in filas),
            "denominaciones": len({r["puesto"] for r in filas}),
            "administraciones": sorted({r.get("administracion") or "" for r in filas}),
            "anios": sorted({(r.get("fecha_boe") or "")[:4] for r in filas}),
            "provincias": sorted({r.get("provincia") or "" for r in filas})}


def agrupar(filas, campo):
    grupos = defaultdict(list)
    for fila in filas:
        grupos[fila[campo]].append(fila)
    return {k: resumen(v) for k, v in sorted(grupos.items())}


def _regla_previa(puesto, salida):
    for nombre in ("_normalizar_docencia_musical", "_normalizar_docencia_artistica_no_musical",
                   "_normalizar_cuerpo_maestros", "_normalizar_maestro_educacion_infantil"):
        resultado = getattr(textual, nombre)(textual._preparar_texto(puesto) or "")
        if resultado is not None and resultado == salida:
            return nombre
    return None


def ficha(fila):
    r = dict(fila)
    puesto = r["puesto"] or ""
    clave = textual._clave(puesto)
    efectivo = normalizar_puesto_efectivo(puesto, **{k: r.get(k) for k in CONTEXTO})
    regla = _regla_previa(puesto, efectivo.textual)
    res = {k: r.get(k) for k in ("oposicion_id", "puesto", "puesto_normalizado", "administracion",
           "administracion_normalizada", "ambito", "tipo_entidad", "fecha_boe", "provincia", "municipio",
           "escala", "subescala", "clase", "sistema", "publicacion_id", "titulo_original", "enlace")}
    res.update(plazas=r["num_plazas"], fuentes_universo=fuentes_candidato(r),
               textual=efectivo.textual, efectivo=efectivo.normalizado,
               regla_contextual=efectivo.regla, evidencia_contextual=list(efectivo.evidencia),
               regla_previa=regla, canon_propuesto=None, conjunto_propuesto=None)
    especialidades = [nombre for nombre, patron in ESPECIALIDADES if re.search(patron, clave)]
    res["especialidades"] = especialidades
    res["descriptor_original_integro"] = puesto
    res["forma_genero_numero"] = (MAESTROS.search(clave).group() if MAESTROS.search(clave) else "contextual")
    res["plural_origen"] = ("cuerpo_o_codigo_explicito" if CUERPO.search(clave) else
                            "categoria_local_sin_prueba_de_cuerpo" if r.get("ambito") == "LOCAL" else
                            "no_determinable_solo_con_campos_disponibles")
    res["especialidades_ausentes_en_salida_actual"] = [nombre for nombre, patron in ESPECIALIDADES
        if nombre in especialidades and not re.search(patron, textual._clave(efectivo.textual or ""))]
    if CUERPO.search(clave):
        micro = "cuerpo_docente_explicito"
    elif re.search(r"taller|centro ocupacional", clave):
        micro = "taller_artistico_ocupacional" if re.search(r"ocupacional|artes plasticas|ceramica|bolillos|bordado|social|prelaboral|artesanal", clave) else "taller_sin_docencia_acreditada"
    elif OFICIOS.search(clave):
        micro = "oficios_no_docentes"
    elif COMPUESTA.search(clave):
        micro = "funciones_docentes_compuestas"
    elif re.search(r"musica|musical|piano|guitarra|violin|saxofon|acordeon|gaita|tenora|tible", clave):
        micro = "musica"
    elif re.search(r"arte|pintura|ceramica|telares", clave):
        micro = "artes_no_musicales"
    elif CENTRO_INFANTIL.search(clave):
        micro = "centros_infantiles"
    elif "infantil" in clave:
        micro = "educacion_infantil"
    elif re.search(r"adultos|adultas|\bepa\b", clave):
        micro = "educacion_adultos"
    elif especialidades:
        micro = "otras_especialidades_docentes"
    elif re.fullmatch(r"maestr(?:o|a|os|as)(?:/(?:o|a|os|as))?", clave):
        micro = "maestro_generico"
    else:
        micro = "otros_contextos_sin_equivalencia"
    res["microfamilia"] = micro
    reproducido = bool(regla and r["puesto_normalizado"] == efectivo.textual == efectivo.normalizado)
    # Una coincidencia de una regla anterior no certifica su significado.
    # Ejemplo observado: Fotocomposición activa la búsqueda musical Composición.
    normalizado = reproducido and micro != "oficios_no_docentes"
    res["alerta_canon_previo_ajeno_a_profesion"] = reproducido and not normalizado
    res["canon_validado_pipeline_previo"] = normalizado
    res["acredita_cuerpo_docente"] = bool(CUERPO.search(clave))
    if normalizado:
        estado, seguridad = "ya_normalizado_regla_previa", None
        motivo = "canon reproducido por regla previa; no se propone otra normalización"
        if micro == "maestro_generico":
            motivo += "; la absorción previa de Maestro no acredita pertenencia al cuerpo docente"
    elif micro == "oficios_no_docentes":
        estado, seguridad = "fuera_de_familia", "D"
        motivo = "oficio profesional distinto de la familia docente; no reducir a Maestro/Maestros"
        if reproducido:
            motivo += "; canon musical preexistente reproducible pero incompatible con el oficio: revisar por separado"
    elif "puesto" not in res["fuentes_universo"]:
        estado, seguridad = "dudoso", "C"
        motivo = "mención en canon/contexto: no demuestra por sí sola la categoría de esta plaza"
    elif puesto in HIPOTESIS_A and r["puesto_normalizado"] == efectivo.normalizado:
        conjunto, canon = HIPOTESIS_A[puesto]
        if conjunto == "cuerpo_maestros_para" and r.get("ambito") not in {"AUTONOMICO", "ESTATAL"}:
            estado, seguridad = "dudoso", "C"
            motivo = "formulación de cuerpo con contexto no estatal/autonómico: revisar coherencia"
        else:
            estado, seguridad = "pendiente_potencial", "A"
            motivo = ("denominación completa, singular y de la misma especialidad; sólo varía la expresión explícita de género"
                      if conjunto == "genero_infantil_completo" else
                      "cuerpo de Maestros explícito; únicamente cambia el enlace para/del, sin especialidad ni otra categoría")
            res.update(canon_propuesto=canon, conjunto_propuesto=conjunto)
    elif micro == "funciones_docentes_compuestas" or COMPUESTA.search(clave):
        estado, seguridad = "denominacion_compuesta", "D"
        motivo = "preservar funciones, profesiones o responsabilidades combinadas; no absorber en un canon simple"
    elif micro == "cuerpo_docente_explicito":
        estado, seguridad = "pendiente_potencial", "C"
        motivo = "cuerpo explícito con cifras sin explicar, localización o texto truncado; requiere revisar el documento original"
    elif re.fullmatch(r"maestr(?:as|os)(?:/(?:as|os))? (?:de )?educacion infantil", clave):
        estado, seguridad = "pendiente_potencial", "B"
        motivo = "misma especialidad aparente; plural/categoría agregada pendiente de validación, sin singularizar"
    elif puesto == "Maestro/a (Educación Infantil)":
        estado, seguridad = "pendiente_potencial", "B"
        motivo = "revisar si el paréntesis expresa especialidad o titulación; no extender la equivalencia automáticamente"
    elif LABORAL.search(clave) or CENTRO_INFANTIL.search(clave):
        estado, seguridad = "laboral_local_contextual", "C"
        motivo = "conservar contrato, escala, nivel, centro y ámbito; equivalencias de género con resto idéntico requieren revisión propia"
    elif especialidades:
        estado, seguridad = "especialidad_significativa", "C"
        motivo = "especialidad explícita preservada; no es equivalente al Maestro genérico"
    else:
        estado, seguridad = "dudoso", "C"
        motivo = "función docente o alcance de la denominación insuficientemente acreditados"
    res.update(estado=estado, seguridad=seguridad, motivo=motivo)
    return res


def reconstruir(filas):
    """Reconciliación de dos selecciones y particiones sin descartar inciertos."""
    ids_todos = [r["oposicion_id"] for r in filas]
    if len(ids_todos) != len(set(ids_todos)):
        raise ValueError("IDs duplicados en la entrada; auditoría detenida")
    registros = [ficha(r) for r in sorted(filas, key=lambda r: r["oposicion_id"]) if fuentes_candidato(r)]
    ids = [r["oposicion_id"] for r in registros]
    ids_b = sorted(r["oposicion_id"] for r in filas if candidato_por_tokens(r))
    if ids != ids_b:
        raise ValueError("Las reconstrucciones del universo no coinciden")
    grupos = defaultdict(list)
    for r in registros:
        grupos[(r["puesto"], r["puesto_normalizado"], r["textual"], r["efectivo"], r["estado"], r["seguridad"])].append(r)
    top = [{"puesto": k[0], "canon_actual": k[1], "canon_textual": k[2], "canon_efectivo": k[3],
            "clasificacion": k[4], "seguridad": k[5], **resumen(v)} for k, v in grupos.items()]
    top.sort(key=lambda r: (-r["filas"], -r["plazas"], r["puesto"] or "", str(r["canon_actual"])))
    candidatos = [r for r in registros if r["seguridad"] is not None]
    conjuntos = []
    ids_propuestas = [r["oposicion_id"] for r in registros if r["conjunto_propuesto"]]
    colisiones = len(ids_propuestas) - len(set(ids_propuestas))
    for nombre, g in _grupos(registros, "conjunto_propuesto").items():
        if nombre is not None:
            canon = g[0]["canon_propuesto"]
            testigos = [r for r in filas if r["puesto_normalizado"] == canon]
            conjuntos.append({"conjunto": nombre, "canon": canon, **resumen(g),
                "variantes_exactas": sorted({r["puesto"] for r in g}), "seguridad": "A",
                "motivo": g[0]["motivo"], "canon_destino_existente_filas": len(testigos),
                "ids_con_canon_destino": sorted(r["oposicion_id"] for r in testigos),
                "perdida_especialidad_cuerpo_escala_contrato_centro_funcion": False,
                "colisiones_entre_conjuntos": colisiones, "aplicacion_real": False,
                "limites": "seguridad de la equivalencia del puesto, no auditoría de cantidades ni de la convocatoria completa",
                "contexto_conservado_por_id": [{k: r[k] for k in ("oposicion_id", "administracion", "escala", "subescala", "clase", "fecha_boe")} for r in g]})
    pares = defaultdict(list)
    for r in candidatos:
        m = re.fullmatch(r"maestr(?:o/a|a/o|o|a)( .+)", textual._clave(r["puesto"] or ""))
        if m:
            pares[m[1]].append(r)
    return {
        "definicion_universo": {"campos": list(CAMPOS_UNIVERSO), "patron": MAESTROS.pattern,
            "codigo_cuerpo": CODIGO_CUERPO.pattern, "comparacion": "NFKD, sin acentos y casefold, palabras completas",
            "metodo_b": "tokens exactos maestro/maestra/maestros/maestras o pareja codigo 597",
            "sin_fuzzy_matching": True, "titulo_solo_contextual": "no acredita por sí solo la profesión de cada plaza"},
        "universo": {**resumen(registros), "filas_examinadas": len(filas),
            "fingerprint_ids": hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode()).hexdigest()},
        "reconstruccion_b": {"ids": ids_b, "iguales": ids == ids_b, "duplicados": 0},
        "coincidencias_parciales_excluidas": [
            {"oposicion_id": r["oposicion_id"], "puesto": r["puesto"]} for r in filas
            if "maestr" in textual._clave(r["puesto"] or "") and not fuentes_candidato(r)],
        "registros": registros, "estados": {k: resumen([r for r in registros if r["estado"] == k]) for k in ESTADOS},
        "cobertura_evidencia": {"con_titulo_publicacion": sum(bool(r["titulo_original"]) for r in registros),
            "sin_titulo_publicacion": sum(not r["titulo_original"] for r in registros),
            "solo_contexto": resumen([r for r in registros if "puesto" not in r["fuentes_universo"]]),
            "fuentes_coincidentes": dict(Counter(k for r in registros for k in r["fuentes_universo"])),
            "limite": "No se descargan documentos ni se infiere su contenido; las cifras sueltas y las denominaciones truncadas quedan en revisión."},
        "ya_normalizados": resumen([r for r in registros if r["canon_validado_pipeline_previo"]]),
        "pendientes": {**resumen([r for r in candidatos if r["estado"] != "fuera_de_familia"]),
            "nota": "universo docente a revisar, no cambios de SQLite propuestos por el normalizador"},
        "candidatos_clasificados": resumen(candidatos),
        "alcance_seguridad": "A/B/C/D evalúa nuevas equivalencias, no aplicaciones pendientes. D rechaza la absorción en un canon simple; las reglas históricas no se reescriben.",
        "clasificacion_seguridad": {k: resumen([r for r in candidatos if r["seguridad"] == k]) for k in "ABCD"},
        "microfamilias": agrupar(registros, "microfamilia"),
        "especialidades": {nombre: resumen([r for r in registros if nombre in r["especialidades"]])
                           for nombre, _ in ESPECIALIDADES if any(nombre in r["especialidades"] for r in registros)},
        "especialidades_nota": "etiquetas no exclusivas; los totales aditivos son las microfamilias y los estados",
        "top_denominaciones": top, "top_pendientes": [r for r in top if r["seguridad"] and r["clasificacion"] != "fuera_de_familia"],
        "grupos_candidatos": [dict(r, motivo=grupos[(r["puesto"], r["canon_actual"], r["canon_textual"], r["canon_efectivo"], r["clasificacion"], r["seguridad"])][0]["motivo"])
                              for r in top if r["seguridad"]],
        "grupos_por_seguridad": {k: sum(r["seguridad"] == k for r in top) for k in "ABCD"},
        "conjuntos_cerrados_seguros": conjuntos,
        "candidatos_dudosos": [r for r in candidatos if r["seguridad"] in {"B", "C"}],
        "candidatos_rechazados": [r for r in candidatos if r["seguridad"] == "D"],
        "genero_mismo_resto": [{"resto_completo_comun": k, **resumen(v),
            "variantes_exactas": sorted({r["puesto"] for r in v}), "decision": "revisión posterior; no autoriza quitar el resto"}
            for k, v in sorted(pares.items()) if len({r["puesto"] for r in v}) > 1],
        "singular_plural": agrupar(registros, "forma_genero_numero"),
        "cuerpos_docentes": resumen([r for r in registros if r["microfamilia"] == "cuerpo_docente_explicito"]),
        "municipales_locales": resumen([r for r in registros if r["ambito"] == "LOCAL"]),
        "genericos_con_canon_maestros_sin_cuerpo_explicito": [r for r in registros
            if r["puesto_normalizado"] == "Maestros" and not r["acredita_cuerpo_docente"]],
        "especialidades_ausentes_salida_preexistente": [r for r in registros if r["especialidades_ausentes_en_salida_actual"]],
        "alertas_canones_preexistentes": [r for r in registros if r["alerta_canon_previo_ajeno_a_profesion"]],
        "limite_validacion_previa": "Reproducir una regla histórica no prueba pertenencia a un cuerpo ni ausencia de pérdida semántica. Las alertas y descriptores ausentes se documentan sin modificar producción.",
        "recomendacion_paso21": ("Existen uno o varios conjuntos A cerrados y potencialmente aplicables. Diseñar un paso independiente y validar de nuevo antes de implementar."
            if conjuntos else "No existen nuevas reglas seguras de Maestros."),
    }


def _grupos(filas, campo):
    grupos = defaultdict(list)
    for r in filas:
        grupos[r[campo]].append(r)
    return grupos


def reconciliar_historicos(filas, directorio=INFORMES):
    actuales = {r["oposicion_id"]: r for r in filas}
    salida = {}
    for nombre, fichero, seccion, campo in (
        ("fase7_9l", "fase7_maestros_pendientes_paso9l2.json", "conjunto_cerrado", "canon_por_id"),
        ("fase8_7", "fase8_paso7_educacion_infantil.json", "conjunto_seguro", "mapa_id_canon"),
    ):
        ruta = Path(directorio) / fichero
        if not ruta.exists():
            salida[nombre] = {"estado": "informe_historico_no_disponible"}
            continue
        previo = json.loads(ruta.read_text())[seccion]
        mapa = {int(k): v for k, v in previo[campo].items()}
        encontrados = [actuales[i] for i in mapa if i in actuales]
        salida[nombre] = {"fuente": str(ruta), "sha256": sha(ruta),
            "historico": {"filas": previo["filas"], "plazas": previo["plazas"]},
            "actual": resumen([dict(r, plazas=r["num_plazas"]) for r in encontrados]),
            "ids_ausentes": sorted(set(mapa) - set(actuales)),
            "ids_con_canon_distinto": sorted(r["oposicion_id"] for r in encontrados if r["puesto_normalizado"] != mapa[r["oposicion_id"]]),
            "variantes_actuales": dict(Counter(r["puesto"] for r in encontrados))}
    return salida


def resumir_gate(informe):
    return {"version": informe["version"], "total_discrepancias": informe["total_discrepancias"],
        "total_plazas_discrepantes": informe["total_plazas_discrepantes"],
        **{k: {f: informe[k][f] for f in ("filas", "plazas", "ids")} for k in paso19.CATEGORIAS},
        "sqlite_modificada": informe["sqlite_modificada"]}


def auditar(ruta_bd=paso19.DB, *, precheck=None, historicos=INFORMES):
    ruta = Path(ruta_bd).resolve()
    inicio = paso19._estado(ruta)
    normalizador = ROOT / "normalizacion_puestos.py"
    hash_inicial = sha(normalizador)
    if precheck and inicio != precheck["sqlite"]:
        raise RuntimeError("Gate SQLite: la base difiere del precheck del paso 20; no restaurar")
    if precheck and hash_inicial != precheck["hashes_archivos_iniciales"]["normalizacion_puestos.py"]:
        raise RuntimeError("Gate normalizador: difiere del precheck")
    gate_antes = precheck["gate_global_paso19"] if precheck else resumir_gate(paso19.auditar(ruta))
    con = sqlite3.connect(ruta.as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        filas = [dict(r) for r in con.execute("SELECT o.*, p.titulo_original FROM oposiciones o LEFT JOIN publicaciones p USING(publicacion_id) ORDER BY o.oposicion_id")]
    finally:
        con.close()
    informe = reconstruir(filas)
    informe["estado_previo"] = reconciliar_historicos(filas, historicos)
    informe["reglas_activas"] = {
        "fuente": "normalizacion_puestos.py", "sha256": hash_inicial,
        "cuerpo": "_normalizar_cuerpo_maestros y reglas_docentes de _normalizar_puesto_una_vez; incluyen Maestro/Maestros genéricos sin inferir contexto",
        "infantil": "_normalizar_maestro_educacion_infantil: singular completo maestr(o/a|a/o|a|o), preposición de/en opcional",
        "precedencia": "Música y artes antes de Maestros; educación infantil separada; no hay una regla global de género para maestro",
        "canones_observados_validados": agrupar([r for r in informe["registros"] if r["canon_validado_pipeline_previo"]], "puesto_normalizado")}
    gate_despues = resumir_gate(paso19.auditar(ruta))
    final = paso19._estado(ruta)
    modificado = sha(normalizador) != hash_inicial
    if final != inicio or gate_despues["sqlite_modificada"]:
        raise RuntimeError("Gate SQLite final: la base cambió; no restaurar")
    if modificado:
        raise RuntimeError("Gate normalizador final: el código cambió durante la auditoría")
    informe.update(version="fase8-paso20-v1", generado_utc=datetime.now(timezone.utc).isoformat(), modo="read-only",
        baseline_sqlite=inicio, sqlite_final=final, sqlite_modificada=False,
        normalizacion_puestos_modificada=modificado,
        normalizador_sha256_inicial=hash_inicial, normalizador_sha256_final=sha(normalizador),
        gate_global_paso19={"antes": gate_antes, "despues": gate_despues, "sin_diferencias": gate_antes == gate_despues},
        aplicacion_real=False)
    return informe


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bd", type=Path, default=paso19.DB)
    p.add_argument("--salida", type=Path, default=SALIDA)
    p.add_argument("--precheck", type=Path, default=PRECHECK)
    args = p.parse_args(argv)
    previo = json.loads(args.precheck.read_text()) if args.precheck.exists() else None
    git_inicial = previo["git"] if previo else estado_git()
    informe = auditar(args.bd, precheck=previo)
    informe["git"] = {"inicial": git_inicial, "final": estado_git()}
    if previo:
        informe["archivos_preexistentes_alterados"] = [f for f, h in previo["hashes_archivos_iniciales"].items() if sha(ROOT / f) != h]
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    detalle = args.salida.with_name(args.salida.stem + "_detalle.csv")
    with detalle.open("w", encoding="utf-8", newline="") as f:
        campos = list(informe["registros"][0]) if informe["registros"] else ["oposicion_id"]
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        for fila in informe["registros"]:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v for k, v in fila.items()})
    print(json.dumps({"universo": {k: informe["universo"][k] for k in ("filas", "plazas", "denominaciones")},
        "seguridad": {k: v["filas"] for k, v in informe["clasificacion_seguridad"].items()},
        "conjuntos_A": len(informe["conjuntos_cerrados_seguros"]), "sqlite_modificada": informe["sqlite_modificada"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
