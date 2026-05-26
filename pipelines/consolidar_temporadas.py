# -*- coding: utf-8 -*-
"""
Arma ``Data/procesada/23-26.csv`` uniendo partidos de las temporadas en foco.

Fuentes (en orden por año):
  - ``Data/partidos_{año}.csv`` si existe
  - filas del año en ``Data/procesada/19-24.csv`` (legacy)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analisis.Ranking.seasons import (  # noqa: E402
    FOCUS_YEARS,
    PARTIDOS_CONSOLIDADO,
    PARTIDOS_LEGACY,
    filtrar_anios,
)
from utils.open_csv import leer_csv_con_encoding_detectado  # noqa: E402


def _detect_sep(path: Path) -> str:
    import chardet

    raw = path.read_bytes()[:8000]
    enc = chardet.detect(raw).get("encoding") or "utf-8"
    sample = raw.decode(enc, errors="replace")
    return ";" if sample.count(";") > sample.count(",") else ","


def _cargar_anio(year: int, legacy: pd.DataFrame | None, sep: str) -> pd.DataFrame:
    per_year = ROOT / "Data" / f"partidos_{year}.csv"
    if per_year.is_file():
        file_sep = _detect_sep(per_year) if sep == ";" else sep
        return leer_csv_con_encoding_detectado(str(per_year), file_sep)
    if legacy is not None and "anio" in legacy.columns:
        sub = legacy[legacy["anio"].astype(int) == year]
        if not sub.empty:
            return sub.copy()
    return pd.DataFrame()


def consolidar(
    years: tuple[int, ...] = FOCUS_YEARS,
    *,
    sep: str = ";",
    output: Path = PARTIDOS_CONSOLIDADO,
) -> pd.DataFrame:
    legacy = None
    if PARTIDOS_LEGACY.is_file():
        legacy = leer_csv_con_encoding_detectado(str(PARTIDOS_LEGACY), sep)

    partes: list[pd.DataFrame] = []
    for year in years:
        chunk = _cargar_anio(year, legacy, sep)
        if chunk.empty:
            print(f"  [aviso] Sin datos para {year}")
            continue
        partes.append(chunk)
        print(f"  {year}: {len(chunk)} filas")

    if not partes:
        raise SystemExit("No se encontraron partidos para ninguna temporada.")

    out = pd.concat(partes, ignore_index=True)
    out = filtrar_anios(out, years)
    from mapeos.exclusiones_partidos import aplicar_exclusiones  # noqa: E402

    out, n_exc = aplicar_exclusiones(out)
    if n_exc:
        print(f"  Exclusiones aplicadas: {n_exc} partidos")
    output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output, index=False, encoding="utf-8-sig", sep=sep)
    print(f"Escrito: {output} ({len(out)} filas)")
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Consolidar partidos 2023-2026.")
    p.add_argument(
        "--years",
        type=int,
        nargs="+",
        default=list(FOCUS_YEARS),
        help="Temporadas a incluir.",
    )
    p.add_argument("--sep", default=";")
    p.add_argument("--output", type=Path, default=PARTIDOS_CONSOLIDADO)
    args = p.parse_args()
    consolidar(tuple(args.years), sep=args.sep, output=args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
