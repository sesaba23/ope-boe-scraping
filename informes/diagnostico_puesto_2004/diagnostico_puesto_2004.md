# Diagnóstico de Puesto — corpus histórico 2004

Reglas experimentales locales aplicadas sin reglas por ID; 3891 y 10041 quedan fuera de alcance.

## Resultado antes/después

### Resultado Antes

- verdaderos_positivos: 0
- falsos_positivos: 16
- falsos_negativos: 8
- diferencias_Puesto: 8
- diferencias_Num_plazas: 0
- posibles_dobles_conteos: 0

### Resultado Despues

- verdaderos_positivos: 6
- falsos_positivos: 10
- falsos_negativos: 2
- diferencias_Puesto: 2
- diferencias_Num_plazas: 0
- posibles_dobles_conteos: 0

## Diagnóstico por publicación

### BOE-A-2004-74 — SIN_DISCREPANCIA

ESPERADO MANUALMENTE

| Puesto | Num_plazas |
|---|---:|
| — | — |

EXTRAÍDO ACTUALMENTE

| Puesto | Num_plazas |
|---|---:|
| — | — |

### BOE-A-2004-81 — PUESTO_NO_DETECTADO

ESPERADO MANUALMENTE

| Puesto | Num_plazas |
|---|---:|
| Ordenanza | 1 |

EXTRAÍDO ACTUALMENTE

| Puesto | Num_plazas |
|---|---:|
| Ordenanza | 1 |

- Diferencia: esperado «Ordenanza»; extraído «Ordenanza». Familia: PUESTO_NO_DETECTADO.
- Evidencia del Puesto extraído: fuente HISTORICAL_TEXT; regla/patrón: propuesta_extractor precargada; sin regla de Puesto cuando el valor es nulo; fragmento:  Orgánica 3/1980, de 22 de abril, del Consejo de Estado y su Reglamento Orgánico, he resuelto: Primero. Convocar proceso selectivo para proveer, por el turno de promoción interna, una plaza vacante de personal laboral del Consejo de Estado de la categoría profesional de Ordenanza, nivel 7. Segundo. Las bases que desarrollan la convocatoria se expondrán en el tablón de anuncios de la planta baja del Consejo de Estado, calle Ma
- Causa y denominación correcta: La denominación explícita correcta es «categoría profesional de Ordenanza»; la propuesta solo asoció la cantidad.

### BOE-A-2004-372 — SIN_DISCREPANCIA

ESPERADO MANUALMENTE

| Puesto | Num_plazas |
|---|---:|
| — | — |

EXTRAÍDO ACTUALMENTE

| Puesto | Num_plazas |
|---|---:|
| personal laboral mediante contratación laboral fija | 2 |

### BOE-A-2004-1396 — PUESTO_DEMASIADO_CORTO

ESPERADO MANUALMENTE

| Puesto | Num_plazas |
|---|---:|
| Jefe Regional de Seguridad | 59 |

EXTRAÍDO ACTUALMENTE

| Puesto | Num_plazas |
|---|---:|
| Jefe Regional de Seguridad | 59 |

- Diferencia: esperado «Jefe Regional de Seguridad»; extraído «Jefe Regional de Seguridad». Familia: PUESTO_DEMASIADO_CORTO.
- Evidencia del Puesto extraído: fuente HISTORICAL_TEXT; regla/patrón: propuesta_extractor precargada; sin regla de Puesto cuando el valor es nulo; fragmento: para 2003 por Real Decreto 215/2003, de 21 de febrero (Boletín Oficial del Estado del 22). En dicha oferta se autoriza a la Agencia Estatal de Administración Tributaria a convocar 59 plazas de personal laboral. Por lo tanto, en cumplimiento de dicho Real Decreto y con el fin de atender las necesidades de personal, Esta Presidencia, previo informe favorable de la Dirección General de la Función Pública, ha resuelto: Primero.-C
- Causa y denominación correcta: «personal laboral» es una descripción genérica; la denominación explícita correcta es «categoría de Jefe Regional de Seguridad».

### BOE-A-2004-2476 — SIN_DISCREPANCIA

ESPERADO MANUALMENTE

| Puesto | Num_plazas |
|---|---:|
| — | — |

