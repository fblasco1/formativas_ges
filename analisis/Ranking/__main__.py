# -*- coding: utf-8 -*-
"""CLI: regenerar rankings desde CSV consolidado de partidos."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analisis.Ranking.core import (  # noqa: E402
    DEFAULT_EXCLUDE_CATEGORIES,
    DEFAULT_YEARS,
    preparar_datos_ranking,
    process_all_years,
)
from analisis.Ranking.seasons import FOCUS_YEARS, resolve_partidos_consolidado  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    years_help = " ".join(str(y) for y in FOCUS_YEARS)
    p = argparse.ArgumentParser(
        description="Calcula Power Ranking por año y acumulado (BP + ORP + pesos)."
    )
    p.add_argument(
        "--input",
        type=Path,
        default=None,
        help=(
            "CSV consolidado de partidos. "
            f"Default: {resolve_partidos_consolidado()} "
            "(o Data/procesada/19-24.csv si aún no existe 23-26.csv)."
        ),
    )
    p.add_argument("--sep", default=";", help="Separador del CSV (default: ;).")
    p.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "Data" / "procesada",
        help="Directorio de salida para rankings (default: Data/procesada).",
    )
    p.add_argument(
        "--years",
        type=int,
        nargs="+",
        default=list(DEFAULT_YEARS),
        help=f"Años a procesar en orden (default: {years_help}).",
    )
    p.add_argument(
        "--exclude-categoria",
        action="append",
        dest="exclude_categorias",
        default=[],
        help="Categoría a excluir (repetible). Default: MINI y PREMINI.",
    )
    p.add_argument("-q", "--quiet", action="store_true", help="Sin mensajes de progreso.")
    args = p.parse_args(argv)

    input_path = args.input or resolve_partidos_consolidado()
    if not input_path.is_file():
        print(f"No existe el archivo de entrada: {input_path}", file=sys.stderr)
        print(
            "Generá Data/procesada/23-26.csv con: "
            "python pipelines/consolidar_temporadas.py",
            file=sys.stderr,
        )
        return 1

    exclude = (
        tuple(args.exclude_categorias)
        if args.exclude_categorias
        else DEFAULT_EXCLUDE_CATEGORIES
    )
    data, ranking_base = preparar_datos_ranking(
        input_path,
        sep=args.sep,
        exclude_categories=exclude,
        years=args.years,
    )
    if data.empty:
        print(
            f"No hay partidos para los años {args.years} en {input_path}",
            file=sys.stderr,
        )
        return 1

    _, ranking_total = process_all_years(
        data,
        args.years,
        ranking_init=ranking_base,
        output_dir=args.output_dir,
        verbose=not args.quiet,
    )
    if not args.quiet:
        print(f"Listo. Equipos en ranking acumulado: {len(ranking_total)}")
        print(f"Salida en: {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
