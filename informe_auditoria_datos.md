# Informe de auditoría de datos BOE

## Resumen ejecutivo

| Métrica | Valor |
|---|---|
| Filas de Oposiciones | 2084 |
| Publicaciones BOE únicas | 1485 |
| Puestos únicos | 1200 |
| Administraciones únicas | 824 |
| Provincias únicas | 52 |
| Filas con Publicacion_ID válido | 2084 |
| Filas legacy | 685 |
| Filas con versión actual | 1399 |
| Filas sin Fecha_analisis | 685 |

### Incidencias principales

| Métrica | Valor |
|---|---|
| Geolocalización | 61 |
| Fechas | 0 |
| Publicaciones a revisar | 0 |
| Cobertura inconsistente | 0 |
| Duplicados por clave | 0 |

## Calidad por columnas

| Columna | Nulos | Vacíos | -- | No disponible | % problemáticos |
|---|---|---|---|---|---|
| Num_plazas | 0 | 0 | 0 | 0 | 0.0 |
| Puesto | 0 | 0 | 0 | 0 | 0.0 |
| Administración | 1 | 0 | 1 | 0 | 0.1 |
| Escala | 0 | 0 | 5 | 348 | 16.94 |
| Subescala | 0 | 0 | 5 | 348 | 16.94 |
| Clase | 0 | 0 | 5 | 858 | 41.41 |
| Sistema | 0 | 0 | 0 | 0 | 0.0 |
| Turno | 0 | 0 | 3 | 1 | 0.19 |
| Fecha_boe | 0 | 0 | 0 | 0 | 0.0 |
| Publicación | 0 | 0 | 5 | 0 | 0.24 |
| Enlace | 0 | 0 | 0 | 0 | 0.0 |
| Municipio | 61 | 0 | 0 | 0 | 2.93 |
| Provincia | 61 | 0 | 0 | 0 | 2.93 |
| Latitud | 61 | 0 | 0 | 0 | 2.93 |
| Longitud | 61 | 0 | 0 | 0 | 2.93 |
| Habitantes | 61 | 0 | 0 | 0 | 2.93 |
| Publicacion_ID | 0 | 0 | 0 | 0 | 0.0 |
| Version_extractor | 0 | 0 | 0 | 0 | 0.0 |
| Fecha_analisis | 685 | 0 | 0 | 0 | 32.87 |

## Geolocalización

| Métrica | Valor |
|---|---|
| Filas sin municipio | 61 |
| Filas sin provincia | 61 |
| Filas sin latitud | 61 |
| Filas sin longitud | 61 |
| Latitud sin longitud | 0 |
| Longitud sin latitud | 0 |
| Coordenadas no numéricas | 0 |
| Coordenadas fuera de rango | 0 |
| Habitantes ausentes o no numéricos | 61 |
| Municipios con varias coordenadas | 0 |
| Municipios con varias administraciones | 38 |

### Casos problemáticos

