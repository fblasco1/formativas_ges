# -*- coding: utf-8 -*-
"""Caché incremental: histórico 2023-2025 congelado + delta 2026."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from analisis.Ranking.seasons import PROCESADA_DIR

CACHE_DIR = PROCESADA_DIR / "renivelacion"
PARTIDOS_HISTORICO = CACHE_DIR / "partidos_enriquecidos_2023_2025.parquet"
ACUMULADO_HISTORICO = CACHE_DIR / "acumulado_tiras_2023_2025.csv"
RANKING_ORP_2025 = CACHE_DIR / "ranking_orp_tiras_2025.csv"
META_JSON = CACHE_DIR / "cache_meta.json"


def _guardar_df(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".parquet":
        try:
            df.to_parquet(path, index=False)
            return
        except (ImportError, ValueError):
            path = path.with_suffix(".csv")
    df.to_csv(path, index=False, encoding="utf-8-sig", sep=";")


def _leer_df(path: Path) -> pd.DataFrame:
    if not path.is_file():
        alt = path.with_suffix(".csv")
        if alt.is_file():
            path = alt
        else:
            raise FileNotFoundError(path)
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, sep=";")


def guardar_cache_historico(
    partidos: pd.DataFrame,
    acumulado: pd.DataFrame,
    ranking_orp_2025: pd.DataFrame,
    meta: dict[str, Any],
) -> None:
    _guardar_df(partidos, PARTIDOS_HISTORICO)
    _guardar_df(acumulado, ACUMULADO_HISTORICO)
    ranking_orp_2025.to_csv(
        RANKING_ORP_2025, index=False, encoding="utf-8-sig", sep=";"
    )
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(META_JSON, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


def cargar_cache_historico() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    partidos = _leer_df(PARTIDOS_HISTORICO)
    acumulado = _leer_df(ACUMULADO_HISTORICO)
    ranking = pd.read_csv(RANKING_ORP_2025, sep=";")
    return partidos, acumulado, ranking


def cache_historico_existe() -> bool:
    return ACUMULADO_HISTORICO.is_file() or ACUMULADO_HISTORICO.with_suffix(
        ".parquet"
    ).is_file()
