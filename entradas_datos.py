from datetime import datetime
from colorama import Fore
import sys


def validar_fechas(fecha_inicio_dt, fecha_fin_dt, fecha_actual_dt):
    """
    Valida que las fechas de inicio y fin sean iguales o menores que la fecha actual.
    Lanza un ValueError si alguna fecha no cumple con la validación.
    """
    if fecha_inicio_dt > fecha_actual_dt:
        raise ValueError("La fecha de inicio no puede ser posterior a la fecha actual.")
    if fecha_fin_dt > fecha_actual_dt:
        raise ValueError("La fecha de fin no puede ser posterior a la fecha actual.")
    if fecha_inicio_dt > fecha_fin_dt:
        raise ValueError("La fecha de inicio no puede ser posterior a la fecha de fin.")


def solicitar_fechas_y_validar(texto_busqueda, fecha_actual, fechas, modo_test=False):
    """
    Solicita al usuario las fechas de inicio y fin, valida que sean correctas,
    y devuelve las fechas junto con el texto de búsqueda.
    """
    fecha_inicio = ""
    fecha_fin = ""

    while True:
        # Si no paso argumentos, busca todas las convocatorias publicadas en un día concreto
        if not texto_busqueda:
            texto_busqueda = input(
                f"Introduzca el {Fore.YELLOW}tipo de plaza{Fore.RESET} a buscar. "
                "[Pulse «Enter» para buscar todas las plazas publicadas]: "
            )
            if not texto_busqueda:
                fecha_inicio = input(
                    f"Introduzca la fecha de publicación del B.O.E (dd/mm/yyyy) [Por defecto: {fecha_actual} (Hoy)]: "
                )
                if not fecha_inicio:
                    fecha_inicio = fecha_actual
                fecha_fin = fecha_inicio
        # Si paso argumentos o introduzco un filtro una vez en ejecución,
        # busca las convocatorias que coincidan en el rango de fechas
        if texto_busqueda:
            fecha_inicio = input(
                f"Introduzca la fecha de inicio (dd/mm/yyyy) [Por defecto: {fecha_actual} (Hoy)]: "
            )
            # Si se elige la fecha por defecto, se asigna la fecha de hoy y no preguntamos
            #   la fecha_fin. Asumimos que sólo se quiere buscar en el día actual
            if not fecha_inicio:
                fecha_inicio = fecha_actual
                fecha_fin = fecha_actual
            else:  # En caso contrario pregunta por la fecha de fin
                fecha_fin = input(
                    f"Introduzca la fecha de fin (dd/mm/yyyy) [Por defecto: {fecha_actual} (Hoy)]: "
                )
            if not fecha_fin:  # Por defecto la fecha_fin es la fecha de hoy
                fecha_fin = fecha_actual

        # Comprobar si la fecha de inicio es válida
        try:
            # Convertir las fechas a objetos datetime
            fecha_inicio_dt = datetime.strptime(fecha_inicio, "%d/%m/%Y")
            fecha_fin_dt = datetime.strptime(fecha_fin, "%d/%m/%Y")
            fecha_actual_dt = datetime.strptime(fecha_actual, "%d/%m/%Y")

            validar_fechas(fecha_inicio_dt, fecha_fin_dt, fecha_actual_dt)
            # Calculo las direcciones necesarias en función de las fechas en las que se
            #   van a buscar las distintas oposiciones
            lista_fechas = fechas.generar_rango_fechas(fecha_inicio, fecha_fin)
            print(f"\n{Fore.BLUE}✅ Fechas válidas.\n")
            return texto_busqueda, fecha_inicio, fecha_fin, lista_fechas

        except ValueError as e:
            print(f"\n{Fore.RED}❌ {e}\n")
            if modo_test:
                raise e  # Elevar la excepción solo en modo test
