# Rendimiento web — Paso 4B: auditoría funcional de filtros y recuentos

Fecha de la auditoría: 2026-09-25
Base consultada: `datos/boe.db` (solo lectura)

## A. Caso reproducido

La petición exacta fue:

`GET /api/estadisticas?puesto=Ingeniero%20T%C3%A9cnico%20Industrial`

El valor que se veía como **2** era `resumen.total_plazas`, renderizado por
`static/js/estadisticas.js` en `#total-plazas`. `calcular_estadisticas()` lo
calcula como `Num_plazas_num.sum()` sobre el DataFrame filtrado; no es el número
de oposiciones. En la respuesta también existe `resumen.total_registros`.

## B. Referencia SQL y reconciliación

El filtro productivo divide el texto en palabras y aplica, para cada una,
`lower(puesto) LIKE lower('%palabra%')`. La misma semántica se aplicó en SQL:

| Métrica | Resultado |
|---|---:|
| `COUNT(*)` (oposiciones) | 536 |
| `SUM(num_plazas)` | 803 |
| `COUNT(num_plazas)` | 536 |
| `num_plazas IS NULL` | 0 |
| `num_plazas` no nulo | 536 |
| fecha mínima / máxima | 2004-03-15 / 2026-09-12 |

La API corregida devuelve exactamente `total_registros=536` y
`total_plazas=803`. La gráfica `evolucion_anual` suma la misma columna y
reconcilia con SQL año a año: 2004: 6, 2005: 34, 2006: 20, 2007: 17,
2008: 16, 2009: 7, 2010: 21, 2011: 13, 2012: 5, 2013: 5, 2014: 3,
2015: 4, 2016: 6, 2017: 4, 2018: 23, 2019: 26, 2020: 10, 2021: 45,
2022: 126, 2023: 106, 2024: 69, 2025: 95 y 2026: 142.

`plazas_por_mes` también usa `Num_plazas_num.sum()`. En el universo corregido
los totales mensuales son: enero 69, febrero 83, marzo 97, abril 30, mayo 99,
junio 78, julio 42, agosto 40, septiembre 45, octubre 41, noviembre 58 y
diciembre 121 (suman 803).

## C. Registros inspeccionados

Una muestra de las primeras filas SQL (orden `fecha_boe, oposicion_id`) es:

| oposicion_id | fecha | puesto | num_plazas | administración | provincia | tipo_personal |
|---:|---|---|---:|---|---|---|
| 2526 | 2004-03-15 | Ingeniero Técnico Industrial | 1 | Diputación Provincial de Zaragoza | Zaragoza | No determinado |
| 3102 | 2004-06-02 | Ingeniero Técnico Industrial | 1 | Ayuntamiento de Sagunto (Valencia) | Valencia/València | No determinado |
| 3384 | 2004-07-20 | Ingeniero Técnico Industrial | 1 | Ayuntamiento de Mislata (Valencia) | Valencia/València | Funcionario |
| 3726 | 2004-10-05 | Ingeniero Técnico Industrial | 1 | Ayuntamiento de Guardamar del Segura (Alicante) | Alicante/Alacant | Funcionario |
| 3755 | 2004-10-08 | Ingeniero Técnico Industrial | 1 | Ayuntamiento de San Martín de la Vega (Madrid) | Madrid | Funcionario |

No hay nulos de `num_plazas` en las 536 coincidencias. El valor de puesto
visible puede aparecer con variantes ortográficas/normalizadas en la base,
pero el filtro productivo se realiza sobre `puesto` bruto.

## D. Causa raíz

El Paso 4 pasó a cargar un DataFrame compartido. El resumen recibía
`filtrar_datos(..., modo_sql=True)`, mientras que la serie comparativa llamaba
`filtrar_datos()` sin ese modo. El modo por defecto elimina diacríticos y, por
tanto, seleccionaba un universo distinto (538 filas en la comprobación
intermedia); el resumen y la gráfica parecían incompatibles. No hubo mutación
del DataFrame compartido: las funciones trabajan con máscaras, columnas
auxiliares y copias locales para las series.

La corrección mínima y general es que `calcular_comparacion_puestos()` use
`modo_sql=True` para el puesto principal y que el modo SQL conserve los
diacríticos del término de búsqueda y solo haga `casefold`, igual que SQLite.
No se añadió ninguna excepción para este puesto ni se introdujo caché.

La comparación del código previo mediante `git diff` muestra que la
divergencia apareció al refactorizar la ruta web hacia el DataFrame compartido
del Paso 4; la ruta SQLite anterior aplicaba una única semántica.

## E. Invariantes y regresión

Se añadieron tests unitarios con un fixture pequeño que comprueba:

* `sum(evolucion_anual) == resumen.total_plazas` cuando representan el mismo
  universo;
* `sum(evolucion_anual_puestos.series[0].values) == total_plazas`;
* el modo SQL no convierte `Técnico` en `Tecnico` y, por tanto, reproduce el
  filtro productivo.

La suite focalizada (estadísticas, web, consultas y filtros relacionados)
termina en **207 passed**.

## F. Otros filtros, hashes y rendimiento

Se probaron puestos frecuentes, fechas, tipo de personal y combinaciones. Las
peticiones responden 200 y sus recuentos son internamente consistentes. El
hash de la respuesta por puesto cambia respecto al resultado erróneo anterior,
como corresponde a la corrección; el hash por defecto observado en este árbol
es `c38fce950c032228c3a65908450f4761b12b26dec0e59d0382bf337589ebb2d7` y no
se altera por esta corrección (la referencia histórica suministrada
`f12eb3b5...` pertenece a otro estado de trabajo). No se usa el hash como
oráculo de una respuesta que contenía el bug.

Mediciones puntuales tras la corrección: petición sin filtro ~1976 ms,
`Ingeniero Técnico Industrial` ~1064 ms y `Ingeniero` ~993 ms. La pequeña
variación frente a la medición previa no procede de caché y se priorizó la
equivalencia funcional.

## G. Integridad de datos

SQLite no se modificó. SHA-256 antes/después:

`3bef628b733427bd7238848ab6aa9359e7114fa15e5498f617a0523d2df53530`

Tamaño: 170123264 bytes; `schema_version=7`, `data_version=78`,
`tipo_personal_version=tipo-personal-v1`, `integrity_check=ok` y
`foreign_key_check=[]`.

Conclusión: el “2” no representaba dos convocatorias perdidas. Era una suma
calculada sobre un subconjunto producido por una semántica distinta; tras la
corrección, las tarjetas, la evolución anual y la serie del puesto representan
las mismas 536 oposiciones y 803 plazas.