| Publicacion_ID | Puesto | Administración | Municipio | Provincia | Latitud | Longitud |
|---|---|---|---|---|---|---|
| BOE-A-2025-1060 | Ingeniero/a Técnico/a Industrial | Diputación Foral de Álava |  |  |  |  |
| BOE-A-2025-11908 | Técnico/a de Administración Especial | Cabildo Insular de Lanzarote |  |  |  |  |
| BOE-A-2025-13692 | Técnico/a de Juventud | Ayuntamiento de L'Alcora (Castellón/Castelló) |  |  |  |  |
| BOE-A-2025-13692 | Ordenanza | Ayuntamiento de L'Alcora (Castellón/Castelló) |  |  |  |  |
| BOE-A-2025-14534 | Jefe/a Servicio Gestión Catastral | Cabildo Insular de Lanzarote |  |  |  |  |
| BOE-A-2025-14534 | Técnico de Recaudación | Cabildo Insular de Lanzarote |  |  |  |  |
| BOE-A-2025-14534 | Técnico de Inspección Catastral | Cabildo Insular de Lanzarote |  |  |  |  |
| BOE-A-2025-14534 | Técnico de Gestión Financiera | Cabildo Insular de Lanzarote |  |  |  |  |
| BOE-A-2025-14534 | Responsable de Oficinas Centrales | Cabildo Insular de Lanzarote |  |  |  |  |
| BOE-A-2025-14534 | Agente de Gestión Tributaria y Recaudación Ejecutiva | Cabildo Insular de Lanzarote |  |  |  |  |
| BOE-A-2026-13512 | Técnico/a superior de administración general | Ayuntamiento de Castell d'Aro |  |  |  |  |
| BOE-A-2026-13529 | Técnico/a de Administración General | Mancomunidad del Sur (Madrid) |  |  |  |  |
| BOE-A-2026-13681 | Técnico/a superior de contabilidad y gestión presupuestaria | Ayuntamiento de L'Eliana (Valencia/València) |  |  |  |  |
| BOE-A-2026-13688 | Técnico/a de biblioteca | Ayuntamiento de L'Eliana (Valencia/València) |  |  |  |  |
| BOE-A-2026-13689 | Técnico/a Auxiliar de Animación Juvenil | Ayuntamiento de L'Eliana (Valencia/València) |  |  |  |  |
| BOE-A-2026-13817 | Técnico/a de Control Interno en el Área Económica | Ayuntamiento de L'Eliana (Valencia/València) |  |  |  |  |
| BOE-A-2026-13817 | Técnico/a de Recaudación | Ayuntamiento de L'Eliana (Valencia/València) |  |  |  |  |
| BOE-A-2026-14178 | Vigilante municipal | Ayuntamiento de L'Espluga de Francolí (Tarragona) |  |  |  |  |
| BOE-A-2026-14806 | Oficial de Primera de la plantilla de personal laboral fijo | Ayuntamiento de La Ràpita (Tarragona) |  |  |  |  |
| BOE-A-2026-14806 | Arquitecto/a Técnico/a | Ayuntamiento de La Ràpita (Tarragona) |  |  |  |  |
| BOE-A-2026-14806 | Arquitecto/a Superior | Ayuntamiento de La Ràpita (Tarragona) |  |  |  |  |
| BOE-A-2026-14935 | Administrativo/va | Ayuntamiento de Castell d'Aro |  |  |  |  |
| BOE-A-2026-15326 | Administrativo/a de Administración General | Ayuntamiento de L'Olleria (Valencia/València) |  |  |  |  |
| BOE-A-2026-15805 | Administrativo/a | Ayuntamiento de L'Alcora (Castellón/Castelló) |  |  |  |  |
| BOE-A-2026-16293 | Técnico/a de Atención Temprana de la plantilla de personal laboral fijo | Mancomunitat de Municipis de la Safor (Valencia/València) |  |  |  |  |
| BOE-A-2026-16875 | Limpiador/a | Ayuntamiento de Medina Sidonia (Cádiz) |  |  |  |  |
| BOE-A-2026-16877 | Técnico/a Medio/a de Administración General de la plantilla de personal laboral fijo | Mancomunidad des Raiguer (Illes Balears) |  |  |  |  |
| BOE-A-2026-16877 | Administrativo/a de la plantilla de personal laboral fijo | Mancomunidad des Raiguer (Illes Balears) |  |  |  |  |
| BOE-A-2026-16976 | Oficial de obras | Ayuntamiento de Medina Sidonia (Cádiz) |  |  |  |  |
| BOE-A-2026-17035 | Arquitecto/a técnico/a | Mancomunidad de Municipios Alto Asón (Cantabria) |  |  |  |  |
| BOE-A-2026-17232 | Técnico/a de Administración General | Mancomunidad Intermunicipal Campiña 2000 (Sevilla) |  |  |  |  |
| BOE-A-2026-17639 | Técnico/a de Administración General | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Técnico/a de Administración General | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Técnico/a de Administración General | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Veterinario/a | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Arquitecto/a | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Técnico/a Superior de Archivo | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Técnico/a Supeior de Igualdad | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Técnico/a Superior Economista | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Técnico/a Superior Economista | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Técnico/a Superior Economista | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Técnico Superior de Calidad Democrática | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Técnico Superior de Biblioteca | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Arquitecto/a Técnico/a | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Arquitecto/a Técnico/a | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Enfermero/a | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Técnico/a Medio Informatico | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Técnico/a Medio de Instalaciones | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Técnico/a Medio de Apoyo a Campañas de la plantilla de personal laboral fijo-discontinuo | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Técnico/a Medio de Apoyo a Campañas de la plantilla de personal laboral fijo-discontinuo | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Técnico/a Medio Agrícola | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Técnico/a Medio Agrícola | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Administrativo/a | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Administrativo/a | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Administrativo/a | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Sargento | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Sargento | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Cabo | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17639 | Cuidador/a | Diputación Provincial de Gipuzkoa |  |  |  |  |
| BOE-A-2026-17868 | Administrativo/a | Consejo General de Arán (Lleida) |  |  |  |  |
| BOE-A-2026-17901 | Peón/a-conductor/a de la plantilla de personal laboral fijo | Mancomunidad El Záncara (Cuenca) |  |  |  |  |

## Valores categóricos

### Sistema

Frecuencias:

| Valor | Frecuencia |
|---|---|
| Concurso-Oposición | 1395 |
| Oposición | 610 |
| Concurso | 73 |
| General De Acceso Libre | 4 |
| Oposicion | 1 |
| General De Acceso Libre Y Promoción Interna | 1 |

Posibles variantes:

| Clave | Variantes |
|---|---|
| oposicion | Oposicion \| Oposición |

### Turno

Frecuencias:

| Valor | Frecuencia |
|---|---|
| Libre | 1547 |
| De Promoción Interna | 405 |
| Reservado A Personas Con Discapacidad | 69 |
| De Movilidad | 50 |
| Restringido | 5 |
| De Promoción Externa | 2 |
| turno general | 1 |
| turno libre | 1 |

Posibles variantes:

Sin casos.

### Escala

Frecuencias:

| Valor | Frecuencia |
|---|---|
| Administración Especial | 1200 |
| Administración General | 531 |

Posibles variantes:

Sin casos.

### Subescala

Frecuencias:

| Valor | Frecuencia |
|---|---|
| Técnica | 799 |
| Servicios especiales | 468 |
| Administrativa | 211 |
| Auxiliar | 110 |
| Gestión | 48 |
| Subalterna | 38 |
| Servicios Especiales | 35 |
| Especial | 21 |
| de Gestión | 1 |

Posibles variantes:

| Clave | Variantes |
|---|---|
| servicios especiales | Servicios Especiales \| Servicios especiales |

### Clase

Frecuencias:

| Valor | Frecuencia |
|---|---|
| Media | 327 |
| Superior | 288 |
| Policía Local y sus auxiliares | 235 |
| Auxiliar | 125 |
| Personal de oficios | 96 |
| Cometidos especiales | 86 |
| Servicio de extinción de incendios | 37 |
| Policía Local y sus Auxiliares | 9 |
| Cometidos Especiales | 7 |
| Personal de Oficios | 7 |
| Servicio de Extinción de Incendios | 4 |

Posibles variantes:

