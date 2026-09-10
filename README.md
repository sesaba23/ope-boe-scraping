# BuscadorBOE

BuscadorBOE recupera, almacena y consulta convocatorias de empleo público publicadas en el Boletín Oficial del Estado (BOE). Separa extracción, SQLite, normalizaciones conservadoras e interfaces de consulta.

La base documentada contiene publicaciones recuperadas entre **2004-01-02 y 2026-09-04**. No debe interpretarse como una garantía de que incluya todas las convocatorias españolas.

## Capacidades

- Búsqueda web y CLI por texto, fecha, administración, territorio, sistema, turno y clasificación.
- Conservación de texto BOE original junto con puesto y administración normalizados.
- Geografía conservadora: municipio, provincia, comunidad, ámbito, entidad, evidencia y confianza.
- Estadísticas, mapa, cobertura diaria, exportación XLSX/CSV y administración de base.
- Migraciones explícitas, snapshots, backups, procesamiento histórico y auditorías.

## Instalación

El entorno de desarrollo usa Python 3.12. No hay un marcador formal de versión: use una versión moderna compatible con `requirements.txt`. SQLite llega con Python. Node solo es necesario para algunas pruebas JavaScript.

```bash
git clone https://github.com/sesaba23/boe.git
cd boe
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

En Windows PowerShell, active el entorno con `\.venv\Scripts\Activate.ps1`. Las dependencias incluyen Flask, Requests, Beautiful Soup, pandas, openpyxl, Folium y pytest.

## Base de datos y portal web

La base operativa es `datos/boe.db`; código y datos se distribuyen por separado. Al arrancar, `gestion_base.asegurar_base_local` verifica la copia configurada: una base existente no se sustituye automáticamente y una ausente puede obtener la copia publicada. Las migraciones disponibles son explícitas, validadas y respaldadas.

```bash
.venv/bin/python web_estadisticas.py
# http://127.0.0.1:5000

