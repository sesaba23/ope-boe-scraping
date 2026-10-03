# Rendimiento Web — Paso 5: caché en memoria por `data_version`

## Estado y referencia

Rama `main`, HEAD inicial `25e3242a98727157e3db5a6687c8a99a17d7e959`,
sin diferencia con `origin/main`. Los únicos cambios locales iniciales eran
un JSON de auditoría generado y los informes no rastreados de
`informes/rendimiento_web/`; permanecen fuera del alcance.

Antes de modificar código, cinco peticiones globales sin caché midieron
2349,74 / 1702,37 / 1693,88 / 1717,60 / 1692,27 ms. Mínimo 1692,27,
máximo 2349,74, media 1831,17 y mediana **1702,37 ms**. El SHA-256 de los
bytes JSON fue
`c38fce950c032228c3a65908450f4761b12b26dec0e59d0382bf337589ebb2d7`.

El flujo previo validaba parámetros GET, leía opciones de filtros, cargaba
`oposiciones` mediante `cargar_datos_estadisticas_sqlite`, preparaba el
DataFrame, filtraba el puesto, calculaba estadísticas y comparación, leía
metadata y finalmente serializaba con `jsonify`. La distribución de
`tipo_personal` se calcula dentro de `calcular_estadisticas`.

La lectura directa y de solo lectura de `metadata.data_version` costó,
antes del cambio, entre 0,23 y 0,68 ms (mediana 0,24 ms) en diez lecturas.
La nueva función `obtener_data_version` consulta solo esa fila y no carga
`oposiciones` ni crea un DataFrame.

## Diseño

La caché pertenece a cada instancia Flask y solo se usa en
`/api/estadisticas`. Es un `OrderedDict` LRU protegido por `RLock`, con un
límite de **8 entradas**. La respuesta global serializada ocupa 2.085.825
bytes (unos 1,99 MiB), así que ocho entradas de ese tamaño sumarían unos
15,9 MiB de payload, más la sobrecarga pequeña de claves y contenedor.
Las respuestas filtradas tienen tamaño similar porque incluyen las opciones
del formulario. La caché no retiene DataFrames.

Se guardan bytes JSON inmutables, no estructuras Python mutables. Para la
misma lista de `tipo_personal`, el HIT devuelve directamente los bytes
almacenados. Para un orden o duplicado diferente con el mismo filtro OR,
decodifica el JSON, sustituye solo `filtros.tipo_personal` por la lista
recibida y vuelve a serializar, preservando el contrato observable. Los
contadores internos `hits` y `misses` permiten observación y tests sin
modificar el JSON público. `limpiar()` reinicia el estado para tests.

Guardar el diccionario Python habría evitado una decodificación excepcional,
pero exigiría proteger copias mutables y serializar en cada HIT. Se eligió
JSON ya serializado porque los HIT habituales evitan también ese coste y los
bytes de la entrada no pueden modificarse accidentalmente.

La clave estructurada es:

`(data_version, fecha_inicio, fecha_final, puesto, provincia, ambito, sistema,
turno, tuple(sorted(set(tipo_personal))), tuple(comparadores))`.

Los parámetros sin efecto se ignoran como antes. Fechas inválidas, rangos
invertidos y comparadores incompatibles se rechazan antes de consultar la
caché. Los valores de puesto permanecen literales: no se eliminan acentos,
no se cambian mayúsculas y no se recortan. Los comparadores conservan el
orden porque ese orden afecta a las series. `tipo_personal` se ordena y
deduplica solo en la clave porque el filtro SQL usa `IN` y tiene semántica OR.
Los errores de carga tampoco se guardan.

Si se observa una versión mayor, se eliminan todas las entradas anteriores.
Una operación iniciada con una versión más antigua no puede reintroducirlas
tras la actualización. El `RLock` protege accesos, expulsiones y limpieza;
dos MISS simultáneos pueden repetir el cálculo, sin corromper la caché. Cada
worker tiene su propia caché; al reiniciar, empieza vacía. Se asume la
política productiva existente de incrementar `data_version` cuando cambian
los datos.

El repositorio no fija un número de workers ni un servidor de despliegue;
la protección con `RLock` cubre peticiones concurrentes dentro de un proceso.

## Benchmark posterior

Cinco MISS controlados (limpieza antes de cada uno): 1863,50 / 1702,62 /
1683,91 / 1693,24 / 1707,85 ms. Mínimo 1683,91, máximo 1863,50,
media 1730,23 y mediana **1702,62 ms**, prácticamente igual al baseline.

Diez HIT: 0,98 / 0,47 / 0,46 / 0,45 / 0,41 / 0,41 / 0,41 / 0,40 /
0,39 / 0,38 ms. Mínimo 0,38, máximo 0,98, media 0,48 y mediana
**0,41 ms**. La mejora de la mediana HIT frente a la referencia es de
aproximadamente **4162×**. La lectura de versión posterior tuvo mediana
0,26 ms en diez ejecuciones.

## Equivalencia e invariantes

Los cinco MISS y diez HIT globales produjeron exactamente el mismo SHA-256
del baseline: `c38fce950c032228c3a65908450f4761b12b26dec0e59d0382bf337589ebb2d7`.

Con `puesto=Ingeniero Técnico Industrial`, MISS y HIT conservan 536
oposiciones, 803 plazas, suma anual 803 y suma de la serie comparativa 803;
SQL directo confirma 0 `num_plazas` nulos. La distribución global conserva
las siete categorías y suma 109.429 registros. La selección simple de
Funcionario reconcilia con SQL; Funcionario+Laboral y el orden inverso
comparten cálculo y conservan los parámetros GET repetidos en `filtros`.

## Tests e integridad

Los tests nuevos cubren clave estructurada, filtros distintos, orden y
duplicados multivalor, MISS/HIT, trabajo pesado evitado en HIT, invalidación
78→79, limpieza de versiones, límite de ocho entradas, LRU real, bytes
inmutables, reset, errores no cacheados e invariantes productivas.

La selección ampliada anterior a los dos últimos tests nuevos terminó en
**500 passed** con `-W error::FutureWarning`; los tests nuevos aislados
terminaron en **15 passed** con el mismo modo estricto. La suite completa
posterior a todos los cambios terminó en **1563 passed, 0 failed, 0 warnings**
en 35 min 20 s.

SQLite productiva sigue sin cambios: SHA-256
`3bef628b733427bd7238848ab6aa9359e7114fa15e5498f617a0523d2df53530`,
`schema_version=7`, `data_version=78`,
`tipo_personal_version=tipo-personal-v1`, integridad `ok` y claves foráneas
sin errores. Se repitieron estas comprobaciones tras la suite completa.

`git diff --check` termina sin errores. La rama sigue siendo `main`, HEAD
sigue en `25e3242a98727157e3db5a6687c8a99a17d7e959` y no se hizo
commit ni push. Los archivos de este paso son `cache_estadisticas.py`,
`consultas_boe.py`, `web_estadisticas.py`, `tests/test_cache_estadisticas.py`
y este informe. El JSON de auditoría que ya estaba modificado y los demás
informes locales no rastreados permanecen sin tocar.

Limitación deliberada: la caché es local a cada proceso y no evita que dos
MISS concurrentes calculen la misma consulta. El siguiente paso razonable es
observar el comportamiento en el despliegue real antes de ampliar la caché
a otras rutas.