| Clave | Variantes |
|---|---|
| cometidos especiales | Cometidos Especiales \| Cometidos especiales |
| policia local y sus auxiliares | Policía Local y sus Auxiliares \| Policía Local y sus auxiliares |
| personal de oficios | Personal de Oficios \| Personal de oficios |
| servicio de extincion de incendios | Servicio de Extinción de Incendios \| Servicio de extinción de incendios |

## Puestos

### Top 30 por registros

| Valor | Frecuencia |
|---|---|
| Administrativo/a | 123 |
| Policía Local | 63 |
| Técnico/a de Administración General | 49 |
| Auxiliar Administrativo/a | 42 |
| Arquitecto/a | 38 |
| Ingeniero/a Técnico/a Industrial | 30 |
| Agente de Policía Local | 28 |
| Trabajador/a Social | 27 |
| Arquitecto/a Técnico/a | 21 |
| Oficial de Policía Local | 16 |
| Administrativo | 14 |
| Agente de la Policía Local | 13 |
| Educador/a Social | 13 |
| Psicólogo/a | 12 |
| Técnico/a de Gestión | 12 |
| Ingeniero/a Técnico Industrial | 11 |
| Auxiliar Administrativo | 10 |
| Oficial de la Policía Local | 10 |
| Subinspector/a de Policía Local | 9 |
| Ordenanza | 9 |
| Auxiliar de Administración General | 9 |
| Delineante | 8 |
| Administrativa/o | 8 |
| Trabajador/a Social de la plantilla de personal laboral fijo | 8 |
| Agente Policía Local | 7 |
| Ingeniero Técnico Industrial | 7 |
| Archivero/a | 7 |
| Subalterno/a | 7 |
| Técnico/a Administración General | 7 |
| Limpiador/a de la plantilla de personal laboral fijo | 7 |

### Top 30 por plazas

| Puesto | Plazas |
|---|---|
| Administrativo/a | 440.0 |
| Cuerpo de Ingenieros Industriales del Estado | 220.0 |
| Policía Local | 207.0 |
| Auxiliar Administrativo/a | 139.0 |
| Técnico/a de Administración General | 122.0 |
| Oficial de Policía | 103.0 |
| Agente de Policía Local | 80.0 |
| Trabajador/a Social | 59.0 |
| Arquitecto/a | 55.0 |
| Cuerpo Facultativo de Conservadores de Museos | 54.0 |
| Ingeniero/a Técnico/a Industrial | 49.0 |
| Administrativo | 48.0 |
| Escala de Personal Investigador Científico de los Organismos Públicos de Investigación | 47.0 |
| Arquitecto/a Técnico/a | 46.0 |
| Cabo | 46.0 |
| Subalterno/a | 43.0 |
| Técnico/a Auxiliar Tributario/a | 40.0 |
| Agente de la Policía Local | 40.0 |
| Oficial de la Policía Local | 35.0 |
| Ordenanza | 34.0 |
| Policía del Cuerpo de Policía Local | 33.0 |
| Subinspector/a de Policía Local | 31.0 |
| Administrativa/o | 31.0 |
| Técnico/a Medio/a en Trabajo Social | 31.0 |
| Auxiliar administrativo/a | 31.0 |
| Oficial de Policía Local | 30.0 |
| Delineante | 29.0 |
| Administrativo/a de Administración General | 29.0 |
| reclasificación de Policía Local | 29.0 |
| Auxiliar Administrativo | 28.0 |

### Posibles variantes

