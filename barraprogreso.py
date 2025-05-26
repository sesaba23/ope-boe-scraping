import time
import sys
from colorama import init, Fore, Style

init(autoreset=True)


def barra_progreso_color(iterable, total=None):
    """
    Muestra una barra de progreso en consola con un texto adicional.
    No se usa en la versión actual de la aplicación.
    Se mantiene a efectos ilustrativos
    """
    if total is None:
        total = len(iterable)
    spinner = ["|", "/", "-", "\\"]
    for i, item in enumerate(iterable):
        progreso = int(50 * (i + 1) / total)
        barra = Fore.GREEN + "#" * progreso + Fore.WHITE + "-" * (50 - progreso)
        porcentaje = (i + 1) * 100 / total
        spin = spinner[i % len(spinner)]
        sys.stdout.write(
            f"\r{Style.BRIGHT}[{barra}] {Fore.CYAN}{porcentaje:6.2f}% {spin}"
        )
        sys.stdout.flush()
        yield item
    print("\n")  # Para nueva línea al terminar


# Ejemplo de uso
# for _ in barra_progreso_color(range(100), total=100):
#    time.sleep(0.05)
