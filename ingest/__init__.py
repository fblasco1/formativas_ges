"""Módulo de ingesta: scraping GES y API interna."""

from ingest.errors import NetworkError, ParseError, ScraperError
from ingest.extractors import Extractor, ExtractorFactory, GesDeportivaExtractor
from ingest.extract_boxscore import get_boxscore, parse_table, clean_shot_value
from ingest.extraer_info_partidos import get_ids_categorias, get_info_partidos

__all__ = [
    "Extractor",
    "ExtractorFactory",
    "GesDeportivaExtractor",
    "NetworkError",
    "ParseError",
    "ScraperError",
    "get_boxscore",
    "get_ids_categorias",
    "get_info_partidos",
    "parse_table",
    "clean_shot_value",
]