| Clave | Variantes |
|---|---|
| tecnico de archivo y administracion electronica | Técnico de Archivo y Administración Electrónica \| Técnico/a de Archivo y Administración Electrónica |
| oficial de primera conductor de la plantilla de personal laboral fijo | Oficial de Primera Conductor de la plantilla de personal laboral fijo \| Oficial/a de Primera Conductor/a de la plantilla de personal laboral fijo |
| tecnico superior en derecho | Técnico/a Superior en Derecho \| Técnico/a superior en Derecho |
| agente de policia local | Agente de Policia Local \| Agente de Policía Local \| Agente de Policía local \| Agente de policía local |
| oficial | Oficial \| Oficial/a |
| asesor juridico | Asesor/a Jurídico/a \| Asesor/a jurídico/a |
| policia local | Policia Local \| Policía Local \| Policía local |
| agente policia local | Agente Policía Local \| Agente policía local \| agente Policía local |
| ingeniero tecnico industrial | Ingeniero Técnico Industrial \| Ingeniero/a Técnico Industrial \| Ingeniero/a Técnico/a Industrial \| Ingeniero/a Técnico/a industrial \| Ingeniero/a técnico industrial \| Ingeniero/a técnico/a industrial |
| tecnico medio | Técnico Medio \| Técnico/a Medio \| Técnico/a Medio/a \| Técnico/a medio \| Técnico/a medio/a |
| arquitecto superior | Arquitecto/a Superior \| Arquitecto/a superior |
| oficial fontanero | Oficial Fontanero/a \| Oficial/a Fontanero/a |
| tecnico de recursos humanos | Técnico de Recursos Humanos \| Técnico/a de Recursos Humanos |
| oficial de jardineria | Oficial de Jardinería \| Oficial/a de Jardinería |
| tecnico superior | Técnico Superior \| Técnico/a Superior |
| auxiliar administrativo | Auxiliar  Administrativo \| Auxiliar Administrativo \| Auxiliar Administrativo//a \| Auxiliar Administrativo/a \| Auxiliar administrativo \| Auxiliar administrativo/a \| Auxiliar-Administrativo |
| tecnico medio de administracion general | Técnico/a Medio de Administración General \| Técnico/a Medio/a de Administración General |
| personal auxiliar administrativo | Personal Auxiliar administrativo \| personal Auxiliar Administrativo \| personal auxiliar administrativo |
| arquitecto municipal | Arquitecto Municipal \| Arquitecto/a Municipal |
| tecnico medio ambiente | Tecnico/a Medio Ambiente \| Técnico/a Medio Ambiente |
| tecnico medio de archivo | Técnico Medio de Archivo \| Técnico/a Medio de Archivo |
| tecnico | Técnico \| Técnico/a \| técnico/a |
| agente de igualdad | Agente de Igualdad \| agente de igualdad |
| sargento | Sargento \| Sargento/a |
| tecnico de recaudacion | Técnico de Recaudación \| Técnico/a de Recaudación |
| tecnico de gestion | Técnico de Gestión \| Técnico de gestión \| Técnico/a de Gestión \| Técnico/a de gestión \| técnico/a de gestión |
| agente de desarrollo local | Agente de Desarrollo Local \| agente de desarrollo local |
| subinspector de la policia local | Subinspector/a de la Policía Local \| Subinspector/a de la policía local |
| tecnico medio recursos humanos | Técnico Medio Recursos Humanos \| Técnico/a Medio/a Recursos Humanos |
| tecnico de prevencion de riesgos laborales | Técnico de Prevención de Riesgos Laborales \| Técnico/a de Prevención de Riesgos Laborales |
| ingeniero | Ingeniero \| Ingeniero/a \| ingeniero/a |
| ayudante de cocina de la plantilla de personal laboral fijo | Ayudante de Cocina de la plantilla de personal laboral fijo \| Ayudante de cocina de la plantilla de personal laboral fijo |
| bombero | Bombero \| Bombero/a |
| tecnico auxiliar de informatica | Técnico Auxiliar de Informática \| Técnico/a Auxiliar de Informática \| Técnico/a auxiliar de informática |
| tecnico superior de educacion infantil de la plantilla de personal laboral fijo | Técnico/a Superior de Educación Infantil  de la plantilla de personal laboral fijo \| Técnico/a Superior de Educación Infantil de la plantilla de personal laboral fijo |
| tecnico de archivo y gestion documental | Técnico de Archivo y Gestión Documental \| Técnico/a de archivo y gestión documental |
| oficial policia local | Oficial Policía Local \| Oficial policía local |
| oficial de albanileria | Oficial de Albañilería \| Oficial/a de Albañilería |
| arquitecto tecnico | Arquitecto Técnico \| Arquitecto/a Tecnico/a \| Arquitecto/a Técnico \| Arquitecto/a Técnico/a \| Arquitecto/a técnico/a \| arquitecto/a técnico/a |
| trabajador social | Trabajador Social \| Trabajador/a Social \| Trabajador/a social \| trabajador/a social |
| administrativo de administracion general | Administrativo/a de Administración General \| Administrativo/a de administración general |
| operario de servicios multiples de la plantilla de personal laboral fijo | Operario de Servicios Múltiples de la plantilla de personal laboral fijo \| Operario de servicios múltiples de la plantilla de personal laboral fijo \| Operario/a de Servicios Múltiples de la plantilla de personal laboral fijo \| Operario/a de servicios múltiples de la plantilla de personal laboral fijo |
| archivero | Archivero \| Archivero/a \| archivero |
| operario | Operario \| operario/a |
| operario servicios multiples de la plantilla de personal laboral fijo | Operario Servicios Múltiples de la plantilla de personal laboral fijo \| Operario/a servicios multiples  de la plantilla de personal laboral fijo |
| tecnico de administracion general | Tecnico/a de Administracion  General \| Técnico de Administración General \| Técnico/a de Administración General \| Técnico/a de administración general \| técnico/a de Administración General |
| operario de servicios multiples | Operario/a de Servicios Múltiples \| Operario/a de servicios múltiples |
| auxiliar administrativo de la plantilla de personal laboral fijo | Auxiliar Administrativo/a de la plantilla de personal laboral fijo \| Auxiliar administrativo/a de la plantilla de personal laboral fijo |
| policia del cuerpo de policia local | Policia del Cuerpo de Policía Local \| Policía del Cuerpo de Policía Local |
| oficial de la policia local | Oficial de la Policía Local \| Oficial de la policía local |
| tecnico administracion general | Técnico Administración General \| Técnico/a Administración General |
| peon de la plantilla de personal laboral fijo | Peón de la plantilla de personal laboral fijo \| Peón/a de la plantilla de personal laboral fijo |
| administrativo administrativa | Administrativo/Administrativa \| Administrativo/administrativa |
| tecnico de medio ambiente | Técnico de medio ambiente \| Técnico/a de Medio Ambiente |
| agente de la policia local | Agente de la Policia Local \| Agente de la Policía Local \| Agente de la policía local |
| letrado asesor juridico | Letrado/a Asesor/a Jurídico/a \| Letrado/a-Asesor/a Jurídico/a |
| administrativo | Administrativo \| Administrativo/a \| administrativo/a |
| tecnico auxiliar en educacion diurna | Técnico/a Auxiliar en Educación Diurna \| técnico/a auxiliar en educación diúrna |
| letrado | Letrado \| Letrado/a |
| educador social | Educador/a Social \| Educador/a social |
| delineante | Delineante \| Delineante/a |
| subalterno | Subalterno \| Subalterno/a |
| arquitecto | Arquitecto \| Arquitecto/a |
| oficial de servicios varios de la plantilla de personal laboral fijo | Oficial de Servicios Varios de la plantilla de personal laboral fijo \| Oficial de servicios varios de la plantilla de personal laboral fijo |
| personal administrativo | Personal Administrativo \| personal Administrativo |
| ingeniero tecnico | Ingeniero Técnico \| Ingeniero/a Técnico/a |
| educador social de la plantilla de personal laboral fijo | Educador/a Social de la plantilla de personal laboral fijo \| Educador/a social de la plantilla de personal laboral fijo |
| bombero conductor | Bombero Conductor \| Bombero-Conductor \| Bombero/a-Conductor/a |
| oficial de vias y obras | Oficial de Vías Y Obras \| Oficial de vías y obras |
| tecnico superior economista | Técnico/a Superior Economista \| Técnico/a Superior/a Economista |
| oficial electricista | Oficial Electricista \| Oficial electricista \| Oficial/a Electricista \| Oficial/a electricista |
| auxiliar de biblioteca | Auxiliar de Biblioteca \| Auxiliar de biblioteca |
| oficial de policia local | Oficial de Policía Local \| Oficial/a de Policía Local |
| oficial agricola ganadero | Oficial/a Agrícola Ganadero/a \| oficial/a agrícola ganadero/a |
| administrativo gestor tributario | Administrativo/a Gestor/a Tributario/a \| Administrativo/a-Gestor/a Tributario/a |
| oficial del cuerpo de policia local | Oficial del Cuerpo de Policía Local \| oficial del cuerpo de Policía Local \| oficial del cuerpo de policía local |
| oficial de servicios multiples de la plantilla de personal laboral fijo | Oficial de Servicios Múltiples de la plantilla de personal laboral fijo \| Oficial/a de Servicios Múltiples de la plantilla de personal laboral fijo |
| subinspector de policia | Subinspector de Policía \| Subinspector/a de Policía |
| diplomado universitario en enfermeria | Diplomado Universitario/a en Enfermería \| Diplomado/a Universitario/a en Enfermería |
| oficial albanil de la plantilla de personal laboral fijo | Oficial Albañil de la plantilla de personal laboral fijo \| Oficial albañil de la plantilla de personal laboral fijo |
| tecnico medio de gestion | Técnico/a Medio de Gestión \| Técnico/a Medio/a de Gestión |
| tecnico informatico | Técnico/a Informático/a \| Técnico/a informático/a \| técnico/a informático/a |
| tecnico deportivo | Técnico/a Deportivo \| Técnico/a Deportivo/a |
| oficial mecanico conductor | Oficial Mecánico/a Conductor/a \| Oficial/a Mecánico/a Conductor/a |
| tecnico de archivo | Técnico de Archivo \| Técnico/a de Archivo \| Técnico/a de archivo |
| ingeniero industrial | Ingeniero/a Industrial \| Ingeniero/a industrial |
| administrativo de tesoreria | Administrativo de Tesorería \| Administrativo de tesorería |
| ingeniero tecnico agricola | Ingeniero/a Técnico Agrícola \| Ingeniero/a Técnico/a Agrícola |
| subinspector de policia local | Subinspector de Policía Local \| Subinspector/a de Policía Local |
| auxiliar administrativa o | Auxiliar Administrativa/o \| Auxiliar-administrativa/o |
| tecnico medio de deportes | Técnico/a  medio de deportes \| Técnico/a Medio/a de Deportes |
| monitor deportivo de la plantilla de personal laboral fijo | Monitor/a Deportivo/a de la plantilla de personal laboral fijo \| Monitor/a deportivo/a de la plantilla de personal laboral fijo |
| tecnico de gestion financiera | Técnico de Gestión Financiera \| Técnico/a de Gestión Financiera |
| tecnico de igualdad | Técnico de Igualdad \| Técnico/a de Igualdad |
| archivero bibliotecario | Archivero/a Bibliotecario/a \| Archivero/a-Bibliotecario/a |
| tecnico auxiliar de archivo y biblioteca | Técnico/a Auxiliar de Archivo y Biblioteca \| Técnico/a auxiliar de archivo y  biblioteca |
| trabajador social de la plantilla de personal laboral fijo | Trabajador/a Social de la plantilla de personal laboral fijo \| Trabajador/a social de la plantilla de personal laboral fijo |

