# Origen de la Administración convocante

## Punto de pérdida

cargar_historico_boe.descubrir descarta titulo/departamento del sumario; después procesar_publicacion/ejecutar descartan metadatos XML. El extractor asigna el departamento BOE genérico a Administración, no la entidad concreta del título.

## Flujo

1. API/sumario: item.titulo, item.url_html, item.url_xml y departamento.nombre
1. cargar_historico_boe.descubrir: conserva en el sumario normalizado, pero persiste solo Publicacion_ID, Fecha_boe y Enlace
1. XML/extractor: analizar_xml conserva titulo/departamento; procesar_publicacion devuelve solo clasificación y filas válidas
1. estado JSON: registrar_resultado recibe sin metadatos/evidencias desde cargar_historico_boe
1. Publicaciones: _publicaciones_historicas lee metadatos.titulo; al estar vacío, Titulo_original queda vacío
1. Oposiciones: extractor histórico asigna Administración=metadatos.departamento, que para esta muestra es Administración Local genérica

## Resumen

- publicaciones_historicas: 134256
- filas_historicas: 106350
- filas_administracion_local: 98545
- muestra_publicaciones: 30
- estado_json_con_metadatos: 0
- consultas_reales: 10
- api_identifica_administracion: 10
- xml_identifica_administracion_adicional: 0
- solo_texto_xml: 0
- no_resoluble_en_consulta: 0
- porcentaje_api: 100.0
- porcentaje_xml_adicional: 0.0
- porcentaje_solo_texto: 0.0
- porcentaje_no_resoluble: 0.0
- entradas_estados_revisadas: 150398
- titulos_en_estados: 0
- departamentos_en_estados: 0
- evidencias_en_estados: 0
- fechas_distintas_para_consultar_sumario: 6548
- xml_identifica_administracion: 10
- porcentaje_xml: 100.0

## Muestra persistida (30)

| ID | Año | Filas | Título Excel | Metadatos estado |
|---|---:|---:|---|---|
| BOE-A-2004-8241 | 2004 | 1 |  | False |
| BOE-A-2005-15919 | 2005 | 1 |  | False |
| BOE-A-2005-5812 | 2005 | 1 |  | False |
| BOE-A-2005-8881 | 2005 | 1 |  | False |
| BOE-A-2006-20877 | 2006 | 2 |  | False |
| BOE-A-2007-10153 | 2007 | 1 |  | False |
| BOE-A-2008-4083 | 2008 | 1 |  | False |
| BOE-A-2008-5664 | 2008 | 1 |  | False |
| BOE-A-2008-9327 | 2008 | 1 |  | False |
| BOE-A-2009-17682 | 2009 | 1 |  | False |
| BOE-A-2010-5611 | 2010 | 1 |  | False |
| BOE-A-2010-6204 | 2010 | 1 |  | False |
| BOE-A-2010-7635 | 2010 | 1 |  | False |
| BOE-A-2011-1471 | 2011 | 1 |  | False |
| BOE-A-2011-18425 | 2011 | 1 |  | False |
| BOE-A-2014-4839 | 2014 | 1 |  | False |
| BOE-A-2014-5061 | 2014 | 1 |  | False |
| BOE-A-2016-10572 | 2016 | 1 |  | False |
| BOE-A-2016-12560 | 2016 | 2 |  | False |
| BOE-A-2016-7947 | 2016 | 1 |  | False |
| BOE-A-2019-12339 | 2019 | 1 |  | False |
| BOE-A-2019-1381 | 2019 | 1 |  | False |
| BOE-A-2019-16250 | 2019 | 1 |  | False |
| BOE-A-2021-18856 | 2021 | 1 |  | False |
| BOE-A-2022-19208 | 2022 | 5 |  | False |
| BOE-A-2022-19745 | 2022 | 3 |  | False |
| BOE-A-2022-24555 | 2022 | 3 |  | False |
| BOE-A-2023-16117 | 2023 | 1 |  | False |
| BOE-A-2023-7775 | 2023 | 25 |  | False |
| BOE-A-2026-16872 | 2026 | 1 | Resolución de 27 de julio de 2026, del Ayuntamiento de Corral de Almaguer (Toledo), referente a la c | False |

## Consultas individuales BOE (máximo 10)

