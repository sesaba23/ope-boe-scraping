import pytest

from coincidencias import (
    buscar_coincidencias_estado,
    buscar_coincidencias_local,
    convertir_en_numero,
)

def test_buscar_coincidencias_completo():
    titulo = "Resolución de 16 de abril de 2025, de la Diputación Provincial de Salamanca, referente a la convocatoria para proveer varias plazas."
    fecha_boe = "«BOE» núm. 110, de 7 de mayo de 2025, páginas 60611 a 60611 (1 pág.)"
    texto = (
        "Resolución de 16 de abril de 2025, de la Diputación Provincial de Salamanca, referente a la convocatoria para proveer varias plazas."
        "En el «Boletín Oficial de la Provincia de Salamanca» número 74, de 16 de abril de 2025, "
        "se han publicado las bases que han de regir la convocatoria para proveer:"
        "Una plaza de Suboficial/a, perteneciente a la escala de Administración Especial, subescala Servicios especiales y clase Servicio de extinción de incendios, mediante el sistema de concurso-oposición, en turno libre."
        "Tres plazas de Sargento/a, pertenecientes a la escala de Administración Especial, subescala Servicios especiales y clase Servicio de extinción de incendios, mediante el sistema de concurso-oposición, en turno libre."
        "Seis plazas de Auxiliar Administrativo, pertenecientes a la escala de Administración General, subescala Auxiliar, mediante el sistema de oposición, en turno libre."
        "Veintiseis plazas de Ingeniero/a Técnico Industrial, pertenecientes a la escala de Administración Especial, subescala Técnica y clase Media, mediante el sistema de concurso-oposición, en turno libre."
        "Dos plazas de Educador/a, pertenecientes a la escala de Administración Especial, subescala Técnica y clase Media, mediante el sistema de concurso-oposición, en turno libre."
        "El plazo de presentación de solicitudes será de veinte días naturales a contar desde el siguiente al de la publicación de esta resolución en el «Boletín Oficial del Estado»."
        "Los sucesivos anuncios referentes a esta convocatoria, cuando procedan de conformidad con las bases, se harán públicos en la forma prevista en las propias bases."
        "Salamanca, 16 de abril de 2025.–El Diputado Delegado del Área de Organización y Recursos Humanos, Carlos García Sierra."
    )
    enlace = "https://www.boe.es/buscar/doc.php?id=BOE-A-2025-9009"

    expresion = ""
    resultado = buscar_coincidencias_local(expresion, texto, titulo, fecha_boe, enlace)

    assert resultado[3] == {
        "Num_plazas": 26,
        "Puesto": "Ingeniero/a Técnico Industrial",
        "Administración": "Diputación Provincial de Salamanca",
        "Escala": "Administración Especial",
        "Subescala": "Técnica",
        "Clase": "Media",
        "Sistema": "Concurso-Oposición",
        "Turno": "Libre",
        "Fecha_boe": "7 de mayo de 2025",
        "Publicación": "«Boletín Oficial de la Provincia de Salamanca» número 74, de 16 de abril de 2025",
        "Enlace": "https://www.boe.es/buscar/doc.php?id=BOE-A-2025-9009",
        "Habitantes": 155619,
        "Latitud": 40.96497,
        "Longitud": -5.663047,
        "Municipio": "Salamanca",
        "Provincia": "Salamanca",
    }, f"El texto esperado a partir del patrón: '{expresion}' no coincide con lo esperado"

    assert len(resultado) == 5, "El diccionario tiene menos elementos de los esperados"

    expresion = "ing téc ind"
    resultado = buscar_coincidencias_local(expresion, texto, titulo, fecha_boe, enlace)

    assert resultado[0] == {
        "Num_plazas": 26,
        "Puesto": "Ingeniero/a Técnico Industrial",
        "Administración": "Diputación Provincial de Salamanca",
        "Escala": "Administración Especial",
        "Subescala": "Técnica",
        "Clase": "Media",
        "Sistema": "Concurso-Oposición",
        "Turno": "Libre",
        "Fecha_boe": "7 de mayo de 2025",
        "Publicación": "«Boletín Oficial de la Provincia de Salamanca» número 74, de 16 de abril de 2025",
        "Enlace": "https://www.boe.es/buscar/doc.php?id=BOE-A-2025-9009",
        "Habitantes": 155619,
        "Latitud": 40.96497,
        "Longitud": -5.663047,
        "Municipio": "Salamanca",
        "Provincia": "Salamanca",
    }, f"El texto esperado a partir del patrón: '{expresion}' no coincide con lo esperado"
    assert len(resultado) == 1, "El diccionario debería tener sólo un elemento"


