# -*- coding: utf-8 -*-
"""
Entry point: scraping FeBAMBA Formativas desde gesdeportiva.json → Data/raw/*.csv.

Por defecto el flujo es **secuencial**. Con ``--workers N`` (N > 1) los torneos se
agrupan por **temporada** (año inferido del nombre) y, **dentro de cada temporada**,
se ejecutan hasta N scrapes en paralelo (hilos). Así se evita mezclar años distintos
y se acota la concurrencia global. Subir N aumenta carga sobre GES: usar con cuidado.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd

from scraper.scraper import FebambaScraper
from utils.logger import get_logger
from utils.torneos_febamba import es_torneo_formativas_febamba, inferir_anio

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GES_JSON = PROJECT_ROOT / "gesdeportiva.json"
RAW_DIR = PROJECT_ROOT / "Data" / "raw"
BASE_URL_DEFAULT = "https://competicionescabb.gesdeportiva.es"


def _sanitized_slug(text: str, max_len: int = 36) -> str:
    s = re.sub(r"[^\w\-]+", "_", text.strip().upper())
    s = re.sub(r"_+", "_", s).strip("_")
    return (s[:max_len] if len(s) > max_len else s) or "TORNEO"


def _temporada_torneo(torneo: dict[str, Any]) -> int:
    """Año lógico para agrupar (misma lógica que el scraper: nombre → fallback Anio)."""
    y = inferir_anio(str(torneo.get("torneo") or ""))
    if y is None:
        raw = torneo.get("Anio")
        y = int(raw) if raw is not None else 0
    return y


def _agrupar_por_temporada(torneos: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    por_anio: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for t in torneos:
        por_anio[_temporada_torneo(t)].append(t)
    return dict(por_anio)


def _scrape_torneo_un_archivo(
    torneo: dict[str, Any], base: str, raw_dir: Path
) -> None:
    """Un torneo → un CSV; un ``FebambaScraper`` por llamada (apto para hilos)."""
    scraper = FebambaScraper(base_url=base)
    partidos = scraper.scrap_torneo(torneo)
    if not partidos:
        logger.warning("Sin partidos para competencia id=%s", torneo.get("id"))
        return
    year = partidos[0].get("anio") or inferir_anio(str(torneo.get("torneo") or ""))
    comp_id = torneo.get("id", "x")
    slug = _sanitized_slug(str(torneo.get("torneo", "")))
    out = raw_dir / f"formativas_{comp_id}_{year}_{slug}.csv"
    pd.DataFrame(partidos).to_csv(out, index=False, encoding="utf-8-sig")
    logger.info("Guardado %s (%s partidos)", out.name, len(partidos))


def run(
    torneos: list[dict[str, Any]] | None = None,
    *,
    workers: int = 1,
    competencia_ids: list[int] | None = None,
) -> None:
    """
    Si ``torneos`` es None, carga y filtra desde ``gesdeportiva.json``.

    ``competencia_ids``: si se pasa (p. ej. ``[1623]``), solo esos id de competencia.

    ``workers``: 1 = un torneo tras otro (dentro de cada temporada ordenado).
    ``workers`` > 1 = hasta ese many hilos en paralelo **solo entre torneos de la misma
    temporada**; las temporadas se procesan en orden cronológico.
    """
    if torneos is None:
        if not GES_JSON.is_file():
            logger.error("No se encontró gesdeportiva.json en %s", GES_JSON)
            return
        with open(GES_JSON, encoding="utf-8") as f:
            data = json.load(f)
        competencias = data.get("competencias") or []
        torneos = [t for t in competencias if es_torneo_formativas_febamba(t)]

    if competencia_ids:
        want = {int(x) for x in competencia_ids}
        torneos = [t for t in torneos if int(t.get("id", -1)) in want]
        if not torneos:
            logger.warning(
                "Ningún torneo formativas coincide con --competencia %s",
                competencia_ids,
            )
            return

    logger.info("Torneos a scrapear: %s (workers=%s)", len(torneos), workers)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    base = BASE_URL_DEFAULT.rstrip("/")
    w = max(1, workers)

    por_temporada = _agrupar_por_temporada(torneos)
    for temporada in sorted(por_temporada.keys()):
        lote = por_temporada[temporada]
        etiqueta = temporada if temporada else "sin_año"
        logger.info("Temporada %s: %s torneo(s)", etiqueta, len(lote))

        if w == 1:
            for torneo in lote:
                try:
                    _scrape_torneo_un_archivo(torneo, base, RAW_DIR)
                except Exception:
                    logger.exception(
                        "Fallo scrapeando id=%s (temporada %s)",
                        torneo.get("id"),
                        etiqueta,
                    )
            continue

        with ThreadPoolExecutor(max_workers=w) as pool:
            futuros = {
                pool.submit(_scrape_torneo_un_archivo, t, base, RAW_DIR): t for t in lote
            }
            for futuro in as_completed(futuros):
                torneo = futuros[futuro]
                try:
                    futuro.result()
                except Exception:
                    logger.exception(
                        "Fallo scrapeando id=%s (temporada %s)",
                        torneo.get("id"),
                        etiqueta,
                    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape FeBAMBA formativas → Data/raw/ (paralelo opcional por temporada)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        metavar="N",
        help="Hilos concurrentes por temporada (1 = secuencial; p. ej. 3 acelera sin mezclar años)",
    )
    parser.add_argument(
        "--competencia",
        type=int,
        nargs="*",
        default=None,
        metavar="ID",
        help=(
            "Solo scrapear estos id(s) de competencia GES (p. ej. 1623 FORMATIVAS 2025). "
            "Sin este flag se scrapean todos los torneos formativas FeBAMBA del JSON."
        ),
    )
    args = parser.parse_args()
    run(workers=args.workers, competencia_ids=args.competencia)


if __name__ == "__main__":
    main()