| ID | API título/departamento | XML título/departamento | Administración concreta | Fuente |
|---|---|---|---|---|
| BOE-A-2004-8241 | Resolución de 2 de abril de 2004, de la Diputación Provincial de Albacete, Instituto de Estudios Albacetenses "Don Juan  / ADMINISTRACIÓN LOCAL | Resolución de 2 de abril de 2004, de la Diputación Provincial de Albacete, Instituto de Estudios Albacetenses "Don Juan  / Administración Local | Diputación Provincial de Albacete | API_SUMARIO |
| BOE-A-2005-15919 | Resolución de 13 de septiembre de 2005, del Ayuntamiento de San Vicente del Raspeig (Alicante), referente a la convocato / ADMINISTRACIÓN LOCAL | Resolución de 13 de septiembre de 2005, del Ayuntamiento de San Vicente del Raspeig (Alicante), referente a la convocato / Administración Local | Ayuntamiento de San Vicente del Raspeig (Alicante) | API_SUMARIO |
| BOE-A-2005-5812 | Resolución de 18 de marzo de 2005, del Ayuntamiento de Castelló d'Empúries (Girona), referente a la convocatoria para pr / ADMINISTRACIÓN LOCAL | Resolución de 18 de marzo de 2005, del Ayuntamiento de Castelló d'Empúries (Girona), referente a la convocatoria para pr / Administración Local | Ayuntamiento de Castelló d'Empúries (Girona) | API_SUMARIO |
| BOE-A-2005-8881 | Resolución de 17 de mayo de 2005, del Ayuntamiento de Benalmádena (Málaga), referente a la convocatoria para proveer una / ADMINISTRACIÓN LOCAL | Resolución de 17 de mayo de 2005, del Ayuntamiento de Benalmádena (Málaga), referente a la convocatoria para proveer una / Administración Local | Ayuntamiento de Benalmádena (Málaga) | API_SUMARIO |
| BOE-A-2006-20877 | Resolución de 6 de noviembre de 2006, del Ayuntamiento de Villafranca de los Barros (Badajoz), referente a la convocator / ADMINISTRACIÓN LOCAL | Resolución de 6 de noviembre de 2006, del Ayuntamiento de Villafranca de los Barros (Badajoz), referente a la convocator / Administración Local | Ayuntamiento de Villafranca de los Barros (Badajoz) | API_SUMARIO |
| BOE-A-2007-10153 | Resolución de 26 de abril de 2007, del Ayuntamiento de El Prat de Llobregat (Barcelona), referente a la convocatoria par / ADMINISTRACIÓN LOCAL | Resolución de 26 de abril de 2007, del Ayuntamiento de El Prat de Llobregat (Barcelona), referente a la convocatoria par / Administración Local | Ayuntamiento de El Prat de Llobregat (Barcelona) | API_SUMARIO |
| BOE-A-2008-4083 | Resolución de 22 de enero de 2008, del Ayuntamiento de La Carolina (Jaén), referente a la convocatoria para proveer una  / ADMINISTRACIÓN LOCAL | Resolución de 22 de enero de 2008, del Ayuntamiento de La Carolina (Jaén), referente a la convocatoria para proveer una  / Administración Local | Ayuntamiento de La Carolina (Jaén) | API_SUMARIO |
| BOE-A-2008-5664 | Resolución de 12 de febrero de 2008, del Consorcio Hospitalario Provincial de Castellón, referente a la convocatoria par / ADMINISTRACIÓN LOCAL | Resolución de 12 de febrero de 2008, del Consorcio Hospitalario Provincial de Castellón, referente a la convocatoria par / Administración Local | Consorcio Hospitalario Provincial de Castellón | API_SUMARIO |
| BOE-A-2008-9327 | Resolución de 8 de mayo de 2008, del Ayuntamiento de San Roque (Cádiz), referente a la convocatoria para proveer varias  / ADMINISTRACIÓN LOCAL | Resolución de 8 de mayo de 2008, del Ayuntamiento de San Roque (Cádiz), referente a la convocatoria para proveer varias  / Administración Local | Ayuntamiento de San Roque (Cádiz) | API_SUMARIO |
| BOE-A-2009-17682 | Resolución de 26 de octubre de 2009, del Ayuntamiento de Cabanillas del Campo, Patronato Deportivo Municipal (Guadalajar / ADMINISTRACIÓN LOCAL | Resolución de 26 de octubre de 2009, del Ayuntamiento de Cabanillas del Campo, Patronato Deportivo Municipal (Guadalajar / Administración Local | Ayuntamiento de Cabanillas del Campo | API_SUMARIO |

## Coste y recomendación

Los estados existentes no permiten reconstruir de forma fiable los títulos perdidos. La opción mínima que conserva título y departamento es consultar de nuevo el sumario/API para cada fecha de edición y asociar sus items por Publicacion_ID; no requiere XML ni reextraer Puesto/Num_plazas. XML solo sería necesario para los casos en que el título/sumario no identifique explícitamente la entidad.
