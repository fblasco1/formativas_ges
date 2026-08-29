# -*- coding: utf-8 -*-
"""
Descarga el fixture de Liga Federal Formativa U15 (Cadetes) desde argentina.basketball.

ATENCIÓN: CargarFixture con compCatId 4643/5117 devuelve Liga Federal MAYORES, no Cadetes.
Para Cadetes U15 usar GES:
  python analysis/descargar_fixture_lff_ges.py --genero masc

Este script queda como referencia del portal argentino (mayores / IDs internos).

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest.argbasket.fixture import get_fixture_partidos_lff, write_csv
from ingest.argbasket.lff_constants import LFF_U15_TORNEO_COMP_CAT_ID


def main() -> int:
    p = argparse.ArgumentParser(
        description="Fixture LFF Cadetes U15 desde argentina.basketball"
    )
    p.add_argument("--temporada", default="2025", help="Temporada (metadata en nombre de salida)")
    p.add_argument("--genero", choices=("masc", "fem"), default="masc")
    p.add_argument(
        "--comp-cat-id",
        type=int,
        default=0,
        help="compCatId torneo (default: 4643 masc / 4644 fem)",
    )
    p.add_argument("--fecha-ini", default="2025-01-01")
    p.add_argument("--fecha-fin", default="2026-05-10")
    p.add_argument("--output", default="")
    p.add_argument("--sin-horas-reales", action="store_true")
    p.add_argument("--progress", action="store_true")
    args = p.parse_args()

    genero_lbl = "masculino" if args.genero == "masc" else "femenino"
    comp_cat_id = args.comp_cat_id or LFF_U15_TORNEO_COMP_CAT_ID[args.genero]

    print(f"Categoría: U15 Cadetes ({genero_lbl})", file=sys.stderr)
    print(f"compCatId torneo: {comp_cat_id}", file=sys.stderr)
    print(f"Rango: {args.fecha_ini} .. {args.fecha_fin}", file=sys.stderr)

    rows = get_fixture_partidos_lff(
        comp_cat_id=comp_cat_id,
        fecha_ini=args.fecha_ini,
        fecha_fin=args.fecha_fin,
        incluir_horas_reales=not args.sin_horas_reales,
        progress=args.progress,
    )
    print(f"Partidos: {len(rows)}", file=sys.stderr)

    out = args.output or str(
        ROOT
        / "outputs"
        / "lff"
        / f"fixture_cadetes_{genero_lbl}_{args.temporada.strip()}.csv"
    )
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    write_csv(out, rows)
    print(f"Guardado: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