EXTRAÍDO ACTUALMENTE

| Puesto | Num_plazas |
|---|---:|
| None | 6 |
| None | 1 |

### BOE-A-2004-3826 — SIN_DISCREPANCIA

ESPERADO MANUALMENTE

| Puesto | Num_plazas |
|---|---:|
| — | — |

EXTRAÍDO ACTUALMENTE

| Puesto | Num_plazas |
|---|---:|
| primera a convocar y 24 de segunda | 39 |

### BOE-A-2004-3891 — PUESTO_NO_DETECTADO

ESPERADO MANUALMENTE

| Puesto | Num_plazas |
|---|---:|
| Guardia Civil | 237 |

EXTRAÍDO ACTUALMENTE

| Puesto | Num_plazas |
|---|---:|
| None | 237 |

- Diferencia: esperado «Guardia Civil»; extraído «None». Familia: PUESTO_NO_DETECTADO.
- Evidencia del Puesto extraído: fuente HISTORICAL_TEXT; regla/patrón: propuesta_extractor precargada; sin regla de Puesto cuando el valor es nulo; fragmento: a Escala Superior de Oficiales de los Cuerpos Generales de los Ejércitos y de Infantería de Marina y a la Escala Superior de Oficiales de la Guardia Civil, para cubrir un total de 237 plazas, distribuidas de la siguiente forma: Ejército Cuerpo Plazas Tierra. General de las Armas. 124 Armada. General. 31 Infantería de Marina. 7 Aire. General. 43 Guardia Civil. 32 Total. 237 2. Condiciones para optar al ingreso Los aspirantes de
- Causa y denominación correcta: La cantidad total se asoció sin Puesto. La tabla Ejército/Cuerpo contiene jerarquía y el valor manual «Guardia Civil» no se puede inferir de forma segura para el total 237.

### BOE-A-2004-6309 — PUESTO_NO_DETECTADO

ESPERADO MANUALMENTE

| Puesto | Num_plazas |
|---|---:|
| Profesores de Enseñanza Secundaria | 183 |
| Profesores Técnicos de Formación Profesional | 35 |
| Profesores de Escuelas Oficiales de Idiomas | 5 |
| Profesores de Música y Artes Escénicas | 59 |

EXTRAÍDO ACTUALMENTE

| Puesto | Num_plazas |
|---|---:|
| Profesores de Enseñanza Secundaria | 183 |
| Profesores Técnicos de Formación Profesional | 35 |
| Profesores de Escuelas Oficiales de Idiomas | 5 |
| Profesores de Música y Artes Escénicas | 59 |

- Diferencia: esperado «Profesores de Enseñanza Secundaria»; extraído «Profesores de Enseñanza Secundaria». Familia: PUESTO_NO_DETECTADO.
- Evidencia del Puesto extraído: fuente HISTORICAL_TEXT; regla/patrón: propuesta_extractor precargada; sin regla de Puesto cuando el valor es nulo; fragmento: narios de los mencionados cuerpos. Que el número de plazas convocadas, cuya distribución se indica en anexo a esta Resolución, es el siguiente: Profesores de Enseñanza Secundaria, 183 plazas. Profesores Técnicos de Formación Profesional, 35 plazas. Profesores de Escuelas Oficiales de Idiomas, 5 plazas. Profesores de Música y Artes Escénicas, 59 plazas. Que el plazo de presentación de instancias será de veinte días naturales co

- Diferencia: esperado «Profesores Técnicos de Formación Profesional»; extraído «Profesores Técnicos de Formación Profesional». Familia: PUESTO_NO_DETECTADO.
- Evidencia del Puesto extraído: fuente HISTORICAL_TEXT; regla/patrón: propuesta_extractor precargada; sin regla de Puesto cuando el valor es nulo; fragmento:  convocadas, cuya distribución se indica en anexo a esta Resolución, es el siguiente: Profesores de Enseñanza Secundaria, 183 plazas. Profesores Técnicos de Formación Profesional, 35 plazas. Profesores de Escuelas Oficiales de Idiomas, 5 plazas. Profesores de Música y Artes Escénicas, 59 plazas. Que el plazo de presentación de instancias será de veinte días naturales contados a partir del siguiente al de la publicación de est

