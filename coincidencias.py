import re


def buscar_coincidencias(expresion, texto):
    # Tomamos las 4 primeras letras de cada palabra de la expresión
    claves = [palabra[:4] for palabra in expresion.split()]

    # Creamos una expresión regular que busca palabras que empiecen igual
    # que las claves y que contengan letras, números, @ / o \ hasta la siguiente coma
    if len(claves) == 1:
        # Si solo hay una palabra, no añadimos espacios intermedios
        patron = rf"\b{claves[0]}[\w/@\\]*(es?)(.*?)(,|\.)"
    else:
        # Si hay varias palabras, las unimos con espacios
        patron = (
            r"\b"
            + r"\s+".join([rf"{clave}[\w/@\\]*(es)?" for clave in claves])
            + r"(.*?)(,|\.)"
        )

    # Buscamos coincidencias
    coincidencias = re.search(patron, texto, flags=re.IGNORECASE)
    return coincidencias
