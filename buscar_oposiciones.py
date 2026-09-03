"""Consulta local y read-only del histórico de oposiciones."""
import argparse
from pathlib import Path

from consultas_boe import ErrorConsultaSQLite, buscar_oposiciones


def _argumentos():
    parser = argparse.ArgumentParser(description="Busca oposiciones en SQLite, sin consultar el BOE.")
    parser.add_argument("texto", nargs="?", help="Puesto o término de búsqueda")
    parser.add_argument("--bd", default=Path.cwd() / "datos/boe.db", help="Ruta a datos/boe.db")
    parser.add_argument("--desde", dest="fecha_desde")
    parser.add_argument("--hasta", dest="fecha_hasta")
    for opcion, destino in (("administracion", "administracion"), ("ambito", "ambito"),
                            ("comunidad", "comunidad_autonoma"), ("provincia", "provincia"),
                            ("municipio", "municipio"), ("tipo-entidad", "tipo_entidad"),
                            ("sistema", "sistema"), ("turno", "turno"), ("escala", "escala"),
                            ("subescala", "subescala"), ("clase", "clase")):
        parser.add_argument(f"--{opcion}", dest=destino)
    parser.add_argument("--pagina", type=int, default=1)
    parser.add_argument("--tamano", type=int, choices=(25, 50, 100), default=25)
    parser.add_argument("--orden", choices=("fecha_desc", "fecha_asc", "puesto_asc", "administracion_asc", "plazas_desc"), default="fecha_desc")
    return parser.parse_args()


def main():
    argumentos = _argumentos()
    try:
        resultado = buscar_oposiciones(
            argumentos.bd, texto=argumentos.texto, fecha_desde=argumentos.fecha_desde,
            fecha_hasta=argumentos.fecha_hasta, administracion=argumentos.administracion,
            ambito=argumentos.ambito, comunidad_autonoma=argumentos.comunidad_autonoma,
            provincia=argumentos.provincia, municipio=argumentos.municipio,
            tipo_entidad=argumentos.tipo_entidad, sistema=argumentos.sistema,
            turno=argumentos.turno, escala=argumentos.escala, subescala=argumentos.subescala,
            clase=argumentos.clase, pagina=argumentos.pagina, tamano_pagina=argumentos.tamano,
            orden=argumentos.orden,
        )
    except (ErrorConsultaSQLite, ValueError) as error:
        print(f"Error: {error}")
        return 2
    if not resultado["total"]:
        print("No se encontraron oposiciones.")
        return 0
    print(f"Resultados: {resultado['total']} (página {resultado['pagina']} de {resultado['total_paginas']})\n")
    for fila in resultado["filas"]:
        print(f"{fila['fecha_boe'] or '—':<12} {str(fila['num_plazas'] if fila['num_plazas'] is not None else '—'):>6}  {fila['puesto']}")
        print(f"{'':20}{fila['administracion'] or 'Administración no disponible'}")
        territorio = " · ".join(x for x in (fila['municipio'], fila['provincia'], fila['comunidad_autonoma']) if x)
        print(f"{'':20}{territorio or 'Territorio no disponible'}")
        print(f"{'':20}{fila['enlace']}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
