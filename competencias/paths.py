# -*- coding: utf-8 -*-
"""Resolución de rutas de datos por competencia (con fallback legacy formativas)."""

from __future__ import annotations

from pathlib import Path

from competencias.registry import DATA_ROOT, get_competencia

# Rutas legacy Ranking_V2 (antes de Data/formativas/)
_LEGACY_PARTIDOS = DATA_ROOT / "partidos_{year}.csv"
_LEGACY_CONSOLIDADO = DATA_ROOT / "procesada" / "23-26.csv"
_LEGACY_RENIVELACION = DATA_ROOT / "procesada" / "renivelacion"


def partidos_anio_path(competencia: str, anio: int) -> Path:
    """
    Ruta preferida del CSV anual. Para formativas, si no existe en
    ``Data/formativas/``, usa ``Data/partidos_{año}.csv``.
    """
    cfg = get_competencia(competencia)
    preferida = cfg.partidos_path(anio)
    if preferida.is_file():
        return preferida
    if competencia == "formativas":
        legacy = DATA_ROOT / f"partidos_{anio}.csv"
        if legacy.is_file():
            return legacy
    return preferida


def partidos_anio_write_path(competencia: str, anio: int) -> Path:
    """Destino al scrapear (siempre namespace de la competencia)."""
    return get_competencia(competencia).partidos_path(anio)


def consolidado_path(competencia: str, nombre: str = "23-26.csv") -> Path:
    preferida = get_competencia(competencia).procesada_dir / nombre
    if preferida.is_file():
        return preferida
    if competencia == "formativas" and nombre == "23-26.csv" and _LEGACY_CONSOLIDADO.is_file():
        return _LEGACY_CONSOLIDADO
    return preferida


def consolidado_write_path(competencia: str, nombre: str = "23-26.csv") -> Path:
    return get_competencia(competencia).procesada_dir / nombre


def renivelacion_dir(competencia: str = "formativas") -> Path:
    """Caché renivelación (sigue en legacy hasta migración explícita)."""
    if competencia == "formativas":
        nuevo = get_competencia("formativas").procesada_dir / "renivelacion"
        if nuevo.is_dir():
            return nuevo
        return _LEGACY_RENIVELACION
    return get_competencia(competencia).procesada_dir / "renivelacion"
