# -*- coding: utf-8 -*-
"""
Compatibilidad con scripts antiguos.

Preferir:
  python -m analisis.Ranking
  from analisis.Ranking.core import process_all_years, ...
"""

from analisis.Ranking.core import (  # noqa: F401
    asignar_basis_points,
    calculate_orp_vectorized,
    crear_ranking_base,
    get_team_positions,
    peso_por_anio,
    peso_por_fase,
    peso_por_nivel,
    peso_por_ronda,
    process_all_years,
    process_year,
)

__all__ = [
    "asignar_basis_points",
    "calculate_orp_vectorized",
    "crear_ranking_base",
    "get_team_positions",
    "peso_por_anio",
    "peso_por_fase",
    "peso_por_nivel",
    "peso_por_ronda",
    "process_all_years",
    "process_year",
]
