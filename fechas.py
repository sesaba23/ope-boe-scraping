from datetime import datetime, timedelta


def generar_rango_fechas(inicio, fin):
    """
    Genera una lista de fechas entre dos fechas dadas.
    Argumentos:
        :param inicio: Fecha de inicio en formato "YYYY/MM/DD".
        :param fin: Fecha de fin en formato "YYYY/MM/DD".
    Retorna:
        :return: Lista de fechas en formato "YYYY/MM/DD".
    """
    # Convertimos las cadenas de texto a objetos datetime
    # fecha_inicio = datetime.strptime(inicio, "%Y/%m/%d")
    # fecha_fin = datetime.strptime(fin, "%Y/%m/%d")
    fecha_inicio = datetime.strptime(inicio, "%d/%m/%Y")
    fecha_fin = datetime.strptime(fin, "%d/%m/%Y")

    # Generamos la lista de fechas
    lista_fechas = []
    while fecha_inicio <= fecha_fin:
        lista_fechas.append(fecha_inicio.strftime("%Y/%m/%d"))
        fecha_inicio += timedelta(days=1)

    return lista_fechas


def fecha_hoy():
    """
    Devuelve la fecha de hoy en formato "DD/MM/YYYY".
    :return: String con la fecha de hoy.
    """
    return datetime.now().strftime("%d/%m/%Y")


# Función para convertir el formato "día de mes de año" a datetime
def convertir_fecha(fecha_str):
    meses = {
        "enero": "01",
        "febrero": "02",
        "marzo": "03",
        "abril": "04",
        "mayo": "05",
        "junio": "06",
        "julio": "07",
        "agosto": "08",
        "septiembre": "09",
        "octubre": "10",
        "noviembre": "11",
        "diciembre": "12",
    }
    # Reemplazar el nombre del mes por su número correspondiente
    for mes, numero in meses.items():
        if mes in fecha_str:
            fecha_str = fecha_str.replace(f" de {mes} de ", f"/{numero}/")
            break
    # Convertir al formato datetime
    return datetime.strptime(fecha_str, "%d/%m/%Y")
