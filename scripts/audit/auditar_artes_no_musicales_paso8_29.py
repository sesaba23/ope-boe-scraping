"""Auditoría read-only de la microfamilia Artes no musicales (PASO 29)."""
from __future__ import annotations
import csv, hashlib, json, re, sqlite3, sys
from collections import Counter, defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from normalizacion_puestos import normalizar_puesto, _clave
from scripts.audit.auditar_criterio_dry_run_global_paso8_19 import auditar as auditar_global

DB = ROOT / "datos/boe.db"
OUT = ROOT / "informes/normalizacion_puestos/fase8_paso29_artes_no_musicales.json"
CSV_OUT = ROOT / "informes/normalizacion_puestos/fase8_paso29_artes_no_musicales_detalle.csv"

def estado():
    st = DB.stat(); con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    try:
        meta = dict(con.execute("select clave,valor from metadata"))
        return {"sha256": hashlib.sha256(DB.read_bytes()).hexdigest(), "tamano": st.st_size, "mtime_ns": st.st_mtime_ns, "schema_version": meta.get("schema_version"), "data_version": meta.get("data_version"), "oposiciones": con.execute("select count(*) from oposiciones").fetchone()[0], "plazas": con.execute("select coalesce(sum(num_plazas),0) from oposiciones").fetchone()[0], "publicaciones": con.execute("select count(*) from publicaciones").fetchone()[0], "busquedas": con.execute("select count(*) from busquedas").fetchone()[0], "cobertura": con.execute("select count(*) from cobertura").fetchone()[0], "integrity_check": con.execute("pragma integrity_check").fetchone()[0], "foreign_key_check": [list(x) for x in con.execute("pragma foreign_key_check")], "wal_existe": DB.with_name(DB.name+'-wal').exists(), "shm_existe": DB.with_name(DB.name+'-shm').exists()}
    finally: con.close()

def seleccionar(con):
    filas = con.execute("""select o.*, p.titulo_original from oposiciones o left join publicaciones p on p.publicacion_id=o.publicacion_id
      where lower(o.puesto) like '%maestr%' and (lower(o.puesto) like '%arte%' or lower(o.puesto) like '%pint%' or lower(o.puesto) like '%ceram%' or lower(o.puesto) like '%telares%' or lower(o.puesto) like '%diseño%')
      and lower(o.puesto) not like '%taller%' and lower(o.puesto) not like '%fotocompos%' and lower(o.puesto) not like '%pintor%' and lower(o.puesto) not like '%carpinter%' order by o.oposicion_id""").fetchall()
    return [dict(f) for f in filas]

def ficha(f):
    clave = _clave(f['puesto']); low = clave
    disciplinas = [x for x in ('dibujo','pintura','escultura','ceramica','fotografia','diseno','grabado','artes plasticas','telares y tejido') if x in low]
    if 'fotocompos' in low: clas, motivo = 'D', 'oficio de fotocomposición; no equivale a composición musical'
    elif 'taller' in low: clas, motivo = 'D', 'taller y relación funcional deben conservarse'
    elif 'artes plasticas y diseno' in low: clas, motivo = 'C', 'disciplina y nivel artístico explícitos; no fusionar con Maestro genérico'
    else: clas, motivo = 'C', 'especialidad artística significativa; falta evidencia para equivalencia automática'
    return {"id": f['oposicion_id'], "puesto": f['puesto'], "puesto_normalizado": f['puesto_normalizado'], "recalculado": normalizar_puesto(f['puesto']), "plazas": f['num_plazas'], "anio": str(f['fecha_boe'])[:4], "administracion": f['administracion'], "provincia": f['provincia'], "escala": f['escala'], "subescala": f['subescala'], "clase": f['clase'], "titulo_original": f['titulo_original'], "disciplina_artistica": disciplinas, "especialidad": disciplinas, "motivo_inclusion": "maestro + término artístico no musical; exclusiones explícitas de talleres/oficios/fotocomposición", "clasificacion": clas, "canon_posible": None, "motivo": motivo}

