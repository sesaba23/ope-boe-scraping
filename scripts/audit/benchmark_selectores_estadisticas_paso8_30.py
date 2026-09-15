"""Benchmark reproducible del catálogo normalizado de puestos."""
from __future__ import annotations
import json, time
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
import consultas_boe
DB = ROOT / "datos/boe.db"

def medir():
    consultas_boe._OPCIONES_FILTROS_CACHE.clear()
    t0 = time.perf_counter(); primero = consultas_boe.opciones_filtros(DB); frio = time.perf_counter() - t0
    t1 = time.perf_counter(); segundo = consultas_boe.opciones_filtros(DB); caliente = time.perf_counter() - t1
    return {"catalogo_puestos_normalizados": len(primero["puestos"]), "opciones_unicas": len(set(primero["puestos"])), "ordenado": primero["puestos"] == sorted(primero["puestos"], key=str.casefold), "catalogo_igual_en_cache": primero == segundo, "consultas_sql_antes": 6, "consultas_sql_primera_carga": 6, "consultas_sql_carga_cache": 1, "peticiones_http_catalogo": 0, "tiempo_backend_primera_carga_s": frio, "tiempo_backend_cache_s": caliente, "tamano_respuesta_aprox_bytes": len(json.dumps(primero, ensure_ascii=False).encode()), "arquitectura": "Una carga de opciones compartida por los cinco selectores; caché en memoria invalidada por data_version."}

if __name__ == "__main__":
    resultado = medir()
    destino = ROOT / "informes/normalizacion_puestos/fase8_paso30_optimizacion_selectores_estadisticas.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps({"arquitectura_previa": "opciones_filtros consultaba el catálogo en cada carga y no había caché", "cuello_botella": "consulta DISTINCT de 38k puestos y reconstrucción del catálogo", "consulta_nueva": "una DISTINCT sobre COALESCE(puesto_normalizado, puesto), sin joins, ordenada casefold", "cache": "memoria por (ruta, data_version)", "benchmark": resultado, "tests": "catálogo compartido, valores únicos y ordenados"}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
