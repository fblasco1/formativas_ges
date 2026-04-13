"""
Agregación de rankings por categoría con `AGE_GROUP_WEIGHT` (ranking “general”).
"""

from __future__ import annotations

import pandas as pd

from analisis.ranking_config import AGE_GROUP_WEIGHT


def weight_for_age_group(age_group: str) -> float:
    """
    Peso para una categoría canónica. Acepta valores compuestos (p. ej. 'CADETES MASCULINO').
    El orden de subcadenas evita que 'MINI' robe a 'PREMINI'.
    """
    u = str(age_group).upper().strip()
    if u in AGE_GROUP_WEIGHT:
        return float(AGE_GROUP_WEIGHT[u])
    substr_keys: tuple[tuple[str, str], ...] = (
        ("LIGA PROXIMO", "LIGA PROXIMO MASCULINO"),
        ("PREINFANTILES", "PREINFANTILES"),
        ("INFANTILES", "INFANTILES"),
        ("JUVENILES", "JUVENILES"),
        ("CADETES", "CADETES"),
        ("MOSQUITOS", "MOSQUITOS"),
        ("PREMINI", "PREMINI"),
        ("PRE MINI", "PREMINI"),
        ("MINI", "MINI"),
    )
    for needle, cfg in substr_keys:
        if needle in u:
            return float(AGE_GROUP_WEIGHT.get(cfg, AGE_GROUP_WEIGHT["DEFAULT"]))
    return float(AGE_GROUP_WEIGHT["DEFAULT"])


def merge_weighted_rankings(rankings: dict[str, pd.DataFrame], weights: dict[str, float] | None = None) -> pd.DataFrame:
    """
    Combina tablas `get_ranking()` con `suma_ponderada = Σ w_k · rating_k` por club.

    No suma `pj`/`pg` entre categorías (evita doble conteo); solo el score combinado.
    """
    scores: dict[str, float] = {}
    for key, df in rankings.items():
        if df is None or df.empty:
            continue
        w = weights[key] if weights is not None else weight_for_age_group(key)
        for _, row in df.iterrows():
            club = str(row["club"])
            r = float(row["rating"])
            scores[club] = scores.get(club, 0.0) + w * r

    rows = [{"club": c, "rating": s} for c, s in sorted(scores.items(), key=lambda x: (-x[1], x[0]))]
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out.insert(0, "pos", range(1, len(out) + 1))
    return out
