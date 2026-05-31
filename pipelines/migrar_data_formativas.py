# -*- coding: utf-8 -*-
"""
Copia CSV legacy de formativas al namespace ``Data/formativas/``.

No borra los archivos originales. Idempotente: no sobrescribe si ya existe el destino.

  python pipelines/migrar_data_formativas.py
  python pipelines/migrar_data_formativas.py --dry-run
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analisis.Ranking.seasons import FOCUS_YEARS  # noqa: E402
from competencias.paths import consolidado_write_path, partidos_anio_write_path  # noqa: E402


def _copiar(src: Path, dst: Path, *, dry_run: bool) -> bool:
    if not src.is_file():
        return False
    if dst.is_file():
        print(f"  [omitido] {dst} ya existe")
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        print(f"  [dry-run] {src} -> {dst}")
    else:
        shutil.copy2(src, dst)
        print(f"  OK {src.name} -> {dst}")
    return True


def migrar(*, dry_run: bool = False) -> int:
    data = ROOT / "Data"
    n = 0

    print("Partidos anuales:")
    for year in FOCUS_YEARS:
        legacy = data / f"partidos_{year}.csv"
        dest = partidos_anio_write_path("formativas", year)
        if _copiar(legacy, dest, dry_run=dry_run):
            n += 1

    print("Consolidado:")
    legacy_cons = data / "procesada" / "23-26.csv"
    dest_cons = consolidado_write_path("formativas")
    if _copiar(legacy_cons, dest_cons, dry_run=dry_run):
        n += 1

    print(f"Archivos migrados: {n}")
    if n:
        print(
            "Siguiente scrape escribirá en Data/formativas/. "
            "Los legacy en Data/partidos_*.csv siguen como fallback de lectura."
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Migrar CSV formativas a Data/formativas/")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    return migrar(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
