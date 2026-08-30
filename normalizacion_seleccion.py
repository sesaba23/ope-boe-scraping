"""Normalización cerrada de turno y sistema selectivo."""

TURNOS = {
    "Turno libre": "Turno Libre", "Turno libre.": "Turno Libre", "turno libre": "Turno Libre", "Libre": "Turno Libre",
    "Promoción interna": "Promoción Interna", "Promocion interna": "Promoción Interna", "De Promoción Interna": "Promoción Interna",
    "Movilidad": "Movilidad", "De Movilidad": "Movilidad", "De Promoción Externa": "Promoción Externa",
    "Reservado A Personas Con Discapacidad": "Reservado a Personas con Discapacidad", "turno general": "Turno General",
    "Restringido": "Restringido", "No disponible": "--", "--": "--",
}
SISTEMAS = {
    "Concurso-oposición": "Concurso-Oposición", "Concurso oposición": "Concurso-Oposición",
    "Concurso-Oposición": "Concurso-Oposición", "Concurso-oposicion": "Concurso-Oposición",
    "Concurso": "Concurso", "Oposición": "Oposición", "Oposicion": "Oposición",
    "Concurso de méritos": "Concurso de Méritos", "Concurso de meritos": "Concurso de Méritos",
    "General De Acceso Libre": "General de Acceso Libre",
    "General De Acceso Libre Y Promoción Interna": "General de Acceso Libre y Promoción Interna",
    "--": "--",
}

def _normalizar(valor, reglas):
    """Preserva NULL y valores desconocidos; sólo aplica decisiones completas."""
    return valor if valor is None else reglas.get(valor, valor)

def normalizar_turno(valor):
    return _normalizar(valor, TURNOS)

def normalizar_sistema(valor):
    return _normalizar(valor, SISTEMAS)
