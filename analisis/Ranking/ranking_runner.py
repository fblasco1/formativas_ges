"""
CLI opcional: genera ranking desde `Data/procesada/matches_clean.parquet`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from analisis.ranking.data_loader import load_matches_from_parquet, run_ranking_on_dataframe


def main() -> None:
    p = argparse.ArgumentParser(description="Ranking FeBAMBA FIBA-adaptado desde matches_clean.")
    p.add_argument(
        "--parquet",
        type=Path,
        default=Path("Data/procesada/matches_clean.parquet"),
        help="Ruta al parquet normalizado",
    )
    p.add_argument("--age-group", default=None, help="Filtrar por substring en age_group/categoria")
    p.add_argument("--genero", default=None, help="MASCULINO / FEMENINO / MIXTO")
    p.add_argument("--out", type=Path, default=None, help="CSV de salida (opcional)")
    args = p.parse_args()

    df = load_matches_from_parquet(args.parquet)
    eng = run_ranking_on_dataframe(df, age_group_filter=args.age_group, genero_filter=args.genero)
    out_df = eng.get_ranking()
    if args.out:
        out_df.to_csv(args.out, index=False)
    else:
        print(out_df.to_string(index=False))


if __name__ == "__main__":
    main()