## Administraciones

### Top 30 por registros

| Valor | Frecuencia |
|---|---|
| Diputación Provincial de Pontevedra | 50 |
| Ayuntamiento de Barcelona | 50 |
| Diputación Provincial de Almería | 35 |
| Ayuntamiento de Bilbao (Bizkaia) | 30 |
| Diputación Provincial de Gipuzkoa | 28 |
| Diputación Provincial de Badajoz | 27 |
| Ayuntamiento de Avilés (Asturias) | 17 |
| Diputación Provincial de Huelva | 15 |
| Ayuntamiento de Tíjola (Almería) | 15 |
| Ayuntamiento de Elx/Elche (Alicante/Alacant) | 13 |
| Ayuntamiento de Alcázar de San Juan (Ciudad Real) | 13 |
| Ayuntamiento de Benalmádena (Málaga) | 12 |
| Ayuntamiento de Culleredo (A Coruña) | 12 |
| Ayuntamiento de Sa Pobla (Illes Balears) | 11 |
| Diputación Provincial de Ciudad Real | 11 |
| Ayuntamiento de Jaén | 11 |
| Diputación Provincial de Toledo | 11 |
| Ayuntamiento de Guardamar del Segura (Alicante/Alacant) | 10 |
| Ayuntamiento de Viladecans (Barcelona) | 10 |
| Ayuntamiento de Cornellà de Llobregat (Barcelona) | 10 |
| Ayuntamiento de Marbella (Málaga) | 10 |
| Ayuntamiento de Móstoles (Madrid) | 10 |
| Ayuntamiento de Logroño (La Rioja) | 9 |
| Ayuntamiento de Getxo (Bizkaia) | 9 |
| Ayuntamiento de Madrid | 9 |
| Diputación Provincial de Zaragoza | 9 |
| Ayuntamiento de Alcorcón (Madrid) | 9 |
| Ayuntamiento de Huesca | 9 |
| Ayuntamiento de Zamora | 9 |
| Ayuntamiento de Almenara (Castellón/Castelló) | 8 |

