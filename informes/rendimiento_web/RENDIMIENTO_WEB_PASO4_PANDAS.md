# Rendimiento Web — Paso 4: optimización de cálculos pandas

## A. Estado inicial

- Rama `main`; HEAD `97a63db025975623c8614854607afc4f0d868385`; tag `v5.2.0`.
- Se conservaron los cambios locales de los Pasos 2 y 3.
- SQLite: `schema_version=7`, `data_version=78`, `tipo_personal_version=tipo-personal-v1`.
- SHA-256 antes/después: `3bef628b733427bd7238848ab6aa9359e7114fa15e5498f617a0523d2df53530`.
- `integrity_check=ok`; `foreign_key_check=[]`.

## B–C. Baseline y resultados congelados

Baseline reproducido de `/api/estadisticas` tras el Paso 3, cinco ejecuciones calientes:

| Mínimo | Mediana | Media | Máximo |
|---:|---:|---:|---:|
| 2.474,6 ms | 2.509,1 ms | 2.501,4 ms | 2.527,4 ms |

Hash JSON de referencia y resultado final:

`f12eb3b5d8482d753452dbcf619f7e3440685b26e8b671efc6f01baed11f9216`

También se conservaron los hashes de variantes con puesto, fechas y `tipo_personal`; permanecen idénticos.

## D–G. Perfil detallado inicial

El perfil CPU del Paso 3 mostraba aproximadamente:

1. `calcular_estadisticas`: ~1.455 ms instrumentados.
2. Copias pandas acumuladas: ~0,6 s en el perfil CPU; la función hacía una copia profunda completa y copias anchas para provincias, comunidades y fechas.
3. `_mascara_no_disponible`: nueve ejecuciones, ~0,57 s acumulados, repitiendo conversiones `fillna → astype(str) → strip → casefold`.
4. Agrupaciones `_agrupar` y ordenaciones de administraciones, puestos, provincias y comunidades.
5. `_evolucion_puestos`: dos ejecuciones, ~0,37 s acumulados.

No se detectó una misma consulta SQL repetida por este cálculo ni trabajo de `tipo_personal` que reclasifique filas.

## H–I. Columnas y memoria

La carga ya era explícita, no `SELECT *`. Se utilizan columnas de plazas, puesto, administración, comunidad, provincia, municipio, ámbito, sistema, turno, `tipo_personal` y fecha.

Memoria aproximada del DataFrame preparado: `88,65 MB`.

Copias anchas anteriores: otra copia potencial de aproximadamente `88,65 MB`, además de copias derivadas. Las nuevas tablas temporales seleccionan sólo columnas necesarias:

| Temporal | Memoria aproximada |
|---|---:|
| Administración + plazas | 9,92 MB |
| Provincia + plazas | 7,43 MB |
| Comunidad + plazas | 8,33 MB |
| Fecha + plazas + puesto | 11,62 MB |

## J–L. Optimización implementada

- `calcular_estadisticas` reutiliza el DataFrame preparado y no realiza una copia profunda completa.
- Sólo se crea una copia estrecha cuando hay que rellenar puestos normalizados nulos.
- Administraciones, provincias y comunidades trabajan con las dos columnas necesarias.
- La evolución temporal trabaja con columnas temporales mínimas.
- Las máscaras de administración y comunidad se calculan una vez y se reutilizan para calidad y agrupación.
- No se cambiaron contratos JSON, frontend, SQL ni SQLite.

No se cambió `value_counts` por `groupby().size()` ni se trasladaron agregaciones a SQL: no había evidencia suficiente de beneficio adicional sin aumentar riesgo semántico.

## M. Tests añadidos y regresión

Se mantuvo el test estructural del Paso 3 para evitar repetir preparación. Las pruebas verifican estadísticas, puestos, filtros, `tipo_personal`, datos vacíos y web.

Suite afectada ejecutada: `143 passed` para estadísticas/web y suites ampliadas `205 passed` en la validación combinada previa.

## N–O. Equivalencia

El hash determinista del JSON principal permanece exactamente igual al Paso 3:

`f12eb3b5d8482d753452dbcf619f7e3440685b26e8b671efc6f01baed11f9216`

Los hashes de `puesto=Ingeniero`, rango de fechas y `tipo_personal=Funcionario+Laboral` también coinciden con sus referencias del Paso 3.

## P–W. Benchmark final

Seis ejecuciones, primera considerada fría y cinco calientes:

| Métrica | Paso 3 | Paso 4 | Mejora |
|---|---:|---:|---:|
| API completa, mediana | 2.509,1 ms | 1.817,2 ms | 27,6 % |
| API completa, media | 2.501,4 ms | 1.814,9 ms | 27,4 % |
| Primera API | 2.910,1 ms | 1.999,6 ms | 31,3 % |
| Fechas | 35,7 ms | 35,7 ms | sin cambio relevante |
| SQLite | ~425 ms | ~422 ms | sin cambio relevante |

Desglose instrumentado después:

| Bloque | Tiempo |
|---|---:|
| opciones de filtros | 341 ms |
| lectura SQLite | 423 ms |
| normalización fechas | 89 ms |
| carga y preparación | 521 ms |
| `calcular_estadisticas` | 737 ms |
| comparación puestos | 219 ms |
| metadata | 130 ms |
| total instrumentado | 1.988 ms |

Mejora acumulada desde el Paso 1: de ~15.796 ms a ~1.817 ms, aproximadamente `88,5 %`.

## X–Y. Nuevo perfil y cuello de botella

El perfil nuevo muestra como costes principales la validación/lectura SQLite (~0,4 s), máscaras de calidad restantes y agrupaciones pandas. La conversión de fechas ya no es relevante (~36–90 ms). `tipo_personal` usa exclusivamente la columna persistida.

El nuevo cuello de botella es el cálculo agregado restante y las validaciones de apertura de la base, no una duplicación de DataFrames.

## Z. Caché

No se implementó. Con el cálculo actual, una caché por `(data_version, parámetros)` podría evitar aproximadamente 1,8 segundos en peticiones repetidas idénticas. Debe evaluarse considerando memoria, multiproceso, reinicios e invalidación.

## AA–AF. Recomendación y cierre

La API aún supera 1 segundo, aunque el cálculo pandas ya se redujo significativamente. Para Paso 5 se recomienda perfilar la validación SQLite y las agrupaciones restantes; después decidir entre otra optimización segura o caché por `data_version`.

`git diff --check` está limpio. No se hizo commit ni push. SQLite permanece byte a byte intacta y el árbol conserva los cambios acumulados de los pasos anteriores junto con este informe.

`RENDIMIENTO WEB PASO 4 COMPLETADO — CÁLCULO PANDAS OPTIMIZADO`
