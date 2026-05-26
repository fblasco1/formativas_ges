# -*- coding: utf-8 -*-
"""Comparación entre ranking baseline (GES) y ranking institucional (tira)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd


def comparar_rankings(
    ranking_actual_clubes: pd.DataFrame,
    ranking_nuevo_clubes: pd.DataFrame,
) -> pd.DataFrame:
    """
    DataFrame con posiciones y puntos de ambos modelos y deltas.

    Espera columnas: Posicion, Club, Puntos en cada entrada.
    """
    a = ranking_actual_clubes.rename(
        columns={
            "Posicion": "Posicion_Actual",
            "Puntos": "Puntos_Actual",
        }
    )
    n = ranking_nuevo_clubes.rename(
        columns={
            "Posicion": "Posicion_Nuevo",
            "Puntos": "Puntos_Nuevo",
        }
    )
    cmp = pd.merge(
        a[["Club", "Posicion_Actual", "Puntos_Actual"]],
        n[["Club", "Posicion_Nuevo", "Puntos_Nuevo"]],
        on="Club",
        how="outer",
    )
    max_pos = max(
        cmp["Posicion_Actual"].max(skipna=True) or 0,
        cmp["Posicion_Nuevo"].max(skipna=True) or 0,
        len(cmp),
    )
    fill_pos = int(max_pos) + 1

    cmp["Posicion_Actual"] = cmp["Posicion_Actual"].fillna(fill_pos).astype(int)
    cmp["Posicion_Nuevo"] = cmp["Posicion_Nuevo"].fillna(fill_pos).astype(int)
    cmp["Puntos_Actual"] = cmp["Puntos_Actual"].fillna(0).astype(int)
    cmp["Puntos_Nuevo"] = cmp["Puntos_Nuevo"].fillna(0).astype(int)

    cmp["Delta_Posicion"] = cmp["Posicion_Actual"] - cmp["Posicion_Nuevo"]
    cmp["Delta_Puntos"] = cmp["Puntos_Nuevo"] - cmp["Puntos_Actual"]

    cmp = cmp.sort_values("Posicion_Nuevo").reset_index(drop=True)
    return cmp[
        [
            "Club",
            "Posicion_Actual",
            "Posicion_Nuevo",
            "Delta_Posicion",
            "Puntos_Actual",
            "Puntos_Nuevo",
            "Delta_Puntos",
        ]
    ]


def exportar_comparativa(
    comparativa: pd.DataFrame,
    path: Path,
    *,
    sep: str = ";",
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    comparativa.to_csv(path, index=False, encoding="utf-8-sig", sep=sep)
    return path
