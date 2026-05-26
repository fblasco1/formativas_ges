# -*- coding: utf-8 -*-
"""
Aplica equipos_map.json a los CSV de partidos, consolida y opcionalmente regenera rankings.

Uso típico tras editar mapeos:
  python pipelines/normalizar_equipos.py --consolidar --ranking
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analisis.Ranking.seasons import FOCUS_YEARS, PARTIDOS_CONSOLIDADO  # noqa: E402
from mapeos.loader import (  # noqa: E402
    cargar_mapeo_equipos,
    normalizar_columna_equipos,
)
from utils.open_csv import leer_csv_con_encoding_detectado  # noqa: E402

DATA_DIR = ROOT / "Data"


def _detect_sep(path: Path) -> str:
    sample = path.read_bytes()[:8000].decode("utf-8", errors="replace")
    return ";" if sample.count(";") > sample.count(",") else ","


def normalizar_archivo(
    path: Path,
    mapeo: dict,
    *,
    sep: str | None = None,
    in_place: bool = True,
) -> tuple[int, int]:
    """Devuelve (filas, cambios en local+visitante)."""
    file_sep = sep or _detect_sep(path)
    df = leer_csv_con_encoding_detectado(str(path), file_sep)
    cambios = 0
    for col in ("local", "visitante"):
        if col not in df.columns:
            continue
        antes = df[col].astype(str)
        df[col] = normalizar_columna_equipos(df[col], mapeo)
        cambios += int((antes != df[col].astype(str)).sum())
    dest = path if in_place else path.with_suffix(".normalizado.csv")
    df.to_csv(dest, index=False, encoding="utf-8-sig", sep=file_sep)
    return len(df), cambios


def normalizar_data(
    years: tuple[int, ...] = FOCUS_YEARS,
    *,
    sep: str = ";",
    verbose: bool = True,
) -> dict:
    mapeo = cargar_mapeo_equipos()
    stats = {"archivos": 0, "filas": 0, "celdas_cambiadas": 0}

    for year in years:
        path = DATA_DIR / f"partidos_{year}.csv"
        if not path.is_file():
            if verbose:
                print(f"  [omitido] {path.name}")
            continue
        filas, cambios = normalizar_archivo(path, mapeo, sep=sep)
        stats["archivos"] += 1
        stats["filas"] += filas
        stats["celdas_cambiadas"] += cambios
        if verbose:
            print(f"  {path.name}: {filas} filas, {cambios} celdas actualizadas")

    legacy = DATA_DIR / "procesada" / "19-24.csv"
    if legacy.is_file():
        filas, cambios = normalizar_archivo(legacy, mapeo, sep=sep)
        stats["archivos"] += 1
        stats["filas"] += filas
        stats["celdas_cambiadas"] += cambios
        if verbose:
            print(f"  {legacy.name}: {filas} filas, {cambios} celdas actualizadas")

    return stats


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Normalizar nombres de equipos en CSV de partidos.")
    p.add_argument(
        "--years",
        type=int,
        nargs="+",
        default=list(FOCUS_YEARS),
        help="Temporadas (partidos_{año}.csv).",
    )
    p.add_argument("--sep", default=";", help="Separador CSV.")
    p.add_argument(
        "--consolidar",
        action="store_true",
        help="Regenerar Data/procesada/23-26.csv tras normalizar.",
    )
    p.add_argument(
        "--ranking",
        action="store_true",
        help="Ejecutar python -m analisis.Ranking tras consolidar.",
    )
    p.add_argument("-q", "--quiet", action="store_true")
    args = p.parse_args(argv)

    verbose = not args.quiet
    if verbose:
        print("Normalizando partidos con equipos_map.json...")
    stats = normalizar_data(tuple(args.years), sep=args.sep, verbose=verbose)
    if verbose:
        print(
            f"Listo: {stats['archivos']} archivos, {stats['filas']} filas, "
            f"{stats['celdas_cambiadas']} celdas cambiadas."
        )

    if args.consolidar:
        if verbose:
            print("Consolidando temporadas...")
        from pipelines.consolidar_temporadas import consolidar  # noqa: E402

        consolidar(tuple(args.years), sep=args.sep, output=PARTIDOS_CONSOLIDADO)

    if args.ranking:
        if verbose:
            print("Regenerando rankings...")
        import subprocess

        r = subprocess.run(
            [sys.executable, "-m", "analisis.Ranking", "--years", *[str(y) for y in args.years]],
            cwd=str(ROOT),
        )
        if r.returncode != 0:
            return r.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