def test_buscar_coincidencias_sin_referencia_a_publicacion():
    texto = (
        "Una plaza de Auxiliar Administrativo, perteneciente a la escala de "
        "Administración General, subescala Auxiliar, mediante el sistema de "
        "oposición, en turno libre."
    )

    resultado = buscar_coincidencias_local(
        "",
        texto,
        "Resolución, del Ayuntamiento de Ejemplo, referente a una convocatoria.",
        "«BOE» núm. 1, de 2 de enero de 2025",
        "https://www.boe.es/ejemplo",
    )

    assert resultado[0]["Publicación"] == "No disponible"


def test_buscar_coincidencias_con_municipio_entre_parentesis():
    resultado = buscar_coincidencias_local(
        "",
        "Una plaza de Ingeniero Industrial, mediante el sistema de oposición.",
        "Resolución, del Cabildo Insular de Tenerife (Santa Cruz de Tenerife), "
        "referente a una convocatoria.",
        "«BOE» núm. 1, de 2 de enero de 2025",
        "https://www.boe.es/ejemplo-tenerife",
    )

    assert resultado[0]["Municipio"] == "Santa Cruz de Tenerife"
    assert resultado[0]["Latitud"] == 28.46981
    assert resultado[0]["Longitud"] == -16.25486


def test_buscar_coincidencias_estado_con_datos_obligatorios_ausentes():
    resultado = buscar_coincidencias_estado(
        "",
        "Se convoca proceso selectivo para cubrir dos plazas.",
        "Resolución, en el Cuerpo de Ingenieros, referente a una convocatoria.",
        "Metadatos sin información adicional",
        "https://www.boe.es/ejemplo-estado",
    )

    assert resultado["Administración"] == "--"
    assert resultado["Sistema"] == "--"
    assert resultado["Fecha_boe"] == "--"


@pytest.mark.parametrize(
    "valor, esperado",
    [("12", 12), ("veintiseis", 26), ("cantidad-desconocida", "cantidad-desconocida")],
)
def test_convertir_en_numero(valor, esperado):
    assert convertir_en_numero(valor) == esperado


@pytest.mark.parametrize(
    "texto, campos_esperados",
    [
        (
            "Una plaza de Técnico de Gestión, mediante el sistema de oposición.",
            {
                "Escala": "No disponible",
                "Subescala": "No disponible",
                "Turno": "No disponible",
            },
        ),
        (
            "Dos plazas de Administrativo; pertenecientes a la escala de "
            "Administración General; por el sistema de concurso-oposición; "
            "acceso libre.",
            {
                "Escala": "Administración General",
                "Subescala": "No disponible",
                "Turno": "Acceso Libre",
            },
        ),
        (
            "Tres plazas de Ingeniero/a Técnico,\n"
            "pertenecientes a la escala de Administración Especial,\n"
            "subescala Técnica y clase Media;\n"
            "mediante el sistema de oposición.",
            {
                "Escala": "Administración Especial",
                "Subescala": "Técnica",
                "Turno": "No disponible",
            },
        ),
    ],
)
def test_buscar_coincidencias_local_con_variaciones_habituales(
    texto, campos_esperados
):
    resultado = buscar_coincidencias_local(
        "",
        texto,
        "Resolución, del Ayuntamiento de Ejemplo, referente a una convocatoria.",
        "«BOE» núm. 1, de 2 de enero de 2025",
        "https://www.boe.es/ejemplo",
    )

    assert resultado is not None
    for campo, esperado in campos_esperados.items():
        assert resultado[0][campo] == esperado
