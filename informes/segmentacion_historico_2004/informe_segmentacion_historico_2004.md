# Segmentación estructural histórica XML — 2004

## Resumen

Muestra: 30 documentos, la misma de la validación final del reconciliador. Bloques detectados: **62** (párrafos: **51**; tablas: **11**).

## Diseño del segmentador

Recorre XML en orden, preserva párrafos y tablas; produce bloques con origen, posición, campos y evidencias locales. Solo considera válida una fila con Puesto y Num_plazas.

## Muestra utilizada

BOE-A-2004-10041, BOE-A-2004-10218, BOE-A-2004-11125, BOE-A-2004-8501, BOE-A-2004-17768, BOE-A-2004-8225, BOE-A-2004-14618, BOE-A-2004-4911, BOE-A-2004-6777, BOE-A-2004-16964, BOE-A-2004-599, BOE-A-2004-6695, BOE-A-2004-10220, BOE-A-2004-603, BOE-A-2004-1938, BOE-A-2004-2476, BOE-A-2004-3113, BOE-A-2004-3826, BOE-A-2004-3891, BOE-A-2004-6696, BOE-A-2004-12789, BOE-A-2004-12790, BOE-A-2004-14961, BOE-A-2004-16452, BOE-A-2004-20342, BOE-A-2004-21227, BOE-A-2004-78, BOE-A-2004-12319, BOE-A-2004-14746, BOE-A-2004-15716

## Resultados antes/después

| Métrica | Antes | Después |
|---|---:|---:|
| VALIDA | 19 | 18 |
| VALIDA_PARCIAL | 27 | 44 |
| NO_UTILIZABLE | 3 | 6 |
| filas_con_puesto | 23 | 22 |
| filas_con_num_plazas | 42 | 58 |
| filas_con_ambos | 19 | 18 |
| publicaciones_con_alguna_valida | 16 | 9 |

## Convocatorias válidas

Una convocatoria es válida exclusivamente si `Puesto` y `Num_plazas` disponen de evidencia local. Turno, sistema, escala, subescala y clase no intervienen en esta clasificación.

## Tablas

Bloques de tabla: 11. Se usan solo columnas con encabezados explícitos; las filas `Total` y etiquetas genéricas no se tratan como puesto.

## Secuencias de párrafos

Se reconocen expresiones explícitas `N plazas de Puesto` y encabezados verticales breves seguidos de una cantidad etiquetada. Las asociaciones sin denominación local quedan parciales.

## Cantidades escritas

Se admiten `1`, `1.250`, `1 250` y palabras controladas, incluido `tres mil veintiocho`. No se convierten años, artículos o códigos porque se exige contexto de plazas.

## Campos opcionales

| Campo | Antes | Después |
|---|---:|---:|
| Turno | 14 | 9 |
| Sistema | 15 | 3 |
| Escala | 10 | 8 |
| Subescala | 9 | 6 |
| Clase | 0 | 0 |

## Errores de asociación y falsos positivos

- `BOE-A-2004-14618`: La reserva "1 plaza de la Sección" aporta cantidad pero no una denominación de puesto inequívoca; se mantiene como parcial.
- `BOE-A-2004-10220`: Las secciones y reservas se segmentan, pero deben pasar por reconciliación de subcupos antes de emitirse como convocatorias independientes.
- `BOE-A-2004-3891`: La tabla contiene cuerpos y una fila Total; se excluyen Total y etiquetas genéricas, pero el contexto de Ejército/Cuerpo requiere composición tabular adicional.

## Casos todavía no resueltos

`BOE-A-2004-6777` (miles y distribución en texto), `BOE-A-2004-3826` (desglose por clases), y las tablas compuestas como `BOE-A-2004-3891` requieren una fase posterior de composición contextual.

## Efecto sobre el reconciliador

Antes: {'TOTAL_DESGLOSADO': 1, 'SIN_RECONCILIACION': 29}. Después: {'TOTAL_DESGLOSADO': 1, 'SIN_RECONCILIACION': 29}. No se ampliaron sus reglas. La segmentación no convierte automáticamente totales y componentes en filas; por tanto no cambió decisiones confirmadas.

## Recomendaciones

Mantener el segmentador como auditoría experimental. La calidad Puesto+Num_plazas mejora en estructuras explícitas, pero deben resolverse la composición de tablas y el enlace de componentes/subcupos antes de utilizar sus filas para escritura histórica.