- Diferencia: esperado «Profesores de Escuelas Oficiales de Idiomas»; extraído «Profesores de Escuelas Oficiales de Idiomas». Familia: PUESTO_NO_DETECTADO.
- Evidencia del Puesto extraído: fuente HISTORICAL_TEXT; regla/patrón: propuesta_extractor precargada; sin regla de Puesto cuando el valor es nulo; fragmento:  Resolución, es el siguiente: Profesores de Enseñanza Secundaria, 183 plazas. Profesores Técnicos de Formación Profesional, 35 plazas. Profesores de Escuelas Oficiales de Idiomas, 5 plazas. Profesores de Música y Artes Escénicas, 59 plazas. Que el plazo de presentación de instancias será de veinte días naturales contados a partir del siguiente al de la publicación de esta convocatoria en el Boletín Oficial de Aragón. Que la 

- Diferencia: esperado «Profesores de Música y Artes Escénicas»; extraído «Profesores de Música y Artes Escénicas». Familia: PUESTO_NO_DETECTADO.
- Evidencia del Puesto extraído: fuente HISTORICAL_TEXT; regla/patrón: propuesta_extractor precargada; sin regla de Puesto cuando el valor es nulo; fragmento: nza Secundaria, 183 plazas. Profesores Técnicos de Formación Profesional, 35 plazas. Profesores de Escuelas Oficiales de Idiomas, 5 plazas. Profesores de Música y Artes Escénicas, 59 plazas. Que el plazo de presentación de instancias será de veinte días naturales contados a partir del siguiente al de la publicación de esta convocatoria en el Boletín Oficial de Aragón. Que la solicitud será dirigida a la Consejera de Educación
- Causa y denominación correcta: Cada denominación correcta aparece explícitamente antes de su cantidad («Profesores …, N plazas»), pero la propuesta no conserva esa asociación textual.

### BOE-A-2004-8235 — SIN_DISCREPANCIA

ESPERADO MANUALMENTE

| Puesto | Num_plazas |
|---|---:|
| — | — |

EXTRAÍDO ACTUALMENTE

| Puesto | Num_plazas |
|---|---:|
| — | — |

### BOE-A-2004-10041 — ESCALA_CONFUNDIDA_CON_PUESTO

ESPERADO MANUALMENTE

| Puesto | Num_plazas |
|---|---:|
| Intervención-Tesorería | 100 |

EXTRAÍDO ACTUALMENTE

| Puesto | Num_plazas |
|---|---:|
| None | 100 |
| funcionarios de Administración Local con habilitación de carácter nacional | 100 |
| funcionarios de Administración Local con habilitación de carácter nacional | 50 |
| None | 50 |
| None | 5 |

- Diferencia: esperado «Intervención-Tesorería»; extraído «None». Familia: ESCALA_CONFUNDIDA_CON_PUESTO.
- Evidencia del Puesto extraído: fuente HISTORICAL_TEXT; regla/patrón: propuesta_extractor precargada; sin regla de Puesto cuando el valor es nulo; fragmento: e febrero, por el que se aprueba la oferta de empleo público para el año 2004 («Boletín Oficial del Estado» del 7), autoriza en su disposición adicional segunda la convocatoria de 100 plazas para la Subescala de Intervención-Tesorería, categoría de entrada, de la Escala de Funcionarios de Administración Local con habilitación de carácter nacional. Así, en cumplimiento de lo dispuesto en el Real Decreto 222/2004, de 6 de febrer
- Causa y denominación correcta: La denominación manual correcta es «Subescala de Intervención-Tesorería». Las cinco propuestas mezclan total, referencia de escala, componentes y subcupo.

- Observación: Cinco filas: total 100, referencia de escala 100, dos componentes 50 y subcupo 5; no se modifica reconciliación.

## Familias de error

- PUESTO_NO_DETECTADO: 3
- PUESTO_DEMASIADO_CORTO: 1
- ESCALA_CONFUNDIDA_CON_PUESTO: 1

## Reglas aplicadas

- Categoría profesional explícita
- Lista local denominación, cantidad
- Categoría explícita del título sobre descriptor genérico

## Casos no resueltos

- BOE-A-2004-3891
- BOE-A-2004-6309
- BOE-A-2004-10041

