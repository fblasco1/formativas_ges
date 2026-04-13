from __future__ import annotations

import pandas as pd

from analisis.ranking.febamba_ranking import FeBAMBARanking
from analisis.ranking.stage_weights import stage_multiplier


def test_stage_multiplier_product() -> None:
    s = stage_multiplier("FASE REGULAR", "1RA FASE", "1", 2024)
    assert s > 0
    s2 = stage_multiplier("PLAYOFF", "FINAL", "INTERCONFERENCIA", 2024)
    assert s2 > s


def test_forfeit_skipped() -> None:
    eng = FeBAMBARanking()
    g = eng.process_match(
        {
            "local": "A",
            "visitante": "B",
            "ptsL": 10,
            "ptsV": 0,
            "is_forfeit": True,
            "fase": "X",
            "ronda": "Y",
            "nivel": "1",
            "anio": 2024,
        }
    )
    assert g == (0.0, 0.0)
    assert eng.get_ranking().empty


def test_tl_before_update_stronger_loser_boosts_winner() -> None:
    """El ganador recibe más GRP si el perdedor tenía rating más alto (O mayor)."""
    eng = FeBAMBARanking()
    eng.initialize_club("WEAK")
    eng.initialize_club("STRONG")
    eng.ratings["STRONG"] = 1300.0
    eng.ratings["WEAK"] = 800.0

    m1 = {
        "local": "WEAK",
        "visitante": "STRONG",
        "ptsL": 50,
        "ptsV": 40,
        "is_forfeit": False,
        "fase": "FR",
        "ronda": "R1",
        "nivel": "1",
        "anio": 2024,
    }
    gw_weak_beats_strong = eng.process_match(m1)[0]

    eng2 = FeBAMBARanking()
    eng2.initialize_club("WEAK")
    eng2.initialize_club("STRONG")
    eng2.ratings["STRONG"] = 1300.0
    eng2.ratings["WEAK"] = 800.0
    m2 = dict(m1)
    m2["ptsL"], m2["ptsV"] = 40, 50
    gw_strong_beats_weak = eng2.process_match(m2)[1]

    assert gw_weak_beats_strong > gw_strong_beats_weak


def test_apply_seasonal_discount() -> None:
    from analisis.ranking_config import DISCOUNT_FACTOR

    eng = FeBAMBARanking()
    eng.initialize_club("A")
    eng.ratings["A"] = 1000.0
    eng.apply_seasonal_discount()
    assert abs(eng.ratings["A"] - 1000.0 * DISCOUNT_FACTOR) < 1e-6


def test_chronological_sort_by_anio() -> None:
    from analisis.ranking.data_loader import sort_matches_chronological

    df = pd.DataFrame(
        [
            {"anio": 2024, "k": 1},
            {"anio": 2023, "k": 2},
        ]
    )
    s = sort_matches_chronological(df)
    assert int(s.iloc[0]["anio"]) == 2023
    assert int(s.iloc[1]["anio"]) == 2024


def test_age_group_filter() -> None:
    eng = FeBAMBARanking(age_group_filter="CADETES")
    eng.process_match(
        {
            "local": "A",
            "visitante": "B",
            "ptsL": 10,
            "ptsV": 0,
            "age_group": "CADETES MASCULINO",
            "is_forfeit": False,
            "fase": "X",
            "ronda": "Y",
            "nivel": "1",
            "anio": 2024,
        }
    )
    assert "A" in eng.ratings
    eng2 = FeBAMBARanking(age_group_filter="CADETES")
    eng2.process_match(
        {
            "local": "C",
            "visitante": "D",
            "ptsL": 10,
            "ptsV": 0,
            "age_group": "INFANTILES MASCULINO",
            "is_forfeit": False,
            "fase": "X",
            "ronda": "Y",
            "nivel": "1",
            "anio": 2024,
        }
    )
    assert "C" not in eng2.ratings
