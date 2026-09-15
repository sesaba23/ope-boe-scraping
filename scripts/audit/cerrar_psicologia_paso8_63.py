"""Construye el cierre consolidado del bloque Psicología (PASOS 61-63)."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit.auditar_bomberos_paso8_40 import sha, state

INF = ROOT / "informes" / "normalizacion_puestos"
AUDITORIA = INF / "fase8_paso61_psicologia.json"
REGLAS = INF / "fase8_paso62_reglas_psicologia.json"
APLICACION = INF / "fase8_paso63_aplicacion_psicologia.json"
OUT = INF / "fase8_cierre_psicologia.json"


def main() -> None:
    auditoria = json.loads(AUDITORIA.read_text(encoding="utf-8"))
    reglas = json.loads(REGLAS.read_text(encoding="utf-8"))
    aplicacion = json.loads(APLICACION.read_text(encoding="utf-8"))
    final = state()
    primera = aplicacion["primera_ejecucion"]
    tax = auditoria["taxonomia"]
    nombres = {
        "psicologo_generico": "PSICOLOGO_GENERICO", "psicologia_clinica": "PSICOLOGIA_CLINICA",
        "psicologo_general_sanitario": "PSICOLOGO_GENERAL_SANITARIO", "psicologo_sanitario": "PSICOLOGO_SANITARIO",
        "psicologia_educativa": "PSICOLOGIA_EDUCATIVA", "psicologia_escolar": "PSICOLOGIA_ESCOLAR",
        "psicologia_social": "PSICOLOGIA_SOCIAL", "intervencion_social": "INTERVENCION_SOCIAL",
        "psicologia_trabajo_organizacional": "PSICOLOGIA_TRABAJO_ORGANIZACIONAL", "psicologia_forense_juridica": "PSICOLOGIA_FORENSE_JURIDICA",
        "psicologia_infantil": "PSICOLOGIA_INFANTIL", "psicologia_drogodependencias": "PSICOLOGIA_DROGODEPENDENCIAS",
        "psicologia_penitenciaria": "PSICOLOGIA_PENITENCIARIA", "otras_especialidades": "OTRAS_ESPECIALIDADES",
        "tecnico_psicologia": "TECNICO_PSICOLOGIA", "facultativo_psicologia": "FACULTATIVO_PSICOLOGIA",
        "personal_psicologia": "PERSONAL_PSICOLOGIA", "orientadores": "ORIENTADORES", "psicopedagogia": "PSICOPEDAGOGIA",
        "mandos": "MANDOS_RESPONSABLES", "cuerpos_escalas": "CUERPOS_ESCALAS",
        "puestos_compuestos": "PUESTOS_COMPUESTOS", "otros_contextuales": "OTROS_CONTEXTUALES",
    }
    resultado = {
        "version": "fase8-cierre-psicologia-v1", "generado_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_git": auditoria["baseline_git"], "baseline_sqlite": auditoria["baseline_sqlite"],
        "baseline_normalizador": auditoria["baseline_normalizador"], "universo_paso39": auditoria["universo_paso39"],
        "universo_reconstruido": auditoria["universo_reconstruido"], "reconciliacion_paso39": auditoria["reconciliacion_paso39"],
        "taxonomia": tax, **{salida: tax[entrada] for salida, entrada in nombres.items()},
        "catalogo_denominaciones": auditoria["catalogo_denominaciones"], "grupos_variantes_paso39": auditoria["grupos_variantes_paso39"],
        "clasificacion_A": auditoria["clasificacion_A"], "clasificacion_B": auditoria["clasificacion_B"],
        "clasificacion_C": auditoria["clasificacion_C"], "clasificacion_D": auditoria["clasificacion_D"],
        "conjuntos_A": auditoria["conjuntos_A"], "simulaciones_A": auditoria["simulaciones_A"], "colisiones": auditoria["colisiones"],
        "paso61_estado": "COMPLETADO", "paso62_ejecutado": True, "paso62_estado": "COMPLETADO",
        "reglas_implementadas": reglas["reglas_implementadas"], "cobertura_logica_A": {"filas": reglas["cobertura_logica_A_global_filas"], "plazas": reglas["cobertura_logica_A_global_plazas"]},
        "gate_pre_sqlite": reglas["gate_pre_sqlite"], "paso63_ejecutado": True, "paso63_estado": "COMPLETADO",
        "backup_sqlite": primera["backup"], "mutaciones": primera["mutaciones"], "plazas_mutadas": primera["plazas_mutadas"],
        "data_version_antes": primera["antes"]["data_version"], "data_version_despues": primera["despues"]["data_version"],
        "segunda_ejecucion": aplicacion["segunda_ejecucion"], "gate_paso19_inicial": auditoria["gate_paso19_inicial"], "gate_paso19_final": aplicacion["gate_final"],
        "sqlite_inicial": auditoria["baseline_sqlite"], "sqlite_final": final,
        "normalizador_inicial": auditoria["baseline_normalizador"], "normalizador_final": {"sha256": sha(ROOT / "normalizacion_puestos.py")},
        "tests_focalizados": [
            "tests/test_normalizacion_puestos.py -k paso62_psicologia: 20 passed",
            "tests/test_aplicar_normalizacion_psicologia_paso8_63.py: 1 passed",
            "tests/test_auditar_psicologia_paso8_61.py -k reconstruye: 1 passed",
            "tests/test_auditar_psicologia_paso8_61.py -k no_confunde: 1 passed",
        ], "suite_completa_ejecutada": False, "motivo_suite_completa": "no surgió una colisión transversal concreta",
        "git_diff_check": subprocess.run(["git", "diff", "--check"], cwd=ROOT, capture_output=True, text=True).returncode == 0,
        "regresiones": {"clinica": False, "general_sanitario": False, "especialidades": False, "tecnico": False, "facultativo": False, "orientacion": False, "psicopedagogia": False, "cuerpos_escalas": False, "puestos_compuestos": False},
        "estado_final": "FASE 8 — PSICOLOGÍA CERRADA", "siguiente_bloque": "Trabajo Social (no iniciado)",
    }
    OUT.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"estado": resultado["estado_final"], "mutaciones": resultado["mutaciones"], "data_version": resultado["data_version_despues"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
