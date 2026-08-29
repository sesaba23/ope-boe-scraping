# Validación final del reconciliador histórico XML (2004)

## Resumen ejecutivo

Muestra determinista: **30** publicaciones de las 518 con evidencia estructural; incluye `BOE-A-2004-10041`. Se descargó una vez el XML de cada una; no se recorrieron las 5.260 publicaciones.

Relaciones documentales reales: **10**. Detectadas correctamente: **1**. Falsos negativos: **9**. Falsos positivos: **0**. Precisión: **100%**; cobertura: **10%**.

La precisión procede de una sola detección positiva y no es representativa; la cobertura sí evidencia que el reconciliador aún no cubre familias frecuentes.

## Selección de la muestra

puntuación determinista de evidencia estructural y selección codiciosa con máximo de tres documentos por mes y cuatro por departamento; se preservó diversidad de fecha, órgano y formato.

## Clasificación documental

| Clase | Casos |
|---|---:|
| AMBIGUO | 3 |
| CANTIDADES_INDEPENDIENTES | 6 |
| NO_HAY_RELACION_RELEVANTE | 11 |
| RELACION_TOTAL_DESGLOSE | 6 |
| SUBCUPO | 2 |
| VARIAS_DISTRIBUCIONES | 2 |

## Resultados del reconciliador

| Resultado | Casos |
|---|---:|
| AMBIGUO_CORRECTAMENTE | 3 |
| CORRECTO | 18 |
| FALSO_NEGATIVO | 9 |

## Falsos positivos

No se observó ninguno: el único `TOTAL_DESGLOSADO` automático (`BOE-A-2004-10041`) corresponde a un desglose real 100 = 50 + 50.

## Falsos negativos

### BOE-A-2004-10218

- Relación real: `RELACION_TOTAL_DESGLOSE`; decisión automática: `AMBIGUO`.
- Cantidades: [5] (total), [8, 7] (componentes), [] (subcupos etiquetados).
- Motivo: La distribución 38/37 se expresa en palabras y la detección recuperó cantidades ajenas (5, 8 y 7), por lo que no pudo validar la suma.

### BOE-A-2004-17768

- Relación real: `VARIAS_DISTRIBUCIONES`; decisión automática: `SIN_RECONCILIACION`.
- Cantidades: [] (total), [24, 3, 21, 2] (componentes), [] (subcupos etiquetados).
- Motivo: Dos distribuciones consecutivas 28=24+3+1 y 24=21+2+1; el agrupamiento no delimita ambas series.

### BOE-A-2004-6777

- Relación real: `RELACION_TOTAL_DESGLOSE`; decisión automática: `SIN_RECONCILIACION`.
- Cantidades: [] (total), [] (componentes), [] (subcupos etiquetados).
- Motivo: El total y los componentes usan miles en palabras y cifra entre paréntesis (3.028), formato no convertido a cantidades conciliables.

### BOE-A-2004-16964

- Relación real: `VARIAS_DISTRIBUCIONES`; decisión automática: `SIN_RECONCILIACION`.
- Cantidades: [] (total), [] (componentes), [] (subcupos etiquetados).
- Motivo: Varias distribuciones anidadas de plazas de formación; faltan límites de grupo y asociación estable de cada total.

### BOE-A-2004-2476

- Relación real: `SUBCUPO`; decisión automática: `SIN_RECONCILIACION`.
- Cantidades: [6] (total), [] (componentes), [] (subcupos etiquetados).
- Motivo: La plaza de reserva es un subcupo del total, pero no queda vinculada estructuralmente al total detectado.

### BOE-A-2004-3826

- Relación real: `RELACION_TOTAL_DESGLOSE`; decisión automática: `SIN_RECONCILIACION`.
- Cantidades: [39] (total), [] (componentes), [] (subcupos etiquetados).
- Motivo: El desglose por clases aparece en tabla y el lector textual no recupera sus componentes.

### BOE-A-2004-3891

- Relación real: `RELACION_TOTAL_DESGLOSE`; decisión automática: `SIN_RECONCILIACION`.
- Cantidades: [237] (total), [] (componentes), [] (subcupos etiquetados).
- Motivo: El total precede a un desglose tabular por Ejército/Cuerpo; los componentes de tabla no llegan al reconciliador.

### BOE-A-2004-12790

- Relación real: `RELACION_TOTAL_DESGLOSE`; decisión automática: `SIN_RECONCILIACION`.
- Cantidades: [5] (total), [] (componentes), [] (subcupos etiquetados).
- Motivo: El total de cinco plazas se materializa en cinco filas/tablas unitarias sin una relación textual explícita.

### BOE-A-2004-14746

- Relación real: `SUBCUPO`; decisión automática: `SIN_RECONCILIACION`.
- Cantidades: [] (total), [] (componentes), [] (subcupos etiquetados).
- Motivo: La reserva de una plaza se reconoce como cantidad, pero no se etiqueta ni vincula explícitamente como subcupo.

## Subcupos

Se documentaron 2 subcupos reales (`BOE-A-2004-2476`, `BOE-A-2004-14746`). Ninguno quedó etiquetado explícitamente por el reconciliador. En ambos casos el resultado final no añadió una fila independiente para el subcupo, por lo que no se constató doble conteo en las filas emitidas.

## Dobles conteos

No se observó doble conteo material en las filas posteriores a la reconciliación. Existe riesgo latente cuando un subcupo se detecta como cantidad funcional sin vínculo explícito; debe revisarse antes de automatizar escrituras.

## Pérdidas potenciales

Hay **9** relaciones reales no conciliadas. No implican necesariamente pérdida de una fila —varias dependen de tablas que el extractor aún no transforma—, pero sí impiden demostrar que totales y componentes no se dupliquen o se pierdan.

## Estado del extractor histórico

Filas completas (los siete campos funcionales presentes): **0**. Filas parciales: **40**. Publicaciones sin fila: **3**.

Campos ausentes por frecuencia: `Clase` (40), `Subescala` (32), `Escala` (30), `Turno` (26), `Sistema` (24), `Puesto` (19), `Num_plazas` (6).

## Reglas añadidas

Ninguna. Aunque las familias de tablas, cifras en palabras/miles y distribuciones múltiples se repiten, resolverlas exige antes una representación estructurada de tabla y asociación de contexto; una regex de reconciliación aislada sería arriesgada.

## Comparación antes/después

No aplica: no se modificó el reconciliador durante esta validación.

## Recomendación de integración

- ¿Es suficientemente seguro para integrarlo en un extractor histórico? **SOLO_CON_REVISION**.
- ¿Está suficientemente maduro para comenzar una validación masiva de 2004? **PARCIALMENTE**, como auditoría/medición y no como escritura automática.
- ¿Recomendaría integrarlo en `plazasboe.py`? **NO TODAVÍA**.

El detalle completo, incluidas cantidades, filas y decisiones de las 30 publicaciones, está en el JSON homónimo.
