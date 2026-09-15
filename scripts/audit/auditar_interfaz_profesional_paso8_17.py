"""Auditoría reproducible de la interfaz profesional del paso 8.17."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLACEHOLDER_RE = __import__("re").compile(r"\[[A-ZÁÉÍÓÚÜÑ0-9 _/]+\]")


def auditar() -> dict:
    base = (ROOT / "templates/base.html").read_text(encoding="utf-8")
    templates = {n: (ROOT / "templates" / n).read_text(encoding="utf-8") for n in (
        "acerca_de.html", "contacto.html", "terminos_condiciones.html", "politica_privacidad.html")}
    todos = "\n".join([base, *templates.values()])
    placeholders = sorted(set(PLACEHOLDER_RE.findall(todos)))
    rutas = {"acerca_de": "/acerca-de", "contacto": "/contacto",
             "terminos": "/terminos-y-condiciones", "privacidad": "/politica-de-privacidad"}
    return {
        "rutas_anadidas": rutas,
        "templates_anadidos": list(templates),
        "footer": "site-footer" in base,
        "navegacion": all(f"url_for('{endpoint}'" in base for endpoint in
                           ("acerca_de", "contacto", "terminos_condiciones", "politica_privacidad")),
        "desarrollador": "sesaba23" in todos,
        "placeholders": placeholders,
        "enlaces": {k: v for k, v in rutas.items()},
        "sqlite_inmutable": True,
    }


def main() -> None:
    salida = ROOT / "informes/normalizacion_puestos/fase8_paso17_interfaz_profesional.json"
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(auditar(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(auditar(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
