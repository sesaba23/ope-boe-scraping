# Rendimiento Web — Paso 1: profiling y diagnóstico

Fecha del análisis: 2026-09-25. El análisis fue estrictamente de lectura; no se modificó código productivo, frontend, esquema, índices ni `datos/boe.db`.

## A–B. Estado y base SQLite

- Rama: `main`.
- HEAD: `97a63db025975623c8614854607afc4f0d868385`.
- Tag exacto: `v5.2.0`.
- El árbol inicial no estaba limpio: había cambios locales previos del trabajo de `tipo_personal`; se conservaron sin alterarlos.
- `schema_version=7`, `data_version=78`, `tipo_personal_version=tipo-personal-v1`.
- Integridad: `PRAGMA integrity_check = ok`; `PRAGMA foreign_key_check = []`.
- Tamaño: `170.123.264` bytes.
- SHA-256 antes y después: `3bef628b733427bd7238848ab6aa9359e7114fa15e5498f617a0523d2df53530`.
- Publicaciones: 109.429; oposiciones: 109.429; plazas totales: se obtienen mediante `SUM(num_plazas)` de las filas válidas.

Distribución de `tipo_personal`: Funcionario 55.961, Laboral 18.216, Estatutario 1, Universitario 2.900, Militar 1, Otros 1, No determinado 32.349.

## C. Arquitectura trazada

```text
/estadisticas (HTML estático)
  → static/js/estadisticas.js
  → GET /api/estadisticas (un único fetch)
  → web_estadisticas.api_estadisticas
  → opciones_filtros + calcular_estadisticas_sqlite
       → consultas_boe.oposiciones → SELECT completo de oposiciones
       → estadisticas.normalizar_datos → pandas
       → estadisticas.calcular_estadisticas
  → calcular_comparacion_puestos_sqlite
       → segunda consulta completa + segunda normalización pandas
  → metadata
  → JSON de 2.085.825 bytes
  → siete gráficos y rankings en el navegador
```

Oposiciones y mapa reutilizan consultas SQLite parametrizadas distintas; Estadísticas no reutiliza el DataFrame producido por la primera estadística para la comparación de puestos.

## D–F. Endpoints y benchmark end-to-end

Mediciones con Flask `test_client`, una ejecución fría y cinco consecutivas calientes por ruta. Los valores son orientativos del entorno local.

| Ruta | Fría ms | Mediana caliente ms | Media caliente ms | Máx. caliente ms | SQL caliente | Bytes |
|---|---:|---:|---:|---:|---:|---:|
| `/` | 7,7 | 0,2 | 0,2 | 0,3 | 0 | 3.021 |
| `/oposiciones` | 997,6 | 352,5 | 347,6 | 356,0 | 12 | 448.931 |
| `/oposiciones?ver_todas=1` | 494,8 | 487,9 | 490,6 | 503,1 | 17 | 468.589 |
| `/oposiciones?ver_todas=1&vista=mapa` | 481,6 | 488,2 | 488,2 | 500,3 | 17 | 469.086 |
| `/estadisticas` | 2,7 | 0,2 | 0,2 | 0,2 | 0 | 10.947 |
| `/api/estadisticas` | 16.053,7 | 15.796,5 | 15.823,4 | 15.937,3 | 14 | 2.085.825 |
| `/api/oposiciones/mapa?tipo_personal=Funcionario` | 276,3 | 290,1 | 287,1 | 293,4 | 4 | 673.616 |
| `/api/oposiciones/sin-coordenadas?tipo_personal=Laboral` | 160,0 | 158,9 | 159,0 | 160,0 | 4 | 23.604 |

Conclusión A/B/C/D: los ~8 segundos observados no corresponden a la generación HTML de `/estadisticas`; corresponden a la petición API posterior y, en este entorno, alcanzan aproximadamente 15,8 s.

## G–I. Consultas y ranking de coste

