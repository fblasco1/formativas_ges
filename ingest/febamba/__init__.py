# -*- coding: utf-8 -*-
"""Ingesta FeBAMBA: contexto de torneo, portal argentina.basketball (2026+), claves naturales."""

from ingest.febamba.argentina_pipeline import collect_partidos_temporada_2026
from ingest.febamba.dual_source_extractor import FebambaDualSourceExtractor
from ingest.febamba.fixture_contexto import merge_contexto_torneo, year_from_temporada
from ingest.febamba.season import historico_antes_portal_argentina, ingesta_usa_portal_argentina

__all__ = [
    "FebambaDualSourceExtractor",
    "collect_partidos_temporada_2026",
    "historico_antes_portal_argentina",
    "ingesta_usa_portal_argentina",
    "merge_contexto_torneo",
    "year_from_temporada",
]
