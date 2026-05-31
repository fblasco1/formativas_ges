# -*- coding: utf-8 -*-
"""Tests del motor de Power Ranking."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analisis.Ranking.core import (  # noqa: E402
    DEFAULT_YEARS,
    asignar_basis_points,
    crear_ranking_base,
    peso_por_anio,
    peso_por_fase,
    peso_por_nivel,
    peso_por_ronda,
    process_all_years,
    process_year,
)
from analisis.Ranking.seasons import (  # noqa: E402
    FOCUS_YEARS,
    ranking_acumulado_filename,
)

FIXTURE = ROOT / "tests" / "fixtures" / "ranking_sample.csv"


class TestSeasons:
    def test_focus_years_default(self):
        assert DEFAULT_YEARS == FOCUS_YEARS == (2023, 2024, 2025, 2026)

    def test_ranking_acumulado_filename(self):
        assert ranking_acumulado_filename(2026) == "Ranking2023-2026.csv"


def _row(pts_l: int, pts_v: int) -> pd.Series:
    return pd.Series({"ptsL": pts_l, "ptsV": pts_v, "local": "A", "visitante": "B"})


class TestBasisPoints:
    def test_empate_cero(self):
        assert asignar_basis_points(_row(0, 0)) == (0, 0)

    def test_forfeit_20_0(self):
        assert asignar_basis_points(_row(20, 0)) == (700, 0)
        assert asignar_basis_points(_row(0, 20)) == (0, 700)

    def test_victoria_ajustada(self):
        assert asignar_basis_points(_row(75, 70)) == (650, 350)
        assert asignar_basis_points(_row(70, 75)) == (350, 650)

    def test_victoria_media(self):
        assert asignar_basis_points(_row(85, 70)) == (700, 300)

    def test_victoria_abultada(self):
        assert asignar_basis_points(_row(95, 70)) == (750, 250)

    def test_marcador_invalido(self):
        assert asignar_basis_points(pd.Series({"ptsL": "x", "ptsV": 1})) == (0, 0)


class TestPesos:
    def test_peso_anio(self):
        assert peso_por_anio(2023) == 0.25
        assert peso_por_anio(2024) == 0.5
        assert peso_por_anio(2026) == 1.0
        assert peso_por_anio(2099) == 1

    def test_peso_fase(self):
        assert peso_por_fase("FASE REGULAR", "1") == 0.65
        assert peso_por_fase("PLAYOFF", "2") == 0.75
        assert peso_por_fase("PLAYOFF", "INTERCONFERENCIA A") == 1
        assert peso_por_fase("FINAL FOUR", "1") == 1

    def test_peso_ronda(self):
        assert peso_por_ronda("1RA FASE", 2024) == 1
        assert peso_por_ronda("2DA FASE", 2024) == 1
        assert peso_por_ronda("2DA FASE", 2023) == 2
        assert peso_por_ronda("2DA FASE", 2025) == 1
        assert peso_por_ronda("3RA FASE", 2025) == 2
        assert peso_por_ronda("FINAL", 2024) == 6

    def test_peso_nivel(self):
        assert peso_por_nivel("INTERCONFERENCIA A") == 2
        assert peso_por_nivel("INTERCONFERENCIA B") == 1.5
        assert peso_por_nivel("3") == 0.75


class TestProcessYear:
    @pytest.fixture
    def sample_data(self) -> pd.DataFrame:
        df = pd.read_csv(FIXTURE, sep=";")
        data, _ = crear_ranking_base(df)
        return data

    def test_un_anio_dos_equipos(self, sample_data: pd.DataFrame):
        base = pd.DataFrame({"Equipo": ["EQUIPO A", "EQUIPO B"], "Puntos": [0, 0]})
        df, ranking = process_year(sample_data, base, 2024, use_orp=False)
        assert len(df) == 2
        assert set(ranking["Equipo"]) == {"EQUIPO A", "EQUIPO B"}
        assert ranking["Puntos"].sum() > 0
        assert ranking.iloc[0]["Puntos"] >= ranking.iloc[1]["Puntos"]

    def test_process_all_years_sin_escribir(self, sample_data: pd.DataFrame, tmp_path: Path):
        base = pd.DataFrame({"Equipo": sample_data["local"].unique(), "Puntos": 0})
        rankings, total = process_all_years(
            sample_data,
            [2024],
            ranking_init=base,
            output_dir=None,
            verbose=False,
        )
        assert 2024 in rankings
        assert len(total) == 2
        assert not list(tmp_path.glob("Ranking2024.csv"))
