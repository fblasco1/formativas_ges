"""Módulo de análisis: normalización, categoría jugador y evolución YoY."""

from analysis.db import (
    build_url,
    get_engine,
    get_session,
    get_session_factory,
    load_config,
)
from analysis.categoria_jugador import (
    CATEGORIA_RANKS,
    RANGO_DESCONOCIDO,
    clasificar_categoria_mas_joven,
    extract_jugador_categorias,
    normalizar_categoria,
    rank_categoria,
    run_pipeline,
)

__all__ = [
    "build_url",
    "get_engine",
    "get_session",
    "get_session_factory",
    "load_config",
    "CATEGORIA_RANKS",
    "RANGO_DESCONOCIDO",
    "clasificar_categoria_mas_joven",
    "extract_jugador_categorias",
    "normalizar_categoria",
    "rank_categoria",
    "run_pipeline",
]
