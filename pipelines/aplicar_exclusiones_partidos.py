# -*- coding: utf-8 -*-
"""
Aplica mapeos/exclusiones_partidos.json a CSV de partidos en Data/.

  python pipelines/aplicar_exclusiones_partidos.py
  python pipelines/aplicar_exclusiones_partidos.py --year 2024
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analisis.Ranking.seasons import FOCUS_YEARS, PROCESADA_DIR  # noqa: E402
from mapeos.exclusiones_partidos import aplicar_exclusiones, cargar_exclusiones  # noqa: E402
from utils.open_csv import leer_csv_con_encoding_detectado  # noqa: E402


def _sep(path: Path) -> str:
    sample = path.read_bytes()[:4000].decode("utf-8", errors="replace")
    return ";" if sample.count(";") > sample.count(",") else ","


def aplicar_archivo(path: Path, *, dry_run: bool = False) -> int:
    if not path.is_file():
        print(f"  [omitido] {path}")
        return 0
    sep = _sep(path)
    df = leer_csv_con_encoding_detectado(str(path), sep)
    antes = len(df)
    nuevo, n = aplicar_exclusiones(df)
    if n == 0:
        print(f"  {path.name}: sin cambios")
        return 0
    if dry_run:
        print(f"  {path.name}: se quitarían {n} de {antes} filas")
        return n
    nuevo.to_csv(path, index=False, encoding="utf-8-sig", sep=sep)
    print(f"  {path.name}: {n} eliminados ({antes} -> {len(nuevo)})")
    return n


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Aplicar exclusiones de partidos a CSV.")
    p.add_argument("--year", type=int, nargs="*", default=list(FOCUS_YEARS))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    reglas = cargar_exclusiones()
    if not reglas:
        print("No hay reglas en exclusiones_partidos.json")
        return 1

    total = 0
    for year in args.year:
        for path in (
            ROOT / "Data" / f"partidos_{year}.csv",
            PROCESADA_DIR / f"{year}.csv",
        ):
            total += aplicar_archivo(path, dry_run=args.dry_run)

    print(f"Total filas afectadas: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