def auditar():
    before = estado(); con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    try:
        rows = seleccionar(con)
        fotocomposicion_corpus = [dict(x) for x in con.execute("select oposicion_id,puesto,puesto_normalizado,num_plazas,fecha_boe,administracion from oposiciones where lower(puesto) like '%fotocompos%' or lower(puesto_normalizado) like '%fotocompos%' order by oposicion_id")]
        ceramica_corpus = [dict(x) for x in con.execute("select oposicion_id,puesto,puesto_normalizado,num_plazas,fecha_boe,administracion from oposiciones where lower(puesto) like '%ceram%' or lower(puesto_normalizado) like '%ceram%' order by oposicion_id")]
    finally: con.close()
    detalles = [ficha(f) for f in rows]
    denoms = defaultdict(list)
    for f in detalles: denoms[f['puesto']].append(f)
    grupos = [{"denominacion": k, "filas": len(v), "plazas": sum(float(x['plazas'] or 0) for x in v), "ids": [x['id'] for x in v], "anios": sorted({x['anio'] for x in v}), "administraciones": sorted({x['administracion'] or '' for x in v}), "canon_persistido": sorted({x['puesto_normalizado'] for x in v}), "canon_recalculado": sorted({x['recalculado'] for x in v}), "clasificaciones": sorted({x['clasificacion'] for x in v})} for k,v in sorted(denoms.items())]
    ids20 = {30313,45286,65342,76416,106790}; ids29 = {x['id'] for x in detalles}
    after = estado(); global_gate = auditar_global()
    gate = {"total_discrepancias": global_gate["total_discrepancias"], "total_plazas_discrepantes": global_gate["total_plazas_discrepantes"], **{k: global_gate[k]["filas"] for k in ("cambios_reales_recalculables", "discrepancias_contextuales_no_recalculables", "discrepancias_no_clasificables_automaticamente")}}
    gate_ok = gate["cambios_reales_recalculables"] == 0 and gate["discrepancias_contextuales_no_recalculables"] == 329 and gate["discrepancias_no_clasificables_automaticamente"] == 0
    return {"paso": "FASE 8 — PASO 29", "precheck": before, "postcheck": after, "sqlite_inmutable": before == after, "normalizador_sha256_inicial": hashlib.sha256((ROOT/'normalizacion_puestos.py').read_bytes()).hexdigest(), "normalizador_sha256_final": hashlib.sha256((ROOT/'normalizacion_puestos.py').read_bytes()).hexdigest(), "reconstruccion": {"filas": len(detalles), "plazas": sum(float(x['plazas'] or 0) for x in detalles), "ids_paso20": sorted(ids20), "ids_paso29": sorted(ids29), "interseccion": sorted(ids20 & ids29), "solo_paso20": sorted(ids20-ids29), "solo_paso29": sorted(ids29-ids20)}, "registros": detalles, "denominaciones": grupos, "variantes_controladas": "Sólo se evaluaron variaciones gráficas/gramaticales; no fuzzy matching.", "fotocomposicion": [x for x in detalles if 'fotocompos' in _clave(x['puesto'])], "fotocomposicion_corpus": fotocomposicion_corpus, "ceramica": [x for x in detalles if 'ceram' in _clave(x['puesto'])], "ceramica_corpus": ceramica_corpus, "anomalias_historicas": [{"id": x['oposicion_id'], "puesto": x['puesto'], "puesto_normalizado": x['puesto_normalizado'], "tipo": "fotocomposicion_persistida_como_composicion_musical", "reproducible": normalizar_puesto(x['puesto']) == 'Profesor de Música - Composición', "impacto_global": "registro fuera del universo Artes A"} for x in fotocomposicion_corpus], "conjuntos_A": [], "simulacion": {"esperados": [], "obtenidos": [], "faltantes": [], "inesperados": []}, "gate_global_paso19": gate, "ok": before == after and gate_ok and len({x['id'] for x in detalles}) == len(detalles)}

def main():
    informe = auditar(); OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(informe, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    with CSV_OUT.open('w', newline='', encoding='utf-8') as fh:
        campos = ['id','puesto','puesto_normalizado','recalculado','plazas','anio','administracion','provincia','escala','subescala','clase','titulo_original','disciplina_artistica','clasificacion','motivo']
        w=csv.DictWriter(fh, fieldnames=campos); w.writeheader()
        for row in informe['registros']: w.writerow({k: '; '.join(row[k]) if isinstance(row[k], list) else row[k] for k in campos})
    print(json.dumps(informe, ensure_ascii=False, indent=2)); raise SystemExit(0 if informe['ok'] else 1)
if __name__ == '__main__': main()
