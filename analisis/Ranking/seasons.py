# -*- coding: utf-8 -*-
"""Temporadas en foco y rutas de datos del Power Ranking."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence, Tuple

# Ventana de análisis actual
FOCUS_YEARS: Tuple[int, ...] = (2023, 2024, 2025, 2026)
TEMPORADA_ACTIVA: int = FOCUS_YEARS[-1]
ACCUMULADO_DESDE: int = FOCUS_YEARS[0]
ACCUMULADO_HASTA: int = FOCUS_YEARS[-1]

# Peso relativo por temporada (la más reciente = 1.0)
YEAR_WEIGHTS: dict[int, float] = {
    2023: 0.25,
    2024: 0.50,
    2025: 0.75,
    2026: 1.00,
}

DATA_DIR = Path("Data")
PROCESADA_DIR = DATA_DIR / "procesada"
PARTIDOS_CONSOLIDADO = PROCESADA_DIR / "23-26.csv"
PARTIDOS_LEGACY = PROCESADA_DIR / "19-24.csv"


def ranking_acumulado_filename(through_year: int | None = None) -> str:
    """Nombre del CSV acumulado, p. ej. ``Ranking2023-2026.csv``."""
    end = through_year if through_year is not None else ACCUMULADO_HASTA
    return f"Ranking{ACCUMULADO_DESDE}-{end}.csv"


def ranking_acumulado_path(
    output_dir: Path | str = PROCESADA_DIR,
    through_year: int | None = None,
) -> Path:
    return Path(output_dir) / ranking_acumulado_filename(through_year)


def ranking_acumulado_label(through_year: int | None = None) -> str:
    end = through_year if through_year is not None else ACCUMULADO_HASTA
    return f"Power Ranking {ACCUMULADO_DESDE}-{end}"


def ranking_anual_path(year: int, output_dir: Path | str = PROCESADA_DIR) -> Path:
    return Path(output_dir) / f"Ranking{year}.csv"


def partidos_por_anio_path(year: int) -> Path:
    return DATA_DIR / f"partidos_{year}.csv"


def resolve_partidos_consolidado() -> Path:
    """CSV consolidado preferido; si no existe, el histórico 19-24."""
    if PARTIDOS_CONSOLIDADO.is_file():
        return PARTIDOS_CONSOLIDADO
    if PARTIDOS_LEGACY.is_file():
        return PARTIDOS_LEGACY
    return PARTIDOS_CONSOLIDADO


def filtrar_anios(df, years: Iterable[int] = FOCUS_YEARS):
    """Filtra partidos a las temporadas indicadas (columna ``anio``)."""
    import pandas as pd

    if "anio" not in df.columns:
        return df
    allowed = {int(y) for y in years}
    anio_num = pd.to_numeric(df["anio"], errors="coerce")
    return df[anio_num.isin(allowed)].copy()


def peso_anio_configurado(anio) -> float:
    return YEAR_WEIGHTS.get(int(anio), 1.0)


def anos_con_patron_ronda_clasico(anio) -> bool:
    """2023 y anteriores: 2ª fase peso 2; 2024+ invierte con 3ª fase."""
    return int(anio) <= 2023
