import os
import shutil
import time
from colorama import Fore, Style


def imprimir_diccionario_puestos(
    diccionario_puestos,
    f_inicio,
    f_fin,
    busqueda="",
    publicaciones_analizadas=None,
    publicaciones_fallidas=0,
):
    """
    Imprime en pantalla cada elemento del diccionario_puestos de uno en uno.
    :param diccionario_puestos: Diccionario que contiene información de los puestos.
    """
    ancho_terminal = shutil.get_terminal_size().columns

    if diccionario_puestos:
        # Asumimos que todas las listas tienen la misma longitud
        num_elementos = len(
            diccionario_puestos["Fecha_boe"]
        )  # Usamos "Fecha" como referencia

        print()
        print("=" * ancho_terminal)

        print(
            f"{Style.BRIGHT}Plazas publicadas en el BOE (Boletín Oficial del Estado): "
        )

        print("=" * ancho_terminal)

        for i in range(num_elementos):
            print(
                f"\n{Fore.YELLOW}Puesto nº {i + 1}:\t {diccionario_puestos['Puesto'][i]} "
                f"{Fore.LIGHTYELLOW_EX}({diccionario_puestos['Num_plazas'][i]} plaza/s)"
            )
            print(
                f"{Fore.LIGHTMAGENTA_EX}Administración:\t {diccionario_puestos['Administración'][i]}"
            )
            print(
                f"{Fore.CYAN}Escala:{Fore.RESET}\t\t {diccionario_puestos['Escala'][i]}"
                f"{Fore.CYAN}\t Subescala:{Fore.RESET} {diccionario_puestos['Subescala'][i]}"
                f"{Fore.CYAN}\t Clase:{Fore.RESET} {diccionario_puestos['Clase'][i]}"
            )
            print(
                f"{Fore.CYAN}Sistema:{Fore.RESET}\t {diccionario_puestos['Sistema'][i]}"
                f"{Fore.CYAN}\t\t Turno:{Fore.RESET} {diccionario_puestos['Turno'][i]}"
            )
            print(
                f"{Fore.CYAN}Fecha BOE:{Fore.RESET}\t {diccionario_puestos['Fecha_boe'][i]}"
            )
            print(
                f"{Fore.CYAN}Publicación:{Fore.RESET}\t {diccionario_puestos['Publicación'][i]}"
            )
            print(f"{Fore.LIGHTGREEN_EX}{diccionario_puestos['Enlace'][i]}")
            print()  # Línea en blanco para separar elementos
            time.sleep(0.1)

        print("=" * ancho_terminal)
        print(
            f"\nPatrón de búsqueda: «{busqueda}»\n"
            f"Periodo: {f_inicio} - {f_fin}\n"
            f"Total convocatorias encontradas: {num_elementos}\n"
        )
        print("=" * ancho_terminal)

    hay_resultados = any(diccionario_puestos[key] for key in diccionario_puestos)
    if publicaciones_fallidas and publicaciones_analizadas == 0:
        print(
            f"{Fore.RED}❌ No se pudo analizar ninguna publicación. "
            f"Publicaciones fallidas: {publicaciones_fallidas}.{Fore.RESET}"
        )
    elif publicaciones_fallidas:
        print(
            f"{Fore.YELLOW}⚠️ Resultados incompletos: "
            f"{publicaciones_fallidas} publicación/es no pudieron analizarse."
            f"{Fore.RESET}"
        )
    elif not hay_resultados:
        print(
            f"{Fore.RED}❌ No se encontraron convocatorias para el periodo seleccionado{Fore.RESET}"
        )
    else:
        print(
            f"{Fore.LIGHTCYAN_EX}✅ Los resultados se han guardado correctamente.\n"
            "📝 Puede consultar el histórico de búsquedas realizadas en el archivo: \n"
            f"{Fore.WHITE}{os.getcwd()}/BOE-oposiciones.xlsx'{Fore.LIGHTCYAN_EX}.\n"
            f"Hoja: {Fore.WHITE}'Oposiciones'."
        )

    print("=" * ancho_terminal)
