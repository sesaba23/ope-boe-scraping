# TIPO_PERSONAL WEB — revisión de filtros responsive y distribución estadística

## Estado y alcance

Estado inicial conservado: rama `main`, HEAD `97a63db025975623c8614854607afc4f0d868385`,
tag `v5.2.0`, con los cambios locales previos de Rendimiento Pasos 2–4B.
No se modificaron `tipo_personal.py`, SQLite, clasificaciones ni el pipeline.

Se auditaron `templates/oposiciones.html`, `templates/estadisticas.html`,
`static/css/portal.css`, `static/css/estadisticas.css`,
`static/js/estadisticas.js`, `static/js/oposiciones_mapa.js`,
`web_estadisticas.py`, `estadisticas.py`, `consultas_boe.py` y sus tests.

## Filtros responsive

Oposiciones ya generaba siete `input[type=checkbox]` con el mismo nombre
`tipo_personal`; Estadísticas los construía dinámicamente desde
`opciones.tipos_personal`. El problema visual era que no existía una regla
compartida para ese grupo: en Estadísticas el `input` genérico heredaba
`width: 100%` y `min-height: 44px`, y en Oposiciones el grupo carecía de un
layout específico.

Se añadió un grupo visual común basado en CSS Grid (`filter-choice-grid`) con
`auto-fit/minmax`, separación compacta, labels completos clicables y un
checkbox explícitamente dimensionado. El fieldset de Estadísticas ocupa la
fila completa; en Oposiciones conserva su estructura y persistencia de
selección. No se fijan tres columnas rígidas: el grid se adapta al espacio.

La solución funciona con los breakpoints existentes del proyecto (menú 960,
tablet 840 y responsive general 720); no se añadió ningún breakpoint nuevo.
En escritorio aprovecha el ancho disponible, en tablet reorganiza las opciones
y en móvil reduce columnas hasta una disposición vertical. No se usa
`overflow-x`, no se cortan labels y no se separan controles de sus labels.

## Causa de la distribución rota

La cadena backend era correcta: SQLite → `cargar_datos_estadisticas_sqlite`
→ `calcular_estadisticas` → `distribucion_tipo_personal` → JSON. El campo se
emitía como una lista estable de siete objetos:

```json
{"tipo_personal": "Funcionario", "registros": 55961}
```

El frontend reutilizaba `renderizarRanking`, cuyo contrato visual espera la
medida en la propiedad `plazas`. Por tanto `Number(undefined)` producía barras
y valores no utilizables aunque el JSON contuviera los datos correctos. La
corrección mínima mantiene el contrato backend y adapta explícitamente
`registros` a `plazas` antes de renderizar. Se conserva el orden oficial y se
mantienen las siete categorías, incluidas las de valor cero.

## Reconciliación productiva

SQLite permanece intacta. La consulta directa devuelve:

| Tipo | Registros |
|---|---:|
| Funcionario | 55.961 |
| Laboral | 18.216 |
| Estatutario | 1 |
| Universitario | 2.900 |
| Militar | 1 |
| Otros | 1 |
| No determinado | 32.349 |
| **Total** | **109.429** |

`GET /api/estadisticas` devuelve exactamente esa distribución y la suma del
campo `registros` es 109.429. Con `tipo_personal=Funcionario` la distribución
conserva las siete categorías y solo Funcionario tiene valor 55.961. Las
selecciones múltiples usan parámetros GET repetidos y aplican OR, por ejemplo:
`tipo_personal=Funcionario&tipo_personal=Laboral`.

También se comprobaron puesto, fechas, tipo de personal y combinaciones de
estos filtros. La distribución siempre se calcula sobre el mismo universo que
las tarjetas y el resto de estadísticas.

## Accesibilidad y persistencia

Se mantienen elementos checkbox reales, asociación label/input, foco visible,
teclado, contraste y las categorías oficiales. Oposiciones conserva la
selección en la plantilla y sus parámetros repetidos en paginación, mapa,
detalle y exportación; Estadísticas reconstruye las casillas desde la lista
devuelta por el API y reaplica `checked` según `filtros.tipo_personal`.

## Validación

* `node --check static/js/estadisticas.js`: correcto.
* Tests focalizados de estadísticas, web y tipo de personal: **161 passed**.
* Se añadieron tests de catálogo estable, suma de distribución, filtros
  simples/múltiples, contrato JSON y clases del grupo compacto.
* `git diff --check`: correcto.
* Benchmark de cinco peticiones globales a `/api/estadisticas`: tiempos
  2004,7 / 1820,9 / 1826,1 / 1787,6 / 1839,7 ms; mediana **1826,1 ms**.

## Integridad SQLite

SHA-256 antes/después:

`3bef628b733427bd7238848ab6aa9359e7114fa15e5498f617a0523d2df53530`

Metadata: `schema_version=7`, `data_version=78`,
`tipo_personal_version=tipo-personal-v1`; `PRAGMA integrity_check` devuelve
`ok` y `PRAGMA foreign_key_check` devuelve `[]`.

No quedan incidencias funcionales de esta revisión. Rendimiento Paso 5 puede
continuar, manteniendo fuera de alcance cualquier caché hasta su propia
auditoría.
