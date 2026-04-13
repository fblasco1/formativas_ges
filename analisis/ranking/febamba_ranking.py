"""
Motor FeBAMBA tipo FIBA: G = B×R×S (perdedor), GW = G×W×O×A×M (ganador), ratings acumulativos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from analisis.ranking_config import (
    A_AWAY_WIN,
    A_HOME_WIN,
    BASE_FACTOR,
    DISCOUNT_FACTOR,
    INITIAL_RATING,
    M_MARGIN_REF,
    M_MAX,
    M_MIN,
    O_COEFF,
    O_MAX,
    O_MIN,
    R_MARGIN_REF,
    R_MAX,
    R_MIN,
    WINNING_FACTOR,
)
from analisis.ranking.stage_weights import stage_multiplier


def _norm_club(x: Any) -> str:
    return str(x).strip().upper()


def _margin_factor(margin: int) -> float:
    if margin <= 0:
        return M_MIN
    t = min(float(margin) / M_MARGIN_REF, 1.0)
    return float(M_MIN + (M_MAX - M_MIN) * t)


def _result_factor(margin: int) -> float:
    if margin <= 0:
        return R_MIN
    t = min(float(margin) / R_MARGIN_REF, 1.0)
    return float(R_MIN + (R_MAX - R_MIN) * t)


def _opponent_factor(tl: float) -> float:
    """O: función del rating pre-partido del perdedor (TL)."""
    base = max(INITIAL_RATING, 1.0)
    raw = 1.0 + O_COEFF * (tl - INITIAL_RATING) / base
    return float(max(O_MIN, min(O_MAX, raw)))


@dataclass
class FeBAMBARanking:
    """
    Ratings acumulativos por club. `process_match` usa TL del perdedor **antes** de actualizar.
    """

    initial_rating: float = INITIAL_RATING
    age_group_filter: str | None = None
    genero_filter: str | None = None
    store_history: bool = False

    ratings: dict[str, float] = field(default_factory=dict)
    played: dict[str, int] = field(default_factory=dict)
    wins: dict[str, int] = field(default_factory=dict)
    losses: dict[str, int] = field(default_factory=dict)

    _last_anio: int | None = field(default=None, repr=False)
    history: list[dict[str, Any]] = field(default_factory=list)

    def initialize_club(self, club: str) -> None:
        c = _norm_club(club)
        if c not in self.ratings:
            self.ratings[c] = float(self.initial_rating)
            self.played.setdefault(c, 0)
            self.wins.setdefault(c, 0)
            self.losses.setdefault(c, 0)

    def apply_seasonal_discount(self) -> None:
        for c in self.ratings:
            self.ratings[c] *= DISCOUNT_FACTOR

    def _match_applies(self, match: dict[str, Any]) -> bool:
        if self.age_group_filter is not None:
            want = self.age_group_filter.upper().strip()
            ag = str(match.get("age_group") or match.get("categoria") or "").upper().strip()
            if want not in ag:
                return False
        if self.genero_filter is not None:
            g = str(match.get("genero") or "").upper().strip()
            if g != self.genero_filter.upper():
                return False
        return True

    def process_match(self, match: dict[str, Any]) -> tuple[float, float]:
        """
        Calcula GRP para local y visitante. Actualiza ratings y contadores.
        Empates y forfaits: (0, 0) sin actualizar.
        """
        if match.get("is_forfeit"):
            return (0.0, 0.0)
        if not self._match_applies(match):
            return (0.0, 0.0)

        local = _norm_club(match["local"])
        visit = _norm_club(match["visitante"])
        if local == visit:
            return (0.0, 0.0)

        try:
            pl = int(match["ptsL"])
            pv = int(match["ptsV"])
        except (TypeError, ValueError):
            return (0.0, 0.0)

        if pl == pv:
            return (0.0, 0.0)

        anio = match.get("anio")
        if anio is not None:
            try:
                yi = int(anio)
            except (TypeError, ValueError):
                yi = None
            if yi is not None:
                if self._last_anio is not None and yi != self._last_anio:
                    self.apply_seasonal_discount()
                self._last_anio = yi

        self.initialize_club(local)
        self.initialize_club(visit)

        r_local = float(self.ratings[local])
        r_visit = float(self.ratings[visit])

        s = stage_multiplier(
            match.get("fase", ""),
            match.get("ronda", ""),
            match.get("nivel", ""),
            self._last_anio,
        )

        if pl > pv:
            winner, loser = local, visit
            tl = r_visit
            margin = pl - pv
            a = A_HOME_WIN
        else:
            winner, loser = visit, local
            tl = r_local
            margin = pv - pl
            a = A_AWAY_WIN

        rfac = _result_factor(margin)
        g_loser = BASE_FACTOR * rfac * s
        o = _opponent_factor(tl)
        mfac = _margin_factor(margin)
        g_winner = g_loser * WINNING_FACTOR * o * a * mfac

        grp_local = g_winner if winner == local else g_loser
        grp_visit = g_winner if winner == visit else g_loser

        self.ratings[winner] = float(self.ratings[winner]) + g_winner
        self.ratings[loser] = float(self.ratings[loser]) + g_loser

        self.played[local] = self.played.get(local, 0) + 1
        self.played[visit] = self.played.get(visit, 0) + 1
        self.wins[winner] = self.wins.get(winner, 0) + 1
        self.losses[loser] = self.losses.get(loser, 0) + 1

        if self.store_history:
            self.history.append(
                {
                    "factor_etapa": s,
                    "fase": match.get("fase"),
                    "ronda": match.get("ronda"),
                    "nivel": match.get("nivel"),
                    "g_loser": g_loser,
                    "g_winner": g_winner,
                    "local": local,
                    "visitante": visit,
                }
            )

        return (grp_local, grp_visit)

    def get_ranking(self) -> pd.DataFrame:
        rows = []
        for club in sorted(self.ratings.keys()):
            pj = self.played.get(club, 0)
            pg = self.wins.get(club, 0)
            pp = self.losses.get(club, 0)
            rows.append(
                {
                    "club": club,
                    "rating": self.ratings[club],
                    "pj": pj,
                    "pg": pg,
                    "pp": pp,
                }
            )
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df = df.sort_values(by=["rating", "pg", "club"], ascending=[False, False, True]).reset_index(
            drop=True
        )
        df.insert(0, "pos", range(1, len(df) + 1))
        return df
