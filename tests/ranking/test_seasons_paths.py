# -*- coding: utf-8 -*-
"""Tests del motor de ranking portado a apps/ranking."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[2] / "apps" / "ranking"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from analisis.Ranking.seasons import (  # noqa: E402
    FOCUS_YEARS,
    PARTIDOS_CONSOLIDADO,
    resolve_partidos_consolidado,
)


def test_focus_years_ventana_actual():
    assert FOCUS_YEARS == (2023, 2024, 2025, 2026)


def test_partidos_consolidado_existe():
    path = resolve_partidos_consolidado()
    assert path.is_file(), f"Falta CSV consolidado: {PARTIDOS_CONSOLIDADO}"
    assert path.name == "23-26.csv"


def test_mapeo_equipos_carga():
    from mapeos.loader import cargar_mapeo_equipos

    mapeo = cargar_mapeo_equipos()
    assert isinstance(mapeo, dict)
    assert len(mapeo) > 100
