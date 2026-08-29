# Estructura histórica XML — 2004

## Resumen

Se conservan celdas y relaciones XML sin relajar validez. No se emitieron nuevas filas válidas.

## Modelo estructural

Celdas: texto, fila/columna original, rowspan, colspan, heredada y celda origen. Filas: grupo padre, nivel y marca de grupo. Bloques: section_id, parent_section y bloque padre.

## Rowspan/colspan

Las pruebas verifican preservación y herencia solo cuando la celda XML demuestra un padre.

## Resultados antes/después

| Métrica | Antes | Después |
|---|---:|---:|
| VALIDA | 18 | 18 |
| VALIDA_PARCIAL | 44 | 44 |
| NO_UTILIZABLE | 6 | 6 |
| filas_con_puesto | 22 | 22 |
| filas_con_num_plazas | 58 | 58 |
| filas_con_ambos | 18 | 18 |
| publicaciones_con_alguna_valida | 9 | 9 |

## Nuevas válidas

0. Todas las candidatas estructurales permanecen parciales por falta de relación padre/hijo demostrable.

## Herencias estructurales

Aceptadas: 0. Rechazadas: 14.

## Casos dudosos

- BOE-A-2004-3891: tabla jerárquica Ejército/Cuerpo sin padre inequívoco.
- BOE-A-2004-3826: desglose por clases no compuesto.
- BOE-A-2004-6777: asociación textual pendiente.
- BOE-A-2004-10220 y BOE-A-2004-14618: subcupos sin contención estructural.

## Efecto sobre reconciliación

Sin cambios: 1 TOTAL_DESGLOSADO y 29 SIN_RECONCILIACION.

## Recomendación

No integrar. Requiere una fase futura de composición de encabezados multinivel y tablas XML específicas.