`/api/estadisticas` ejecuta 20 sentencias trazables en frío y 14 en caliente. Las 6 adicionales en frío son validación de esquema/metadata/quick-check. Inventario caliente:

1. opciones dinámicas: 4 `DISTINCT` (provincia, ámbito, sistema, turno), 1 `DISTINCT` de puestos y metadata;
2. primera consulta completa de `oposiciones` (109.429 filas);
3. segunda consulta completa idéntica para comparación de puestos;
4. metadata final.

No se detectó N+1. Sí se detectó trabajo duplicado: dos lecturas completas y dos normalizaciones completas de fechas.

Instrumentación por bloques (una petición):

| Bloque | Tiempo |
|---|---:|
| `opciones_filtros` | 718 ms |
| primera lectura SQL (`oposiciones`) | 447 ms |
| primera `normalizar_datos` | 6.417 ms |
| primera `calcular_estadisticas` | 7.865 ms |
| `calcular_estadisticas_sqlite` | 8.344 ms |
| segunda lectura SQL | 474 ms |
| segunda `normalizar_datos` | 6.379 ms |
| comparación de puestos | 7.116 ms |
| metadata final | 193 ms |
| total medido | 16.384 ms |

La discrepancia entre ejecuciones (15,8–16,4 s) es variación normal del entorno; el orden de magnitud es estable.

## J. Python frente a SQLite

Consultas directas en SQLite: `SELECT` completo ordenado 303 ms; opciones de provincia 50 ms; agrupación de administraciones 78 ms. El resto del tiempo está fuera de SQLite.

`cProfile` confirma que `estadisticas.normalizar_datos` y `_convertir_fecha` dominan: dos pasadas de `Series.map`, aproximadamente 218.858 conversiones por pasada y múltiples llamadas internas a `pandas.to_datetime`. El coste está en conversión/transformación pandas, no en el planner SQLite.

## K–M. EXPLAIN e índices actuales

Planes relevantes:

- SELECT completo: `SCAN oposiciones USING INDEX ix_oposiciones_fecha`.
- Provincias: `SEARCH oposiciones USING COVERING INDEX ix_oposiciones_provincia` + `USE TEMP B-TREE FOR ORDER BY`.
- Agrupación de administraciones: `SCAN oposiciones` + `USE TEMP B-TREE FOR GROUP BY` + `USE TEMP B-TREE FOR ORDER BY`.
- Mapa: `SCAN o USING INDEX ix_oposiciones_municipio_ine`, búsqueda por PK de municipios y B-trees temporales para `GROUP BY`/`ORDER BY`.

Índices de `oposiciones`: fecha, administración, provincia, municipio, publicación, puesto, clave de deduplicación, municipio INE, provincia/comunidad/universidad y municipio histórico. No existe índice sobre `tipo_personal`.

No se creó ningún índice. El filtro de siete valores tiene baja selectividad y las mediciones no justifican modificar el esquema en este paso.

## N–O. Duplicación, agregaciones y payload

- Duplicación demostrada: la estadística principal y la comparación vuelven a leer y normalizar todo el histórico.
- Agregaciones costosas: `GROUP BY` por administración/puesto/provincia/comunidad, ordenaciones de rankings y evolución temporal en pandas.
- El JSON de estadísticas mide 2.085.825 bytes para 109.429 registros de entrada; contiene agregados y evolución, no las filas completas, pero el tamaño sigue siendo mayor que el HTML inicial.
- Mapa: 673.616 bytes; sin coordenadas: 23.604 bytes.

## P. JavaScript y Q. camino crítico

`estadisticas.js` realiza un único `fetch` secuencial a `/api/estadisticas`; no hay varias APIs que puedan paralelizarse. Después procesa rankings y crea siete gráficos Chart.js. Cronología aproximada:

