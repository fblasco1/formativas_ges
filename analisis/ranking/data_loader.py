"""
Carga de partidos y orden cronológico para el motor de ranking.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from analisis.ranking.febamba_ranking import FeBAMBARanking


def load_matches_from_parquet(path: str | Path) -> pd.DataFrame:
    """Lee `matches_clean.parquet` (o equivalente)."""
    p = Path(path)
    return pd.read_parquet(p)


def load_matches_from_csv(path: str | Path, sep: str = ";") -> pd.DataFrame:
    return pd.read_csv(path, sep=sep, encoding="utf-8", low_memory=False)


def _parse_fecha(s: Any) -> pd.Timestamp | pd.NaT:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return pd.NaT
    t = str(s).strip()
    if not t:
        return pd.NaT
    return pd.to_datetime(t, dayfirst=True, errors="coerce")


def sort_matches_chronological(df: pd.DataFrame) -> pd.DataFrame:
    """
    Orden: `anio`, luego `fecha` (dd/mm/yyyy) si existe; desempate estable por orden de fila original.
    """
    d = df.copy().reset_index(drop=True)
    if "anio" not in d.columns:
        return d
    d["_anio"] = pd.to_numeric(d["anio"], errors="coerce").fillna(0).astype(int)
    d["_ord"] = range(len(d))
    if "fecha" in d.columns:
        d["_fecha"] = d["fecha"].map(_parse_fecha)
        d = d.sort_values(by=["_anio", "_fecha", "_ord"], na_position="last", kind="mergesort")
    else:
        d = d.sort_values(by=["_anio", "_ord"], kind="mergesort")
    return d.drop(columns=[c for c in ("_anio", "_fecha", "_ord") if c in d.columns]).reset_index(
        drop=True
    )


def row_to_match_dict(row: pd.Series) -> dict[str, Any]:
    """Convierte una fila del dataset normalizado a dict para `FeBAMBARanking.process_match`."""
    return row.where(pd.notna(row), None).to_dict()


def run_ranking_on_dataframe(
    df: pd.DataFrame,
    *,
    age_group_filter: str | None = None,
    genero_filter: str | None = None,
    store_history: bool = False,
) -> FeBAMBARanking:
    """
    Procesa todos los partidos en orden y devuelve una instancia `FeBAMBARanking` lista para `get_ranking()`.
    """
    from analisis.ranking.febamba_ranking import FeBAMBARanking as _FeBAMBARanking

    ordered = sort_matches_chronological(df)
    eng = _FeBAMBARanking(
        age_group_filter=age_group_filter,
        genero_filter=genero_filter,
        store_history=store_history,
    )
    for _, row in ordered.iterrows():
        eng.process_match(row_to_match_dict(row))
    return eng
