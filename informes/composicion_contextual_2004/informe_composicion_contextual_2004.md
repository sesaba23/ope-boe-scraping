# Composición contextual histórica XML — 2004

## Resumen

Herencia exclusivamente desde un candidato único del mismo grupo estructural; nunca por distancia textual, entre tablas o tras un encabezado nuevo.

## Resultados antes/después

| Métrica | Extractor anterior | Segmentador | Segmentador + composición |
|---|---:|---:|---:|
| VALIDA | 19 | 18 | 18 |
| VALIDA_PARCIAL | 27 | 44 | 44 |
| NO_UTILIZABLE | 3 | 6 | 6 |
| filas_con_puesto | 23 | 22 | 22 |
| filas_con_num_plazas | 42 | 58 | 58 |
| filas_con_ambos | 19 | 18 | 18 |
| publicaciones_con_alguna_valida | 16 | 9 | 9 |

## Herencias realizadas

Herencias tentativas registradas: 0. Nuevas filas válidas aceptadas tras revisión manual: 0.

## Herencias rechazadas

Contextos ambiguos rechazados: 14. No se cruza un grupo, tabla o encabezado nuevo.

## Nuevas filas válidas

Ninguna: se prioriza no introducir falsos positivos.

## Falsos positivos

Se rechazaron encabezados narrativos y la tabla jerárquica de BOE-A-2004-3891.

## Tablas jerárquicas

Bloques de datos: {'PARRAFO': 51, 'TABLA': 11}. La herencia de tabla exige una celda de puesto estructuralmente vacía.

## Distribuciones textuales

Los componentes solo heredan en el mismo grupo y con un candidato único.

## Efecto sobre reconciliación

El resultado permanece igual en las tres fases: 1 `TOTAL_DESGLOSADO` y 29 `SIN_RECONCILIACION`. No se añadieron reglas al reconciliador.


## Limitaciones

BOE-A-2004-3891, BOE-A-2004-3826, BOE-A-2004-6777, BOE-A-2004-10220 y BOE-A-2004-14618 siguen requiriendo composición estructural de tablas o subcupos.

## Recomendación

Mantener como diagnóstico experimental. Antes de integrar, representar estructura de columnas/celdas y límites de sección XML.
