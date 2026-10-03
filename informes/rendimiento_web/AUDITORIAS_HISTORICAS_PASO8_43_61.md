# Auditorías históricas PASO 8.43 y PASO 8.61

## Diagnóstico

Estado inicial: `main`, HEAD `97a63db025975623c8614854607afc4f0d868385`, con
cambios locales previos preservados. SQLite no se modificó:

* SHA-256: `3bef628b733427bd7238848ab6aa9359e7114fa15e5498f617a0523d2df53530`
* `schema_version=7`, `data_version=78`, `tipo_personal_version=tipo-personal-v1`
* `integrity_check=ok`, `foreign_key_check=[]`

Los dos fallos eran el mismo tipo de error conceptual: los tests verifican
reglas A contra un snapshot histórico, pero las simulaciones consultaban todo
`datos/boe.db` vivo. El snapshot CSV de cada paso no contiene las publicaciones
posteriores incorporadas después de la auditoría.

## PASO 8.43 — Bibliotecas y Archivos

La propiedad del test es que los dos conjuntos A, `Bibliotecario` y `Auxiliar
de Biblioteca`, sean literales, exactos y disjuntos. El universo histórico
reconstruido sigue siendo 1977 filas y 3816 plazas; A contiene 548 filas y los
cánones exactos son los esperados.

La discrepancia era:

| canon | esperado histórico | obtenido contra DB viva | diferencia |
|---|---:|---:|---|
| Bibliotecario | 151 filas / 184 plazas | 151 / 184 | ninguna |
| Auxiliar de Biblioteca | 397 / 635 | 398 / 637 | sobrante `109656` |

`109656` es una publicación posterior al snapshot, no una colisión semántica.
Sus datos son: `puesto=Auxiliar de Biblioteca`, `puesto_normalizado=Auxiliar de
Biblioteca`, 2 plazas, fecha BOE `2026-09-18`, Ayuntamiento de Santa Cruz de
Tenerife, provincia Santa Cruz de Tenerife, título «Resolución de 10 de
septiembre de 2026, del Ayuntamiento de Santa Cruz de Tenerife, referente a la
convocatoria para proveer varias plazas», BOE-A-2026-19447.

## PASO 8.61 — Psicología

El conjunto A es exclusivamente el genérico individual (`Psicólogo`, sus
variantes de género y grafías definidas). Especialidades como Psicólogo
Clínico, Psicólogo General Sanitario, Psicólogo Sanitario, Psicólogo Educativo,
Técnico Psicólogo, Facultativo Psicólogo, Psicólogo-Orientador y escalas/cuerpos
permanecen separadas.

La fila `oposicion_id=109741` es:

* `publicacion_id=BOE-A-2026-19742`, fecha `2026-09-23`;
* `puesto=Psicólogo/a`, `puesto_normalizado=Psicólogo`;
* Ayuntamiento de Elda, Administración Especial, subescala Técnica, clase No
  disponible;
* 4 plazas, provincia Alicante/Alacant, Comunitat Valenciana, tipo de
  personal Funcionario;
* título: «Resolución de 16 de septiembre de 2026, del Ayuntamiento de Elda,
  Instituto Municipal de Servicios Sociales de Elda (Alicante/Alacant),
  referente a la convocatoria para proveer varias plazas»;
* enlace BOE: `https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-19742`.

Es un registro nuevo posterior al CSV histórico de PASO 8.61. No es un bug del
normalizador: la denominación original es una variante genérica válida y la
normalización persistida a `Psicólogo` es coherente. La clasificación correcta
del desfase es **D — test histórico mal acoplado al universo vivo**, no error de
datos ni deuda de extracción.

## Corrección aplicada

* PASO 8.43: cuando existe el CSV histórico, la simulación de cada conjunto A
  restringe también el universo obtenido a sus IDs fuente.
* PASO 8.61: cuando existe el detalle CSV histórico, la cobertura del genérico
  se calcula dentro de esos IDs, no sobre todas las filas actuales.

Si no existe snapshot, se conserva el comportamiento léxico de respaldo. No se
añadieron IDs a excepciones, no se cambiaron tests para ocultar el desfase, no
se modificó `normalizacion_puestos.py`, no se modificó `tipo_personal.py` y no
se escribió SQLite.

## Validación

Tests focalizados: **5 passed**. El test de migración con
`-W error::FutureWarning`: **10 passed**. Suite completa normal:
**1548 passed, 0 warnings**. Segunda pasada estricta
`pytest -q -W error::FutureWarning`: **1548 passed, 0 warnings**, en
2088,74 s.

El warning procedía de `tests/test_migracion_sqlite.py:23`: asignar
`"Madrid"` a una columna que pandas había inferido como `float64` al rellenarla
con `NaN`. El fixture declara ahora esas columnas textuales como `object`; no
se añadió ningún filtro de warnings.

`git diff --check` es correcto. No se ejecutaron `git add`, `git commit`,
`git push`, `git reset`, `git restore` ni `git checkout`.
