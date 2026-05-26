# -*- coding: utf-8 -*-
"""Scrapea una o más temporadas GES (solo las indicadas)."""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.main import FebambaScraper

TORNEOS = {
    2023: {
        "id": 682,
        "url": "https://competicionescabb.gesdeportiva.es/competicion.aspx?competencia=682",
        "torneo": "FORMATIVAS 2023",
    },
    2024: {
        "id": 1178,
        "url": "https://competicionescabb.gesdeportiva.es/competicion.aspx?competencia=1178",
        "torneo": "FORMATIVAS 2024",
    },
    2025: {
        "id": 1623,
        "url": "https://competicionescabb.gesdeportiva.es/competicion.aspx?competencia=1623",
        "torneo": "FORMATIVAS 2025",
    },
    2026: {
        "id": 2015,
        "url": "https://competicionescabb.gesdeportiva.es/competicion.aspx?competencia=2015",
        "torneo": "FORMATIVAS 2026",
    },
}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("years", type=int, nargs="+", help="Años a scrapear, ej. 2025 2026")
    args = p.parse_args()

    scraper = FebambaScraper(base_url="https://competicionescabb.gesdeportiva.es/")
    os.makedirs("Data", exist_ok=True)

    for year in args.years:
        if year not in TORNEOS:
            print(f"[error] Año {year} no configurado en TORNEOS")
            continue
        t = TORNEOS[year]
        info = {"id": t["id"], "url": t["url"], "Anio": year, "torneo": t["torneo"]}
        print(f"=== Scrapeando {t['torneo']} (id={t['id']}) ===", flush=True)
        try:
            partidos = scraper.scrap_torneo(info)
            if partidos:
                df = pd.DataFrame(partidos)
                out = os.path.join("Data", f"partidos_{year}.csv")
                df.to_csv(out, index=False, encoding="utf-8-sig", sep=";")
                print(f"OK -> {out} ({len(df)} partidos)", flush=True)
            else:
                print(f"Sin partidos para {year}", flush=True)
        except Exception as e:
            print(f"Error {year}: {e}", flush=True)
            raise
    print("Listo. Consolidar: python pipelines/consolidar_temporadas.py", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
