# -*- coding: utf-8 -*-
"""Tests del motor comparativo institucional."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analisis.ranking_comparativo.categorias_u import banda_u_desde_categoria  # noqa: E402
from analisis.ranking_comparativo.clubes import club_desde_equipo  # noqa: E402
from analisis.ranking_comparativo.comparativa import comparar_rankings  # noqa: E402
from analisis.ranking_comparativo.institucional import (  # noqa: E402
    aplicar_penalizacion_tira,
)
from analisis.ranking_comparativo.institucional import factor_tira_club as ft  # noqa: E402


class TestCategoriasU:
    def test_mapeo_premini_mini(self):
        assert banda_u_desde_categoria("PREMINI") == "U9"
        assert banda_u_desde_categoria("MINI") == "U11"
        assert banda_u_desde_categoria("JUVENILES MASCULINO") == "U19"


class TestClubes:
    def test_quita_sufijo_a(self):
        assert club_desde_equipo("PEDRO ECHAGUE A") == "PEDRO ECHAGUE"


class TestFactorTira:
    def test_penalizacion_completa(self):
        assert ft("X", set()) == 0.0

    def test_sin_penalizacion(self):
        assert ft("X", {"U9", "U11", "U13", "U15", "U17", "U19"}) == 1.0

    def test_falta_u9(self):
        assert ft("X", {"U11", "U13", "U15", "U17", "U19"}) == 0.8


class TestComparativa:
    def test_delta_posicion(self):
        actual = pd.DataFrame(
            {"Posicion": [1, 2], "Club": ["A", "B"], "Puntos": [100, 50]}
        )
        nuevo = pd.DataFrame(
            {"Posicion": [2, 1], "Club": ["A", "B"], "Puntos": [80, 90]}
        )
        cmp = comparar_rankings(actual, nuevo)
        assert cmp.loc[cmp["Club"] == "A", "Delta_Posicion"].iloc[0] == -1
        assert cmp.loc[cmp["Club"] == "B", "Delta_Posicion"].iloc[0] == 1


class TestPenalizacionTira:
    def test_aplica_factor(self):
        df = pd.DataFrame(
            {
                "fecha_norm": ["1/1/2024"],
                "club_local": ["CLUB A"],
                "club_visitante": ["CLUB B"],
                "local": ["CLUB A"],
                "visitante": ["CLUB B"],
                "categoria": ["JUVENILES"],
                "banda_u": ["U19"],
                "LocalSuma": [100.0],
                "VisitaSuma": [50.0],
            }
        )
        out = aplicar_penalizacion_tira(df)
        assert "P_tira_local" in out.columns
        assert out["Puntos_local_inst"].iloc[0] <= out["LocalSuma"].iloc[0]
