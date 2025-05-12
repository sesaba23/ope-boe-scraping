import os
import shutil
import time
from colorama import Fore, Style


def imprimir_diccionario_puestos(diccionario_puestos, f_inicio, f_fin, busqueda=""):
    """
    Imprime en pantalla cada elemento del diccionario_puestos de uno en uno.
    :param diccionario_puestos: Diccionario que contiene información de los puestos.
    """
    # Asumimos que todas las listas tienen la misma longitud
    num_elementos = len(
        diccionario_puestos["Fecha_boe"]
    )  # Usamos "Fecha" como referencia

    ancho_terminal = shutil.get_terminal_size().columns

    print("=" * ancho_terminal)

    print(f"{Style.BRIGHT}PLazas publicadas en el BOE (Boletín Oficial del Estado): ")

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
            f"{Fore.CYAN}Publicación:{Fore.RESET}\t {diccionario_puestos['Publicacion'][i]}"
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

    if not any(diccionario_puestos[key] for key in diccionario_puestos):
        print(
            f"{Fore.RED}No se encontraron convocatorias para el periodo seleccionado{Fore.RESET}"
        )
    else:
        print(
            f"{Fore.LIGHTCYAN_EX}Los resultados se han guardado correctamente.\n"
            "Puede consultar el histórico de búsquedas realizadas en el archivo: \n"
            f"{Fore.WHITE}{os.getcwd()}/BOE-oposiciones.xlsx'{Fore.LIGHTCYAN_EX}.\n"
            f"Hoja: {Fore.WHITE}'Oposiciones'."
        )

    print("=" * ancho_terminal)


# Ejemplo de uso
diccionario_puestos = {
    "Fecha": [],
    "Puesto": [],
    "Administración": [],
    "Escala": [],
    "Publicación": [],
    "Enlace": [],
}
# Vamos almacenando los puestos encontrados en el diccionario
diccionario_puestos["Fecha"].append("fecha_publicacion")
diccionario_puestos["Puesto"].append("texto_extraido")
diccionario_puestos["Administración"].append("texto_administracion")
diccionario_puestos["Escala"].append("texto_escala")
diccionario_puestos["Publicación"].append("texto_publicacion")
diccionario_puestos["Enlace"].append("enlace")
