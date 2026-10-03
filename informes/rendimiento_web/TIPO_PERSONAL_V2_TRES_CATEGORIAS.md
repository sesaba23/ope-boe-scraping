# TIPO_PERSONAL v2 — tres categorías

## Estado inicial y alcance

El trabajo partió de `main`, HEAD `25e3242a98727157e3db5a6687c8a99a17d7e959`, con cambios locales no commiteados del Paso 5 de rendimiento web. Se preservaron esos cambios y el informe de auditoría preexistente.

La SQLite inicial era byte a byte `3bef628b733427bd7238848ab6aa9359e7114fa15e5498f617a0523d2df53530`, con `schema_version=7`, `data_version=78`, `tipo_personal_version=tipo-personal-v1`, `integrity_check=ok` y `foreign_key_check=[]`.

## Diseño v2

El contrato productivo queda en el orden estable: `Funcionario`, `Laboral`, `Otros`.

La implementación conserva las reglas y `familias_detectadas` internas para provenance. La categoría final conserva `Funcionario` y `Laboral`; `Universitario`, `Militar`, `Estatutario`, el antiguo `Otros` y `No determinado` se exponen como `Otros`. La precedencia existente se mantiene: primero se respetan las excepciones de sector universitario y las filas mixtas; después militar/estatutario; luego laboral explícito y finalmente funcionario. Una fila laboral y funcionarial simultánea conserva el resultado v1 `No determinado`, que ahora se persiste como `Otros`.

`No determinado` ya no puede ser resultado público ni valor persistido. Las familias antiguas pueden aparecer sólo en `familias_detectadas` y reglas, como evidencia explicativa.

## Migración explícita

Se añadió el remapeo v1→v2 en `migrar_tipo_personal.py`. No se volvió a reclasificar el histórico: se transformó exclusivamente el valor persistido.

| Categoría | v1 | v2 esperado | v2 real |
|---|---:|---:|---:|
| Funcionario | 55.961 | 55.961 | 55.961 |
| Laboral | 18.216 | 18.216 | 18.216 |
| Otros | 1 | 35.252 | 35.252 |
| Estatutario + Universitario + Militar + No determinado | 35.251 | — | — |
| **Total** | **109.429** | **109.429** | **109.429** |

Antes de tocar la productiva se copió la base a una ruta temporal y se ejecutó dry-run, migración, validación e idempotencia. La copia dio exactamente `Funcionario=55961`, `Laboral=18216`, `Otros=35252`, `data_version 78→79`, versión v2, integridad correcta y segunda ejecución sin cambios.

La productiva creó el backup `backups/sqlite/boe_20261002_172250_899171.db`.

Resultado productivo:

- SHA antes: `3bef628b733427bd7238848ab6aa9359e7114fa15e5498f617a0523d2df53530`.
- SHA después: `d428fb83b536a99057607d4fe8d27c318bfa841c3f40273d0b0ff5d1a1adfcb1`.
- Tamaño: 170.123.264 bytes antes y después.
- `schema_version=7`, `data_version=78→79`.
- `tipo_personal_version=tipo-personal-v1→tipo-personal-v2`.
- Integridad `ok`; claves foráneas `[]`.

La base final tiene exactamente 109.429 filas, la suma agrupada también es 109.429 y `DISTINCT tipo_personal` sólo devuelve `Funcionario`, `Laboral` y `Otros`.

Los cambios cubren el clasificador y su migración (`tipo_personal.py`, `migrar_tipo_personal.py`, `migrar_excel_sqlite.py`), consultas/estadísticas (`consultas_boe.py`, `estadisticas.py`, `web_estadisticas.py`), los tres checkboxes y el detalle (`templates/oposiciones.html`, `templates/detalle_oposicion.html`, `static/js/estadisticas.js`) y sus tests. Las exportaciones y el mapa reutilizan el mismo filtro validado por `consultas_boe.py`, por lo que reciben el catálogo v2 sin rutas paralelas.

## Aplicación web y caché

Oposiciones y Estadísticas muestran sólo tres casillas, conservan parámetros GET repetidos y semántica OR. La distribución estadística siempre devuelve las tres categorías, incluso con ceros. Los filtros antiguos `Estatutario`, `Universitario`, `Militar` y `No determinado` responden 400; no se traducen silenciosamente a `Otros`.

La caché del Paso 5 sigue usando `data_version` en la clave. Tras la migración la versión 79 impide reutilizar cualquier entrada v1; las pruebas de cambio de versión y las consultas v2 confirman MISS inicial y HIT posterior. El orden y duplicados multivalor siguen canonicalizados.

Post-v2, cinco MISS de `/api/estadisticas` midieron 1697,425–1847,382 ms, media 1742,706 y mediana **1716,825 ms**. Diez HIT midieron 0,388–0,701 ms, media 0,443 y mediana **0,402 ms**. Todas las respuestas globales MISS/HIT produjeron el SHA JSON v2 `7d4b15609e998c63b2cb93303811d24663e73e9ef1e8f6cc97d433adbe5ecbdd`.

La selección `Ingeniero Técnico Industrial` conserva 536 oposiciones, 803 plazas, suma anual 803 y suma de serie comparativa 803, tanto en MISS como en HIT. Las selecciones simples dan 55.961, 18.216 y 35.252; las combinaciones OR dan 91.213, 53.468 y 109.429 para Funcionario+Otros, Laboral+Otros y las tres categorías.

## Tests

Se actualizaron tests unitarios del clasificador, pipeline, migración, consultas, estadísticas, web y caché. La batería focalizada con `-W error::FutureWarning` terminó en **261 passed**. Incluye migración en copia, idempotencia, catálogo de tres, valores antiguos rechazados, valores cero, multiselección, caché MISS/HIT/LRU/invalidez y las invariantes 536/803.

La suite completa `pytest -q` terminó con **1563 passed, 0 failed, 0 warnings** en 35 min 13 s. `git diff --check` termina sin errores. No se ha hecho commit ni push.

## Referencias antiguas justificadas

Las cadenas antiguas permanecen únicamente en reglas internas y provenance del clasificador, en el remapeo explícito v1→v2, en snapshots/auditorías históricas y en tests que prueban la migración o que las antiguas URLs son inválidas. No forman parte del catálogo, filtros, valores persistidos ni distribución web actuales.