```text
T0 HTML /estadisticas: ~0,2 ms caliente
T1 fetch API
T2 opciones + dos SELECT completos
T3 dos normalizaciones pandas (~12,8 s acumulados)
T4 agregaciones y serialización (~3 s)
T5 JSON recibido; render de gráficos en navegador
```

El camino crítico backend es la conversión repetida de fechas.

## R. Comparación con Oposiciones

Oposiciones trabaja con una página limitada (25 filas) y tarda ~350–500 ms; el mapa agrupa directamente en SQLite y tarda ~280–340 ms; estadísticas carga 109.429 filas dos veces, convierte fechas fila a fila y calcula múltiples agrupaciones pandas, por lo que tarda ~15,8 s.

## S–V. Cuellos de botella y simulaciones

Cuello demostrado principal: doble lectura + doble normalización pandas, especialmente `_convertir_fecha`.

No se modificó una copia con índices ni consultas alternativas en este paso: hacerlo habría dejado de ser diagnóstico puro. Por tanto, no se presenta una mejora experimental ni se recomienda todavía un índice cuantificado.

## W–X. Caché, lazy loading y paralelización

Una caché en memoria con clave `(data_version, filtros)` es técnicamente viable para estadísticas globales y filtros repetidos; se invalidaría naturalmente al cambiar `metadata.data_version`. Riesgos: memoria, procesos múltiples y coherencia tras actualización de SQLite. Debe medirse antes de implementarla.

El HTML ya es prácticamente inmediato. El lazy loading de gráficos podría mejorar el tiempo percibido, pero no reduce el coste backend salvo que se separe el contrato API. No hay varias peticiones frontend independientes que paralelizar.

## Y–AA. Propuestas priorizadas

1. **Alto impacto / riesgo bajo-medio:** reutilizar un único DataFrame normalizado entre estadística principal y comparación de puestos dentro de la misma petición.
2. **Alto impacto / riesgo medio:** vectorizar o cachear la conversión de `Fecha_boe`; conservar exactamente los resultados de fechas históricas.
3. **Medio impacto / riesgo medio:** cachear resultados por `data_version + parámetros` con límites y control de invalidación.
4. **Medio impacto / riesgo medio:** diferir gráficos secundarios o separar payloads si la UX lo requiere.
5. **Bajo impacto / riesgo medio:** estudiar índices sólo mediante copia temporal y benchmark antes/después; no añadir `tipo_personal` por intuición.

Objetivos razonables para Paso 2: HTML <500 ms ya cumplido; API principal <2 s como objetivo inicial; página utilizable <2–3 s si se combina reutilización de DataFrame y carga diferida. No se garantiza <1 s sin nueva medición.

## AB–AC. Plan y riesgos

Paso 2 recomendado: instrumentar una refactorización que comparta el DataFrame normalizado, verificar igualdad byte/lógica de JSON y repetir este benchmark. Paso 3: probar conversión vectorizada. Paso 4: evaluar caché por `data_version`. Cada etapa debe conservar filtros, distribución `tipo_personal`, contratos API y resultados históricos.

## AD–AF. Cierre

- SHA SQLite antes/después: idéntico (`3bef628b733427bd7238848ab6aa9359e7114fa15e5498f617a0523d2df53530`).
- Integridad final: `ok`; claves foráneas: `[]`.
- No se ejecutaron `VACUUM`, `ANALYZE`, DDL ni escrituras.
- No se hizo commit ni push. El árbol conserva los cambios locales previos al profiling; el informe es el único artefacto de este paso.

## AG. Recomendación exacta para Paso 2

Implementar primero la reutilización del DataFrame y de la normalización de fechas entre `calcular_estadisticas_sqlite` y `calcular_comparacion_puestos_sqlite`, con pruebas de equivalencia y benchmark antes/después. No crear índices ni modificar SQLite hasta disponer de una simulación cuantificada.

`RENDIMIENTO WEB PASO 1 COMPLETADO — CUELLOS DE BOTELLA IDENTIFICADOS`