# LAN, si se desea expresamente
.venv/bin/python web_estadisticas.py --host 0.0.0.0 --port 5000
```

Páginas: `/oposiciones`, `/estadisticas`, `/mapas`, `/cobertura` y `/administracion/base-datos`.

## Línea de comandos

| Comando | Finalidad |
| --- | --- |
| `python buscar_oposiciones.py "ingeniero" --provincia Madrid` | Consulta SQLite sin consultar BOE. |
| `python gestionar_base.py verificar` | Comprueba la base local. |
| `python gestionar_base.py manifest` | Muestra el manifiesto técnico. |
| `python plazasboe.py` | Scraper interactivo: solicita fechas y texto. |
| `python migrar_esquema_sqlite.py --base-datos RUTA` | Migra el schema disponible con backup. |
| `python sincronizar_sqlite.py snapshot` | Crea un snapshot consistente y manifiesto. |
| `python sincronizar_sqlite.py restaurar SNAPSHOT` | Restaura un snapshot validado. |
| `python recalcular_geografia.py --dry-run` | Audita geografía antes de escribir. |
| `python reconciliar_codigos_ine.py --dry-run` | Audita enlaces INE de alta confianza. |
| `python exportar_excel.py --salida salida.xlsx` | Exporta SQLite a XLSX. |

Revise siempre `--help` y prefiera una copia para pruebas. Los auditores trasladados se ejecutan como módulos:

```bash
python -m scripts.audit.analizar_geografia_ambito --help
python -m scripts.audit.auditoria_datos --help
```

## Estructura

```text
base_datos.py, consultas_boe.py       SQLite y consultas compartidas
plazasboe.py, boe_api.py              extracción y persistencia BOE
web_estadisticas.py                   portal Flask
gestion_base.py, sincronizar_sqlite.py gestión, copias y restauración
servicio_exportacion.py               exportaciones reutilizables
normalizacion_*.py, resolucion_*.py   normalización y geografía
scripts/audit/                        auditorías independientes
tests/                                suite pytest
templates/, static/                   interfaz web
datos/                                base operativa y catálogos
informes/, backups/                   evidencia y copias históricas/locales
```

## SQLite, normalización y calidad

En el estado documentado: `schema_version=6`, `data_version=27`. El schema identifica estructura; `data_version`, contenido. Ambos son metadata técnica.

| Grupo | Tablas y finalidad |
| --- | --- |
| Extracción | `publicaciones`, `oposiciones`, `busquedas`, `log_errores`, `cobertura`, `metadata`. |
| Geografía actual | `catalogos_geograficos`, `comunidades_autonomas`, `provincias`, `municipios`, `territorios_insulares`, relaciones insulares y `sedes_administraciones`. |
| Historia y aliases | `municipios_historicos`, `denominaciones_municipales_historicas`, `alias_sedes_administraciones`, `universidades`, `alias_universidades`. |

Una fila de `oposiciones` es una unidad extraída: una publicación puede producir varias filas. `num_plazas` es la cifra asociada a esa fila; contar filas no equivale necesariamente a convocatorias únicas.

- **Extraídos:** `puesto`, `administracion`, `num_plazas`, fechas, publicación, enlace, `sistema`, `turno`, `escala`, `subescala`, `clase`, `publicacion_id` y `version_extractor`.
- **Normalizados/inferidos:** puesto y administración normalizados, ámbito, tipo de entidad, municipio, provincia, comunidad, códigos/IDs geográficos, universidad, municipio histórico, evidencia, confianza y versión de resolutor.
- **Trazabilidad:** fecha de análisis, coordenadas y habitantes cuando estén disponibles.

Hay claves foráneas e índices para fecha, publicación, puesto, administración y geografía. La búsqueda libre `%LIKE%` puede requerir escaneo según el filtro. Los valores derivados no sustituyen el texto original del BOE.

Las reglas usan catálogos locales, aliases explícitos y códigos INE. Los casos dudosos no se fuerzan; los territorios insulares son una dimensión distinta de la provincia administrativa.

## Operaciones seguras y exportaciones

Las consultas usan parámetros. Antes de migrar, recalcular, reconciliar, restaurar o actualizar: cierre otros escritores, trabaje sobre una copia si prueba, use `--dry-run` si existe y compruebe `PRAGMA integrity_check` y `PRAGMA foreign_key_check`.

La sincronización distingue SHA-256 físico y fingerprint lógico. La exportación completa produce cinco datasets; la filtrada de Oposiciones aplica filtros lógicos y orden, no paginación ni estado visual.

## Perfil analítico y limitaciones

La base contiene **108.836 filas** y **332.058 plazas** entre 2004 y 2026. Puesto normalizado está informado en todas las filas; municipio en 98.588 (90,6 %) y provincia en 100.989 (92,8 %). La cobertura tiene 8.283 días, todos reutilizables en este estado.

Predominan `LOCAL` (97.577 filas), `MUNICIPAL` (87.752), `Concurso-Oposición` (43.098) y `Turno Libre` (59.869). Puestos frecuentes: Auxiliar Administrativo, Administrativo y Policía Local. Son estadísticas descriptivas del dataset, no de una muestra aleatoria.

Usos razonables: evolución anual, perfiles recurrentes, distribución territorial, administraciones convocantes, sistemas de acceso, calidad y cobertura. Limitaciones: heterogeneidad histórica, cambios de formato BOE, campos ausentes, posibles filas relacionadas con una publicación, territorialización derivada y convocatorias que pueden publicarse fuera del BOE. El dato original debe prevalecer para auditoría.

## Informes, backups, pruebas y seguridad

`informes/` conserva auditorías y evidencia histórica; no es requisito para arrancar. `backups/` contiene copias de operaciones y procesamientos; muchos están ignorados por Git y deben depurarse manualmente según valor operativo.

Se mantienen SQL parametrizado, whitelist de orden, protección de fórmulas en exportaciones, nombres de descarga controlados, temporales fuera del repositorio y validación antes de sustituir SQLite.

```bash
.venv/bin/python -m pytest
```

La suite vive en `tests/`; algunas pruebas JavaScript requieren Node. Licencia AGPL-3.0: consulte [licence.md](licence.md).
