"""Módulo de ingesta: scraping GES y API interna."""

from ingest.errors import NetworkError, ParseError, ScraperError
from ingest.extractors import Extractor, ExtractorFactory, GesDeportivaExtractor
from ingest.extract_boxscore import get_boxscore, parse_table, clean_shot_value
from ingest.extraer_info_partidos import get_ids_categorias, get_info_partidos
from ingest.extract_fixture_argentina_basketball import (
    fetch_cargar_fixture_html,
    fetch_partido_en_vivo_html,
    extraer_hora_inicio_fin_desde_en_vivo_html,
    get_fixture_partidos_argentina_basketball,
    parse_tabla_calendarios,
)

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
    "fetch_cargar_fixture_html",
    "fetch_partido_en_vivo_html",
    "extraer_hora_inicio_fin_desde_en_vivo_html",
    "get_fixture_partidos_argentina_basketball",
    "parse_tabla_calendarios",
    "parse_table",
    "clean_shot_value",
]
