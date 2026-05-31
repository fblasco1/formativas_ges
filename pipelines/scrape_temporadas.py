# -*- coding: utf-8 -*-
"""Scrapea temporadas formativas (wrapper de scrape_competencia)."""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from competencias.formativas.ges import TORNEOS_FORMATIVAS as TORNEOS  # noqa: F401
from pipelines.scrape_competencia import scrape_anios  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("years", type=int, nargs="+", help="Años a scrapear, ej. 2025 2026")
    args = p.parse_args()
    scrape_anios("formativas", args.years)
    print("Listo. Consolidar: python pipelines/consolidar_temporadas.py", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