### Top 30 por plazas

| Administración | Plazas |
|---|---|
| Ayuntamiento de Barcelona | 304.0 |
| Subsecretaría (Ministerio de Industria y Turismo) | 220.0 |
| Ayuntamiento de Madrid | 182.0 |
| Diputación Provincial de Gipuzkoa | 154.0 |
| Diputación Provincial de Pontevedra | 115.0 |
| Diputación Provincial de Huelva | 97.0 |
| Diputación Provincial de Almería | 79.0 |
| Ayuntamiento de Getxo (Bizkaia) | 74.0 |
| Diputación Provincial de Badajoz | 70.0 |
| Ayuntamiento de Bilbao (Bizkaia) | 67.0 |
| Ayuntamiento de Santander (Cantabria) | 57.0 |
| Ayuntamiento de Córdoba | 56.0 |
| Subsecretaría (Ministerio de Cultura) | 54.0 |
| Ayuntamiento de Avilés (Asturias) | 48.0 |
| Subsecretaría (Ministerio de Ciencia) | 47.0 |
| Ayuntamiento de Fuengirola (Málaga) | 45.0 |
| Consorcio Provincial de Extinción de Incendios y Salvamento de Toledo | 40.0 |
| Ayuntamiento de Elx/Elche (Alicante/Alacant) | 40.0 |
| Ayuntamiento de Torrevieja (Alicante/Alacant) | 40.0 |
| Ayuntamiento de San Fernando de Henares (Madrid) | 37.0 |
| Ayuntamiento de Marbella (Málaga) | 37.0 |
| Ayuntamiento de Badajoz | 36.0 |
| Ayuntamiento de Viladecans (Barcelona) | 35.0 |
| Ayuntamiento de Cornellà de Llobregat (Barcelona) | 35.0 |
| Ayuntamiento de Palma (Illes Balears) | 34.0 |
| Ayuntamiento de Fuenlabrada (Madrid) | 32.0 |
| Ayuntamiento de Sa Pobla (Illes Balears) | 32.0 |
| Ayuntamiento de Alcorcón (Madrid) | 31.0 |
| Ayuntamiento de Alacant/Alicante (Alicante/Alacant) | 31.0 |
| Ayuntamiento de Tíjola (Almería) | 31.0 |

### Posibles variantes

| Clave | Variantes |
|---|---|
| diputacion provincial de granada | Diputacion Provincial de Granada \| Diputación Provincial de Granada |
| consejo comarcal del girones (girona) | Consejo Comarcal del Gironès (Girona) \| Consejo Comarcal del Gironés (Girona) |

### Inconsistencias geográficas

| Métrica | Valor |
|---|---|
| varias_localizaciones | 0 |
| geolocalizaciones_inconsistentes | 0 |

## Fechas

| Métrica | Valor |
|---|---|
| Fecha_boe inválidas | 0 |
| Fechas BOE futuras | 0 |
| Fecha_analisis inválidas | 0 |
| Fecha_ultimo_analisis inválidas | 0 |
| Fechas inconsistentes Oposiciones/Publicaciones | 0 |

## Publicaciones

| Métrica | Valor |
|---|---|
| Filas | 2236 |
| Publicacion_ID duplicados | 0 |
| con_coincidencias sin Oposiciones | 0 |
| sin_coincidencias con Oposiciones | 0 |
| Coincidencias no numérico | 0 |
| Coincidencias negativo | 0 |
| Versiones realmente inválidas | 0 |
| Versiones legacy | 537 |
| Estados desconocidos | 0 |
| Criterio | consistente: igualdad; diferencia explicable: ambos positivos (posible deduplicación); revisar: valores inválidos o contradicción de estado. |

### Comparación Coincidencias/filas



| Elemento | Valor |
|---|---|
| consistente | 2236 |

## Cobertura

| Métrica | Valor |
|---|---|
| Filas | 62 |
| Fechas duplicadas | 0 |
| Estados desconocidos | 0 |
| Versiones inválidas | 0 |
| Numero_publicaciones inválido | 0 |
| sin_edicion distinto de cero | 0 |
| Fechas inválidas | 0 |
| Cobertura/Publicaciones no coinciden | 0 |

## Búsquedas

| Métrica | Valor |
|---|---|
| Total | 36185 |
| Códigos únicos | 36185 |
| Publicaciones únicas implícitas | 28726 |
| Textos de búsqueda distintos | 7 |
| Códigos no asociables | 0 |

### Distribución por texto



| Elemento | Valor |
|---|---|
| archiv | 15686 |
| ing téc ind | 9154 |
| ing téc industrial | 7458 |
| ingeniero técnico ind | 1699 |
|  | 1106 |
| ing ind | 593 |
| arquitec | 489 |

## Log de errores

| Métrica | Valor |
|---|---|
| Total | 33 |
| Enlaces únicos | 28 |
| Potencialmente resueltos | 0 |
| Sin evidencia de resolución | 33 |

### Tipos



| Elemento | Valor |
|---|---|
| Error al acceder | 26 |
| Error buscando coincidencias | 7 |

### Errores repetidos por enlace



