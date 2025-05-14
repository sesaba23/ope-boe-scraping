from fechas import convertir_fecha

import pandas as pd
from openpyxl import Workbook
import os, sys
import re
from colorama import Fore
import warnings


def preparar_excel_y_dataframes():
    # Cargamos un Excel con las fechas de los días que nos interesan
    # Verificar si el archivo Excel existe. Si no, crearlo
    if not os.path.exists("BOE-oposiciones.xlsx"):
        # Crear un nuevo libro de Excel
        wb = Workbook()
        # Renombrar la hoja activa a "busquedas"
        ws1 = wb.active
        ws1.title = "Búsquedas"
        # ws1["A1"] = "Código"
        # Crear la segunda hoja
        ws2 = wb.create_sheet(title="Oposiciones")
        # Guardar el archivo
        wb.save("BOE-oposiciones.xlsx")

    # Cargamos el archivo Excel
    excel_file = pd.ExcelFile("BOE-oposiciones.xlsx")

    # Leer todas las hojas como diccionario de DataFrames
    dataframes_dict = {
        sheet_name: excel_file.parse(sheet_name)
        for sheet_name in excel_file.sheet_names
    }

    return dataframes_dict


def combinar_dataframes(
    diccionario_puestos, diccionario_busquedas, df_opo_guardadas, df_busquedas
):
    """
    Código para crear el DataFrame
    """
    # Convertimos el "diccionario_puestos" en un DataFrame de pandas
    df_diccionario_puestos = pd.DataFrame(diccionario_puestos)
    # Combinar el DataFrame existente (df_opo_guardadas) con el nuevo (df_diccionario_puestos)
    df_combinado = pd.concat(
        [df_opo_guardadas, df_diccionario_puestos], ignore_index=True
    )

    # Eliminar duplicados si es necesario, basándonos en columnas clave
    #   (por ejemplo, "Puesto" y "Fecha")
    df_combinado = df_combinado.drop_duplicates(
        subset=["Puesto", "Fecha_boe", "Administración", "Enlace"], keep="last"
    )

    # Ahora convierto el "diccionario_busquedas" en otro DataFrame
    df_diccionario_busquedas = pd.DataFrame(diccionario_busquedas)
    # Combinar el DataFrame existente (df_busquedas) con el nuevo (df_diccionario_puestos)
    df_busquedas_combinado = pd.concat(
        [df_diccionario_busquedas, df_busquedas], ignore_index=True
    )
    # Eliminar duplicados si es necesario, basándonos en columnas clave (por ejemplo, "Código")
    df_busquedas_combinado = df_busquedas_combinado.drop_duplicates(
        subset=["Código"], keep="last"
    )

    return df_combinado, df_busquedas_combinado


def guardar_excel(df_combinado, df_busquedas_combinado):
    """
    Código para guardar los resultados en un archivo Excel
    """
    # Guardar los DataFrame en el archivo Excel creado al principio si está cerrado
    try:
        with pd.ExcelWriter(
            "BOE-oposiciones.xlsx",
            mode="a",
            engine="openpyxl",
            if_sheet_exists="replace",
        ) as writer:
            df_busquedas_combinado.to_excel(writer, sheet_name="Búsquedas", index=False)
            df_combinado.to_excel(writer, sheet_name="Oposiciones", index=False)
    except PermissionError:
        print(
            f"\n{Fore.RED}El archivo 'BOE-oposiciones.xlsx' está abierto. "
            f"Cierre el archivo y vuelva a intentarlo.{Fore.RESET}"
        )
        sys.exit(0)


def prepara_data_frame_mostrar_resultados(texto_busqueda, df_combinado, lista_fechas):
    """
    Buscamos los resultados buscados por el usuario dentro del propio
    Dataframe, incluidas las fechas de inicio y fin
    """

    # Convertir la columna "Fecha" del DataFrame al formato datetime en una nueva columna
    #   "Fecha_dt" para facilitar la comparación de fechas
    #   Si cambiamos directamente el formato de la columna fecha, al ejecutar, da un warning
    df_combinado["Fecha_dt"] = df_combinado["Fecha_boe"].apply(convertir_fecha)

    # Filtrar el DataFrame por el rango de fechas
    # Las fechas de inicio y final son el primer y último elemento de "lista_fechas"
    df_combinado_filtrado_por_fecha = df_combinado[
        (df_combinado["Fecha_dt"] >= lista_fechas[0])
        & (df_combinado["Fecha_dt"] <= lista_fechas[-1])
    ]

    # Ordenar el DataFrame por la columna "Fecha_dt" en orden cronológico inverso
    df_combinado_filtrado_por_fecha = df_combinado_filtrado_por_fecha.sort_values(
        by="Fecha_dt", ascending=True
    )

    # Eliminar la columna auxiliar "Fecha_dt" si no es necesaria
    df_combinado_filtrado = df_combinado_filtrado_por_fecha.drop(columns=["Fecha_dt"])

    palabras_busqueda = texto_busqueda.split()
    patron_regex = (
        r"\b"
        + r"\s+".join([rf"{clave}[\w/@\\]*(es)?" for clave in palabras_busqueda])
        + r"(.*?)"
    )
    # Desactivar warnings relacionados con expresiones regulares
    warnings.filterwarnings("ignore", message="This pattern is interpreted")

    # Filtrar el DataFrame por coincidencias en la columna "Puesto"
    df_filtrado_por_patron = df_combinado_filtrado_por_fecha[
        df_combinado_filtrado_por_fecha["Puesto"].str.contains(
            patron_regex, flags=re.IGNORECASE, na=False
        )
    ]
    # Restaurar los warnings después de la operación
    warnings.filterwarnings("default", message="This pattern is interpreted")

    return df_filtrado_por_patron
