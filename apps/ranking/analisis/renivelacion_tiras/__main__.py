# -*- coding: utf-8 -*-
"""
Pipeline de renivelación por Tira (incremental).

  python -m analisis.renivelacion_tiras --congelar-historico
  python -m analisis.renivelacion_tiras --actualizar-2026
  python -m analisis.renivelacion_tiras
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analisis.renivelacion_tiras.pipeline import (  # noqa: E402
    actualizar_2026,
    congelar_historico,
    ejecutar_completo,
    exportar_baseline_comparativo,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Renivelación por Tira (2023-2026 incremental).")
    p.add_argument(
        "--congelar-historico",
        action="store_true",
        help="Procesa 2023-2025 y guarda caché congelado.",
    )
    p.add_argument(
        "--actualizar-2026",
        action="store_true",
        help="Suma partidos_2026.csv al caché histórico.",
    )
    p.add_argument(
        "--baseline",
        action="store_true",
        help="Exporta además Ranking_Tiras_Baseline_2026.csv.",
    )
    p.add_argument("-q", "--quiet", action="store_true")
    args = p.parse_args(argv)
    verbose = not args.quiet

    if args.congelar_historico and not args.actualizar_2026:
        congelar_historico(verbose=verbose)
        if args.baseline:
            exportar_baseline_comparativo(verbose=verbose)
        return 0

    if args.actualizar_2026 and not args.congelar_historico:
        actualizar_2026(verbose=verbose)
        if args.baseline:
            exportar_baseline_comparativo(verbose=verbose)
        return 0

    ejecutar_completo(verbose=verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
