# 📰 Web Scraping del BOE para Oposiciones Públicas

Este proyecto realiza **web scraping** del Boletín Oficial del Estado (BOE) para extraer información sobre oposiciones y otros datos relevantes. Los resultados se almacenan en un archivo Excel y se pueden filtrar por fechas y patrones de búsqueda.
---

## 🎯 ¿Para quién es útil este proyecto?

Está específicamente pensado para buscar plazas o convocatorias publicadas por:
- 👨‍💼 La **Administración Local**: Grupos A1 y A2 (ingenierías, arquitectura, obras públicas, etc.)
- 👩‍💻 También **Grupos B, C1, C2**: Auxiliar Administrativo, Administrativo, Conserje, Policía Local, etc.
- 🏛️ **Administración del Estado**: Ingenieros Industriales del Estado, Abogados del Estado, Arquitectos de la Hacienda Pública, etc.

>
> ⚠️ **Nota:**  
> Actualmente **no es fiable** para carreras de la rama sanitaria, ya que la mayoría de estas plazas se publican en los Boletines Oficiales de las Comunidades Autónomas.  
> Por el momento, la aplicación no realiza búsquedas en los Boletines o Diarios Autonómicos.
**A petición, especialmente de entidades o asociaciones como Colegios Oficiales**, iré ampliando sus capacidades de búsqueda en puestos y plazas concretos de las Comunidades Autónomas que se soliciten.
>
---

## 👨‍🔬 Autor

| Nombre                | Contacto                |
|-----------------------|------------------------|
| Sergio Sánchez Barahona | sesaba23@gmail.com     |
| Ingeniero Industrial e Ingeniero en Electrónica | |

## 🚀 Instalación y ejecución

### Requisitos

La aplicación necesita Python y conexión a Internet para consultar `boe.es`. Sus dependencias están fijadas en `requirements.txt`: Beautiful Soup, Colorama, Folium, openpyxl, pandas, Requests, tqdm, `word2number_es` y pytest para ejecutar las pruebas.

### Crear el entorno virtual

Desde la raíz del proyecto:

```bash
python -m venv .venv
```

Actívalo en Linux o macOS:

```bash
source .venv/bin/activate
```

En Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Instala las dependencias:

```bash
python -m pip install -r requirements.txt
```

Para salir del entorno virtual:

```bash
deactivate
```

### Ejecutar la aplicación

La ejecución principal es:

```bash
python plazasboe.py
```

También puede indicarse el puesto buscado como argumento:

```bash
python plazasboe.py ingeniero industrial
```

La aplicación solicita las fechas en formato `dd/mm/aaaa`. Si no se proporciona un puesto, también lo solicita de forma interactiva.

### Archivos generados

Los archivos de salida se crean en el directorio desde el que se ejecuta la aplicación:

- `BOE-oposiciones.xlsx`: histórico de búsquedas, convocatorias y errores.
- `mapa_municipios.html`: mapa de las convocatorias con coordenadas.
- `puestos_sin_coordenadas.html`: convocatorias que no pudieron localizarse geográficamente.

Para ejecutar las pruebas:

```bash
python -m pytest -q
```

## 📄 LICENCIA

Este proyecto está licenciado bajo la Licencia Pública General Affero de GNU, versión 3.0 (AGPL-3.0). Puedes consultar sus términos en `licence.md` o en el siguiente enlace:

https://www.gnu.org/licenses/agpl-3.0.html


## 🤝 Contribuciones

¡Las contribuciones son bienvenidas!
Si deseas colaborar, por favor abre un issue o envía un pull request.

---

## ⚠️ Descargo de responsabilidad

> Este software se distribuye bajo la Licencia Pública General Affero de GNU (AGPL), lo que significa que puedes usarlo, modificarlo y redistribuirlo bajo los términos de dicha licencia.
>
> **Sin embargo, este script se proporciona "tal cual", sin ninguna garantía**, expresa o implícita, incluyendo pero no limitándose a garantías de comerciabilidad o idoneidad para un propósito particular.
>
> El autor no se hace responsable de ningún daño directo, indirecto, incidental, especial, ejemplar o consecuente (incluyendo pero no limitado a pérdida de datos, interrupción de servicios, fallos en otros sistemas, o daños a terceros) que pueda surgir del uso de este software, incluso si se ha advertido de la posibilidad de tales daños.
>
> **El uso de esta aplicación es bajo tu propia responsabilidad.** Asegúrate de comprender su funcionamiento antes de ejecutarlo, especialmente si estás buscando plazas o convocatorias muy específicas.
Esta aplicación se suministra como una herramienta de ayuda que permite facilitar la búsqueda de convocatorias de plazas y puestos publicados en el BOE por la Administración General del Estado (AGE) y las distintas Administraciones Locales ahorrando gran cantidad de tiempo y esfuerzo.
>
>No obstante, **no es infalible** y puede no encontrar ciertas plazas debido a la infinita casuistica y formas de publicar los textos de las distintas convocatorias por las más de 8.100 administraciones Locales y de la AGE, que además pueden variar en el tiempo.
La única manera de asegurarte de no te pierdes ninguna convocatiria al 100% es consultando diariamente el BOE y es posible que ni aún así, debido al enorme número de publicaciones diarias.
>
>Este proyecto puede hacer uso de bibliotecas de terceros o acceder a servicios externos. El mantenimiento y responsabilidad de dichos servicios corresponde a sus respectivos autores o proveedores.

---

## 📚 Notas adicionales

- El proyecto puede hacer uso de bibliotecas de terceros o acceder a servicios externos. El mantenimiento y responsabilidad de dichos servicios corresponde a sus respectivos autores o proveedores.
- Para más detalles, consulta el archivo `licence.md`.

---

¡Gracias por usar este proyecto! ⭐
