# -*- coding: utf-8 -*-
"""
Scrape GES parametrizado por competencia.

  python pipelines/scrape_competencia.py formativas 2026
  python pipelines/scrape_competencia.py formativas 2023 2024 2025 2026
  python pipelines/scrape_competencia.py --competencia liga_federal 2026
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from competencias.paths import partidos_anio_write_path  # noqa: E402
from competencias.registry import get_competencia, list_competencias  # noqa: E402
from scraper.main import FebambaScraper  # noqa: E402

GES_BASE = "https://competicionescabb.gesdeportiva.es/"


def scrape_anios(competencia: str, years: list[int], *, verbose: bool = True) -> dict[int, int]:
    cfg = get_competencia(competencia)
    if not cfg.torneos:
        raise RuntimeError(
            f"Competencia {cfg.nombre!r} ({cfg.estado}) sin torneos GES configurados. "
            f"Agregá IDs en competencias/{cfg.slug}/ges.py (rama estadisticas para otras ligas)."
        )

    scraper = FebambaScraper(base_url=GES_BASE)
    resultados: dict[int, int] = {}

    for anio in sorted(set(years)):
        if anio not in cfg.torneos:
            if verbose:
                print(f"[omitido] {anio}: no configurado en {competencia}")
            continue

        info = cfg.torneo(anio)
        if verbose:
            print(f"=== {cfg.nombre} | {info['torneo']} (id={info['id']}) ===", flush=True)

        partidos = scraper.scrap_torneo(info)
        if not partidos:
            if verbose:
                print(f"Sin partidos para {anio}", flush=True)
            resultados[anio] = 0
            continue

        out = partidos_anio_write_path(competencia, anio)
        out.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(partidos).to_csv(out, index=False, encoding="utf-8-sig", sep=";")
        resultados[anio] = len(partidos)
        if verbose:
            print(f"OK -> {out} ({len(partidos)} partidos)", flush=True)

    return resultados


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Scrape GES por competencia.")
    p.add_argument(
        "competencia",
        nargs="?",
        default="formativas",
        help="Slug: formativas, liga_federal, liga_argentina, …",
    )
    p.add_argument("years", type=int, nargs="*", help="Años a scrapear, ej. 2026")
    p.add_argument("--competencia", dest="comp_flag", help="Alternativa: --competencia formativas")
    p.add_argument("--list", action="store_true", help="Listar competencias registradas")
    args = p.parse_args(argv)

    if args.list:
        for c in list_competencias():
            anos = sorted(c.torneos.keys()) if c.torneos else []
            print(f"  {c.slug:16} [{c.estado:11}] {c.nombre}  años={anos}")
        return 0

    slug = (args.comp_flag or args.competencia or "formativas").strip().lower()
    years = args.years
    if not years:
        cfg = get_competencia(slug)
        if cfg.focus_years:
            years = list(cfg.focus_years[-1:])
        else:
            p.error("Indicá al menos un año o configurá focus_years en el registro.")

    scrape_anios(slug, years)
    if slug == "formativas":
        print("Siguiente: python pipelines/normalizar_equipos.py --consolidar", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