| Elemento | Valor |
|---|---|
| https://www.boe.es/diario_boe/txt.php?id=BOE-A-2025-11466 | 3 |
| https://www.boe.es/diario_boe/txt.php?id=BOE-A-2025-1671 | 2 |
| https://www.boe.es/boe/dias/2026/08/09/index.php?s=2B | 2 |
| https://www.boe.es/boe/dias/2026/07/26/index.php?s=2B | 2 |

## Duplicados e inconsistencias

| Métrica | Valor |
|---|---|
| Filas duplicadas exactas | 0 |
| Duplicados según clave actual | 0 |
| Publicacion_ID + Puesto con datos diferentes | 63 |
| Enlaces con valores contradictorios | 182 |

## Diagnóstico de segundo nivel

### Versiones de Publicaciones

| Métrica | Valor |
|---|---|
| Total publicaciones | 2236 |
| Legacy pendientes de reprocesamiento | 537 |
| Vacías | 0 |
| Nulas | 0 |
| Versiones numéricas válidas | 1699 |
| Versiones numéricas futuras | 0 |
| Valores realmente inválidos | 0 |

#### Distribución exacta

| Valor | Categoría | Publicaciones | Porcentaje |
|---|---|---|---|
| 1 | versión numérica válida | 1699 | 75.98 |
| legacy | legacy | 537 | 24.02 |

#### Ejemplos realmente inválidos

Sin casos.

### Convocatorias aparentemente duplicadas

| Métrica | Valor |
|---|---|
| Grupos totales | 63 |
| LEGÍTIMO | 63 |
| REVISAR | 0 |
| Columnas que provocan diferencias | {'Turno': 62, 'Num_plazas': 51, 'Sistema': 26} |

#### Casos REVISAR

Sin casos.

### Publicaciones multiconvocatoria

| Métrica | Valor |
|---|---|
| Enlaces analizados | 182 |
| NORMAL_MULTICONVOCATORIA | 182 |
| POSIBLE_INCONSISTENCIA | 0 |
| Falsos positivos de primera auditoría | 182 |

#### Posibles inconsistencias

Sin casos.

### Estado real del Log de errores

| Métrica | Valor |
|---|---|
| Errores totales | 33 |
| Enlaces únicos | 28 |
| RESUELTO | 10 |
| PENDIENTE | 7 |
| ERROR_DE_INDICE | 0 |
| NO_DETERMINABLE | 16 |

#### Casos pendientes

| Fecha error | Tipo | Enlace | Clasificación | Evidencia |
|---|---|---|---|---|
| 2025-05-25 21:51:43 | Error buscando coincidencias | https://www.boe.es/diario_boe/txt.php?id=BOE-A-2025-1671 | PENDIENTE | No existe en Publicaciones. |
| 2025-05-26 22:18:43 | Error buscando coincidencias | https://www.boe.es/diario_boe/txt.php?id=BOE-A-2024-9948 | PENDIENTE | No existe en Publicaciones. |
| 2025-05-26 22:18:43 | Error buscando coincidencias | https://www.boe.es/diario_boe/txt.php?id=BOE-A-2024-21440 | PENDIENTE | No existe en Publicaciones. |
| 2025-05-26 22:18:43 | Error buscando coincidencias | https://www.boe.es/diario_boe/txt.php?id=BOE-A-2025-1671 | PENDIENTE | No existe en Publicaciones. |
| 2025-06-10 21:59:12 | Error buscando coincidencias | https://www.boe.es/diario_boe/txt.php?id=BOE-A-2025-11466 | PENDIENTE | No existe en Publicaciones. |
| 2025-06-10 22:04:14 | Error buscando coincidencias | https://www.boe.es/diario_boe/txt.php?id=BOE-A-2025-11466 | PENDIENTE | No existe en Publicaciones. |
| 2025-06-10 22:06:21 | Error buscando coincidencias | https://www.boe.es/diario_boe/txt.php?id=BOE-A-2025-11466 | PENDIENTE | No existe en Publicaciones. |
| 2026-08-20 22:40:03 | Error al acceder | https://www.boe.es/boe/dias/2026/03/08/index.php?s=2B | NO_DETERMINABLE | No existe cobertura para la fecha del índice. |
| 2026-08-20 22:40:03 | Error al acceder | https://www.boe.es/boe/dias/2026/03/15/index.php?s=2B | NO_DETERMINABLE | No existe cobertura para la fecha del índice. |
| 2026-08-20 22:40:03 | Error al acceder | https://www.boe.es/boe/dias/2026/03/22/index.php?s=2B | NO_DETERMINABLE | No existe cobertura para la fecha del índice. |
| 2026-08-20 22:40:03 | Error al acceder | https://www.boe.es/boe/dias/2026/03/29/index.php?s=2B | NO_DETERMINABLE | No existe cobertura para la fecha del índice. |
| 2026-08-20 22:40:03 | Error al acceder | https://www.boe.es/boe/dias/2026/04/05/index.php?s=2B | NO_DETERMINABLE | No existe cobertura para la fecha del índice. |
| 2026-08-20 22:40:03 | Error al acceder | https://www.boe.es/boe/dias/2026/04/12/index.php?s=2B | NO_DETERMINABLE | No existe cobertura para la fecha del índice. |
| 2026-08-20 22:40:03 | Error al acceder | https://www.boe.es/boe/dias/2026/04/19/index.php?s=2B | NO_DETERMINABLE | No existe cobertura para la fecha del índice. |
| 2026-08-20 22:40:03 | Error al acceder | https://www.boe.es/boe/dias/2026/04/26/index.php?s=2B | NO_DETERMINABLE | No existe cobertura para la fecha del índice. |
| 2026-08-20 22:40:03 | Error al acceder | https://www.boe.es/boe/dias/2026/05/03/index.php?s=2B | NO_DETERMINABLE | No existe cobertura para la fecha del índice. |
| 2026-08-20 22:40:03 | Error al acceder | https://www.boe.es/boe/dias/2026/05/10/index.php?s=2B | NO_DETERMINABLE | No existe cobertura para la fecha del índice. |
| 2026-08-20 22:40:03 | Error al acceder | https://www.boe.es/boe/dias/2026/05/17/index.php?s=2B | NO_DETERMINABLE | No existe cobertura para la fecha del índice. |
| 2026-08-20 22:40:03 | Error al acceder | https://www.boe.es/boe/dias/2026/05/24/index.php?s=2B | NO_DETERMINABLE | No existe cobertura para la fecha del índice. |
| 2026-08-20 22:40:03 | Error al acceder | https://www.boe.es/boe/dias/2026/05/31/index.php?s=2B | NO_DETERMINABLE | No existe cobertura para la fecha del índice. |
| 2026-08-20 22:40:03 | Error al acceder | https://www.boe.es/boe/dias/2026/06/07/index.php?s=2B | NO_DETERMINABLE | No existe cobertura para la fecha del índice. |
| 2026-08-20 22:40:03 | Error al acceder | https://www.boe.es/boe/dias/2026/06/14/index.php?s=2B | NO_DETERMINABLE | No existe cobertura para la fecha del índice. |
| 2026-08-20 22:40:03 | Error al acceder | https://www.boe.es/boe/dias/2026/06/21/index.php?s=2B | NO_DETERMINABLE | No existe cobertura para la fecha del índice. |

