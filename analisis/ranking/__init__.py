"""
Motor de ranking FeBAMBA (adaptación FIBA): `FeBAMBARanking`, factor S y carga de partidos.
"""

from analisis.ranking.data_loader import (
    load_matches_from_csv,
    load_matches_from_parquet,
    run_ranking_on_dataframe,
    sort_matches_chronological,
)
from analisis.ranking.febamba_ranking import FeBAMBARanking
from analisis.ranking.ranking_general import merge_weighted_rankings, weight_for_age_group
from analisis.ranking.stage_weights import stage_multiplier

__all__ = [
    "FeBAMBARanking",
    "load_matches_from_csv",
    "load_matches_from_parquet",
    "merge_weighted_rankings",
    "run_ranking_on_dataframe",
    "sort_matches_chronological",
    "stage_multiplier",
    "weight_for_age_group",
]
