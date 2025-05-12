import pytest

from coincidencias import buscar_coincidencias_todas

texto = (
    "Dos plazas de INGENIERO/A Técnico Industrial, "
    "pertenecientes a la escala de Administración Especial, "
    "subescala Técnica y clase Media, "
    "mediante el sistema de concurso-oposición, en turno libre."
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

    texto_singular = "Una plaza de Suboficial/a, perteneciente a la escala de Administración Especial, subescala Servicios especiales y clase Servicio de extinción de incendios, mediante el sistema de concurso-oposición, en turno libre."
    texto_plural = "Dos plazas de Ingeniero/a Técnico Industrial, pertenecientes a la escala de Administración Especial, subescala Técnica y clase Media, mediante el sistema de concurso-oposición, en turno libre."

    expresion = ""
    resultado = buscar_coincidencias_todas(expresion, texto, titulo, fecha_boe, enlace)

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
        "Publicacion": "Boletín Oficial de la Provincia de Salamanca» número 74, de 16 de abril de 2025",
        "Enlace": "https://www.boe.es/buscar/doc.php?id=BOE-A-2025-9009",
    }, f"El texto esperado a partir del patrón: '{expresion}' no coincide con lo esperado"

    assert len(resultado) == 5, "El diccionario tiene menos elementos de los esperados"

    expresion = "ing téc ind"
    resultado = buscar_coincidencias_todas(expresion, texto, titulo, fecha_boe, enlace)

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
        "Publicacion": "Boletín Oficial de la Provincia de Salamanca» número 74, de 16 de abril de 2025",
        "Enlace": "https://www.boe.es/buscar/doc.php?id=BOE-A-2025-9009",
    }, f"El texto esperado a partir del patrón: '{expresion}' no coincide con lo esperado"
    assert len(resultado) == 1, "El diccionario debería tener sólo un elemento"