### Geolocalización pendiente por tipo de administración

| Métrica | Valor |
|---|---|
| Filas totales | 61 |

| Tipo | Filas | Publicaciones | Administraciones |
|---|---|---|---|
| Diputación Foral | 1 | 1 | 1 |
| Cabildo Insular | 7 | 2 | 1 |
| Ayuntamiento | 17 | 13 | 7 |
| Mancomunidad/Mancomunitat | 7 | 6 | 6 |
| Diputación Provincial | 28 | 1 | 1 |
| Otros | 1 | 1 | 1 |

#### Ayuntamientos

| Publicacion_ID | Administración | Puesto | Municipio | Provincia |
|---|---|---|---|---|
| BOE-A-2025-13692 | Ayuntamiento de L'Alcora (Castellón/Castelló) | Técnico/a de Juventud |  |  |
| BOE-A-2025-13692 | Ayuntamiento de L'Alcora (Castellón/Castelló) | Ordenanza |  |  |
| BOE-A-2026-13512 | Ayuntamiento de Castell d'Aro | Técnico/a superior de administración general |  |  |
| BOE-A-2026-13681 | Ayuntamiento de L'Eliana (Valencia/València) | Técnico/a superior de contabilidad y gestión presupuestaria |  |  |
| BOE-A-2026-13688 | Ayuntamiento de L'Eliana (Valencia/València) | Técnico/a de biblioteca |  |  |
| BOE-A-2026-13689 | Ayuntamiento de L'Eliana (Valencia/València) | Técnico/a Auxiliar de Animación Juvenil |  |  |
| BOE-A-2026-13817 | Ayuntamiento de L'Eliana (Valencia/València) | Técnico/a de Control Interno en el Área Económica |  |  |
| BOE-A-2026-13817 | Ayuntamiento de L'Eliana (Valencia/València) | Técnico/a de Recaudación |  |  |
| BOE-A-2026-14178 | Ayuntamiento de L'Espluga de Francolí (Tarragona) | Vigilante municipal |  |  |
| BOE-A-2026-14806 | Ayuntamiento de La Ràpita (Tarragona) | Oficial de Primera de la plantilla de personal laboral fijo |  |  |
| BOE-A-2026-14806 | Ayuntamiento de La Ràpita (Tarragona) | Arquitecto/a Técnico/a |  |  |
| BOE-A-2026-14806 | Ayuntamiento de La Ràpita (Tarragona) | Arquitecto/a Superior |  |  |
| BOE-A-2026-14935 | Ayuntamiento de Castell d'Aro | Administrativo/va |  |  |
| BOE-A-2026-15326 | Ayuntamiento de L'Olleria (Valencia/València) | Administrativo/a de Administración General |  |  |
| BOE-A-2026-15805 | Ayuntamiento de L'Alcora (Castellón/Castelló) | Administrativo/a |  |  |
| BOE-A-2026-16875 | Ayuntamiento de Medina Sidonia (Cádiz) | Limpiador/a |  |  |
| BOE-A-2026-16976 | Ayuntamiento de Medina Sidonia (Cádiz) | Oficial de obras |  |  |

## Recomendaciones

| Clasificación | Hallazgo | Recomendación |
|---|---|---|
| HISTÓRICO | 537 publicaciones legacy | Mantenerlas diferenciadas y planificar su reprocesamiento controlado; no tratarlas como datos corruptos. |
| FALSO POSITIVO DE AUDITORÍA | 63 grupos Publicacion_ID + Puesto legítimos | No considerar diferencias de turno, sistema, escala, clase o plazas como duplicados por sí solas. |
| FALSO POSITIVO DE AUDITORÍA | 182 publicaciones multiconvocatoria normales | Excluirlas de futuras reglas genéricas de contradicción por enlace. |
| GEOGRAFÍA | 61 filas sin geolocalización completa | Priorizar los ayuntamientos; mantener separadas las administraciones supramunicipales. |
| HISTÓRICO | 7 errores todavía pendientes | Conservar el log y revisar los casos sin evidencia posterior de resolución. |
