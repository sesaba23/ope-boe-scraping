"""Adaptador CLI para exportar la base SQLite a un Excel interoperable."""
import argparse
import json
from pathlib import Path

import servicio_exportacion as servicio


# Se mantienen los nombres públicos históricos para scripts y pruebas externas.
CONTRATOS = servicio.CONTRATOS
MAPA_OPOSICIONES = servicio.MAPA_OPOSICIONES


def cargar_sqlite(ruta):
    """Compatibilidad: carga los datasets funcionales sin escribir SQLite."""
    return servicio.cargar_datos_exportacion_completa(ruta)


def _fingerprint_hoja(dataframe, nombre):
    return servicio._fingerprint_hoja(dataframe, nombre)


def auditar(dataframes, ruta_excel):
    return servicio.auditar_xlsx(dataframes, ruta_excel)


def _backup(ruta, directorio="backups/exportacion_excel"):
    return servicio._backup_xlsx(ruta, directorio)


def _guardar_informe(informe):
    informes = Path("informes/exportacion_excel")
    informes.mkdir(parents=True, exist_ok=True)
    contenido = json.dumps(informe, ensure_ascii=False, indent=2) + "\n"
    (informes / "auditoria_exportacion_excel.json").write_text(
        contenido, encoding="utf-8"
    )
    (informes / "auditoria_exportacion_excel.md").write_text(
        "# Auditoría exportación Excel\n\n" + contenido, encoding="utf-8"
    )


def exportar(ruta_bd="datos/boe.db", salida="BOE-oposiciones.xlsx", *, sobrescribir=False):
    """Conserva el contrato CLI histórico delegando en el motor compartido."""
    informe = servicio.exportar_base_xlsx(ruta_bd, salida, sobrescribir=sobrescribir)
    _guardar_informe(informe)
    return informe


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bd", default="datos/boe.db")
    parser.add_argument("--salida", default="BOE-oposiciones.xlsx")
    parser.add_argument("--sobrescribir", action="store_true")
    argumentos = parser.parse_args(argv)
    print(
        json.dumps(
            exportar(
                argumentos.bd, argumentos.salida, sobrescribir=argumentos.sobrescribir
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
