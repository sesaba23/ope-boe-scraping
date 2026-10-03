# Rendimiento Web — Paso 3: optimización de conversión de fechas

## Estado y restricciones

- Rama `main`, HEAD `97a63db025975623c8614854607afc4f0d868385`, tag `v5.2.0`.
- Se conservaron los cambios locales de los Pasos 2 y el informe previo.
- SQLite no se modificó: SHA-256 `3bef628b733427bd7238848ab6aa9359e7114fa15e5498f617a0523d2df53530`.
- `schema_version=7`, `data_version=78`, `tipo_personal_version=tipo-personal-v1`, integridad `ok`, claves foráneas `[]`.
- No se implementó caché, no se crearon índices y no se tocó frontend.

## Comportamiento congelado

`_convertir_fecha` admite valores nulos, enteros/cadenas `YYYYMMDD`, cadenas españolas con «de», fechas `d/m/Y`, objetos `date`/`datetime`/`Timestamp`, ISO y fallback de `pandas.to_datetime`; los inválidos producen `NaT`.

La implementación nueva conserva `_convertir_fecha` para excepciones y formatos minoritarios. Sólo acelera grupos homogéneos identificables con seguridad.

## Inventario real

Sobre las 109.429 filas de `oposiciones.Fecha_boe`:

| Formato/tipo | Registros |
|---|---:|
| cadena ISO `YYYY-MM-DD` | 109.429 |
| nulos | 0 |
| cadenas vacías | 0 |
| otros formatos | 0 |
| resultados inválidos de la conversión actual | 0 |

Hay 5.705 valores distintos, pero todos pertenecen al mismo formato ISO.

## Baseline

Microbenchmark de `serie.map(_convertir_fecha)` sobre exactamente las 109.429 fechas:

| Primera | Mínimo | Mediana | Media | Máximo |
|---:|---:|---:|---:|---:|
| 6.444,6 ms | 6.430,3 ms | 6.446,7 ms | 6.449,4 ms | 6.465,8 ms |

Mediana previa de `/api/estadisticas`: 9.806,8 ms.

El coste procedía de procesamiento Python fila a fila y llamadas individuales a `pandas.to_datetime` desde `_convertir_fecha`.

## Diseño aplicado

Se añadió `preparar_fechas()`:

1. crea una serie temporal con el mismo índice;
2. detecta explícitamente cadenas ISO mediante expresión regular;
3. convierte el grupo ISO completo con `pd.to_datetime(..., format="%Y-%m-%d")`;
4. envía sólo valores no ISO y no nulos al parser legacy;
5. recompone la serie como `datetime64[ns]`.

La preparación de `Fecha_dt` sigue ejecutándose una sola vez por petición gracias al Paso 2.

## Equivalencia exhaustiva

Se compararon los 109.429 resultados de `serie.map(_convertir_fecha)` con `preparar_fechas()` considerando `NaT` como equivalente:

```text
diferencias = 0
filas en fallback = 0
```

La estrategia también conserva tests de ISO, formatos españoles, nulos, vacíos, inválidos, `datetime` y `Timestamp`.

## Benchmark después

Microbenchmark de `preparar_fechas()`:

| Primera | Mínimo | Mediana | Media | Máximo |
|---:|---:|---:|---:|---:|
| 38,2 ms | 35,1 ms | 35,7 ms | 35,6 ms | 36,0 ms |

Reducción de la preparación: aproximadamente `6.411 ms`, un `99,4 %`.

Benchmark de `/api/estadisticas` después:

| Primera | Mínimo | Mediana | Media | Máximo |
|---:|---:|---:|---:|---:|
| 2.910,1 ms | 2.474,6 ms | 2.509,1 ms | 2.501,4 ms | 2.527,4 ms |

Comparado con el Paso 2: reducción de aproximadamente `7.298 ms`, un `74,4 %` adicional.

## Perfil posterior

Desglose instrumentado de una petición:

| Bloque | Tiempo |
|---|---:|
| opciones de filtros | 347 ms |
| lectura SQLite | 425 ms |
| `normalizar_datos` / fechas | 87 ms |
| carga y preparación | 523 ms |
| estadísticas principales | 1.453 ms |
| comparación de puestos | 218 ms |
| metadata | 143 ms |
| total instrumentado | 2.725 ms |

El perfil CPU confirma que la conversión de fechas dejó de ser el cuello de botella dominante. Ahora destacan las copias/agrupaciones pandas de `calcular_estadisticas`, validaciones de SQLite y construcción de series.

## Hash de respuesta

El hash determinista por defecto permanece idéntico al Paso 2:

`f12eb3b5d8482d753452dbcf619f7e3440685b26e8b671efc6f01baed11f9216`

También se verificaron las variantes de puesto, fechas y `tipo_personal`; sus hashes coinciden con el baseline del Paso 2.

## Tests

Suite afectada y de regresión: `156 passed`.

Incluye equivalencia de fechas, formatos reales, estadísticas, comparación de puestos, API, `tipo_personal` y web.

## Decisión para Paso 4

La conversión de fechas ya no justifica otro paso específico: bajó de ~6,45 s a ~36 ms. El siguiente cuello de botella está en el cálculo pandas, especialmente copias, agrupaciones y validaciones repetidas de la ruta de estadísticas. Se recomienda perfilar y optimizar ese cálculo antes de valorar una caché por `data_version`.

`RENDIMIENTO WEB PASO 3 COMPLETADO — CONVERSIÓN DE FECHAS OPTIMIZADA Y RESULTADOS CONSERVADOS`
