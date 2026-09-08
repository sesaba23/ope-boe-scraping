"""CLI de administración de la base SQLite publicada."""
import argparse, json
from pathlib import Path
import gestion_base

def main():
    p=argparse.ArgumentParser(); p.add_argument("accion", choices=("verificar","publicar","manifest","actualizar")); p.add_argument("--bd", default="datos/boe.db"); p.add_argument("--repo"); p.add_argument("--confirmar", action="store_true")
    a=p.parse_args()
    repo = a.repo or (gestion_base.repositorio_configurado() if a.accion in {"publicar", "actualizar"} else None)
    if a.accion == "actualizar":
        comparacion = gestion_base.preparar_actualizacion_github(a.bd, repo)
        print(json.dumps(comparacion, ensure_ascii=False, indent=2))
        if not a.confirmar and input("¿Confirmar actualización? [s/N] ").strip().lower() not in {"s", "si", "sí"}: return
        r = gestion_base.actualizar_base_desde_github(a.bd, repo)
    else:
        r = gestion_base.publicar_base(a.bd,repo) if a.accion=="publicar" else (gestion_base.crear_manifest(a.bd) if a.accion=="manifest" else gestion_base.verificar_integridad(a.bd))
    print(json.dumps(r,ensure_ascii=False,indent=2))
if __name__ == "__main__": main()
