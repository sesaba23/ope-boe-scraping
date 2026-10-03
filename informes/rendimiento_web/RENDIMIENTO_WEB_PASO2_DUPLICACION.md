# Rendimiento Web — Paso 2: eliminación de carga y normalización duplicadas

## Estado y restricciones

- Rama `main`, HEAD `97a63db025975623c8614854607afc4f0d868385`, tag `v5.2.0`.
- El repositorio ya contenía cambios locales previos y el informe del Paso 1; se conservaron.
- SQLite no se modificó. SHA-256 antes/después: `3bef628b733427bd7238848ab6aa9359e7114fa15e5498f617a0523d2df53530`.
- `schema_version=7`, `data_version=78`, `tipo_personal_version=tipo-personal-v1`, integridad `ok`, claves foráneas `[]`.
- No se implementó caché, índice ni cambio frontend.

## Baseline reproducible

Antes del cambio, cinco ejecuciones calientes de `/api/estadisticas` dieron:

| Primera | Mínimo | Mediana | Media | Máximo |
|---:|---:|---:|---:|---:|
| 16.053,7 ms | 15.769,5 ms | 15.796,5 ms | 15.823,4 ms | 15.937,3 ms |

El baseline ejecutaba 14 sentencias SQL calientes, incluyendo dos `SELECT` completos de `oposiciones`.

Hash determinista del JSON baseline (orden de claves normalizado):

`f12eb3b5d8482d753452dbcf619f7e3440685b26e8b671efc6f01baed11f9216`

## Cambio aplicado

Se añadió una preparación compartida en `estadisticas.py`:

- `cargar_datos_estadisticas_sqlite()` carga SQLite y llama una única vez a `preparar_datos_estadisticas()`.
- `preparar_datos_estadisticas()` añade `Fecha_dt` y `Num_plazas_num` sólo si faltan.
- `calcular_comparacion_puestos()` recibe el DataFrame preparado.
- `calcular_comparacion_puestos_sqlite()` se conserva como wrapper compatible para llamadores externos.
- `web_estadisticas.api_estadisticas` carga una vez y pasa el mismo DataFrame a estadísticas principales y comparación.
- Las conversiones posteriores usan `Fecha_dt` ya preparada; no vuelven a convertir la columna completa.

Se mantuvieron filtros, contratos JSON, categorías `tipo_personal`, comportamiento de datos vacíos y APIs públicas.

## Evidencia de no duplicación

Con trazado SQLite después del cambio:

- 16 sentencias totales en frío, 10 de validación/metadata y opciones, 1 lectura completa de `oposiciones`.
- En caliente: 1 lectura completa de `oposiciones` por petición.
- Una llamada a `normalizar_datos` por petición.

El test `test_calculos_comparten_dataframe_preparado_sin_repetir_normalizacion` falla si un consumidor intenta normalizar de nuevo un DataFrame preparado.

## Benchmark después

Cinco ejecuciones calientes después del cambio:

| Primera | Mínimo | Mediana | Media | Máximo |
|---:|---:|---:|---:|---:|
| 10.116,7 ms | 9.716,3 ms | 9.806,8 ms | 9.794,2 ms | 9.854,3 ms |

Comparación con la mediana baseline:

- diferencia absoluta: `5.989,7 ms` menos;
- mejora: `37,9 %` aproximadamente;
- bytes de respuesta: `2.085.825` antes y después.

## Desglose después

| Bloque | Después |
|---|---:|
| opciones de filtros | 345 ms |
| lectura SQLite | 425 ms |
| única normalización | 6.461 ms |
| preparación total | 6.896 ms |
| estadísticas principales | 1.455 ms |
| comparación de puestos | 219 ms |
| metadata | 131 ms |
| total instrumentado | 9.087 ms |

El tiempo restante corresponde a serialización y envoltura Flask.

## Equivalencia funcional

El JSON determinista después del cambio produjo exactamente el mismo hash que el baseline:

`f12eb3b5d8482d753452dbcf619f7e3440685b26e8b671efc6f01baed11f9216`

También se comprobaron variantes representativas. Los hashes baseline/después coinciden para fechas y filtros de `tipo_personal`; para `puesto=Ingeniero` ambos son `0d1b1ce22207ea4368d1939c8bf0dc66264803cd732759c2882b050350aa09c6`, y para `puesto=Ingeniero&tipo_personal=Funcionario` ambos son `ad5474d382c56cfda045758a0d344859972762eae531e46fc91341fb8e58af5a`.

Pruebas ejecutadas:

- Estadísticas, web y `tipo_personal`: `154 passed`.
- End-to-end de puestos/estadísticas: `45 passed`.
- Test específico de no duplicación: `1 passed`.

## Siguiente cuello de botella

Tras eliminar la duplicación, la normalización de fechas sigue siendo el coste dominante: aproximadamente 6,46 s de los 9,09 s instrumentados. La conversión repetida dentro de consumidores ya desapareció; lo que queda es la primera conversión fila a fila mediante `_convertir_fecha`.

El Paso 3 debería evaluar una estrategia vectorizada o por formatos agrupados, manteniendo equivalencia exacta para fechas históricas. No se recomienda implementar caché todavía: podría evitar aproximadamente los 9–10 s completos en peticiones repetidas, pero primero debe resolverse la preparación y medirse el beneficio residual.

## Estado final

- No se modificó SQLite ni se crearon índices.
- No se cambió el frontend.
- No se hizo commit ni push.
- El único artefacto nuevo de diagnóstico es este informe; los cambios de código son exclusivamente la eliminación de duplicación solicitada.

`RENDIMIENTO WEB PASO 2 COMPLETADO — DUPLICACIÓN ELIMINADA Y RESULTADOS CONSERVADOS`
