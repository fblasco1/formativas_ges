# -*- coding: utf-8 -*-
"""Algoritmo baseline GES (BP + ORP + multiplicadores)."""

from __future__ import annotations

from typing import Dict, Iterable, Optional, Tuple

import pandas as pd

from analisis.Ranking.core import (
    _aplicar_pesos_y_puntos,
    asignar_basis_points,
    calculate_orp_vectorized,
    preparar_ranking_tabla,
    process_year,
)
from analisis.ranking_comparativo.clubes import club_desde_equipo


def enriquecer_partidos_baseline(
    df: pd.DataFrame,
    prev_ranking: pd.DataFrame,
    *,
    use_orp: bool,
) -> pd.DataFrame:
    """Añade BP, ORP, pesos y LocalSuma/VisitaSuma por fila."""
    out = df.copy()
    bp = out.apply(asignar_basis_points, axis=1, result_type="expand")
    out["BP_LOCAL"], out["BP_VISITA"] = bp[0], bp[1]
    if use_orp:
        out = calculate_orp_vectorized(out, prev_ranking)
    else:
        out["ORP_LOCAL"] = 0.0
        out["ORP_VISITA"] = 0.0
    return _aplicar_pesos_y_puntos(out)


def ranking_equipos_desde_partidos(df: pd.DataFrame) -> pd.DataFrame:
    local = (
        df.groupby("local", as_index=False)["LocalSuma"]
        .sum()
        .rename(columns={"local": "Equipo", "LocalSuma": "Puntos"})
    )
    visita = (
        df.groupby("visitante", as_index=False)["VisitaSuma"]
        .sum()
        .rename(columns={"visitante": "Equipo", "VisitaSuma": "Puntos"})
    )
    ranking = (
        pd.concat([local, visita], ignore_index=True)
        .groupby("Equipo", as_index=False)["Puntos"]
        .sum()
    )
    return preparar_ranking_tabla(ranking)


def ranking_clubes_desde_equipos(ranking_equipos: pd.DataFrame) -> pd.DataFrame:
    """Agrega equipos A/B bajo el mismo club para comparar con el modelo institucional."""
    tmp = ranking_equipos.copy()
    tmp["Club"] = tmp["Equipo"].map(club_desde_equipo)
    agg = tmp.groupby("Club", as_index=False)["Puntos"].sum()
    agg = agg.sort_values("Puntos", ascending=False).reset_index(drop=True)
    agg["Posicion"] = range(1, len(agg) + 1)
    return agg[["Posicion", "Club", "Puntos"]]


def procesar_baseline_anual(
    data: pd.DataFrame,
    years: Iterable[int],
    ranking_prev_equipos: Optional[pd.DataFrame] = None,
) -> Tuple[Dict[int, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    """
    Procesa años en orden.

    Returns:
        partidos_por_anio, ranking_acumulado_equipos, ranking_acumulado_clubes
    """
    years_list = list(years)
    partidos: Dict[int, pd.DataFrame] = {}
    ranking_total = ranking_prev_equipos

    for i, year in enumerate(years_list):
        use_orp = i > 0 and ranking_total is not None and not ranking_total.empty
        prev = (
            ranking_total
            if use_orp
            else pd.DataFrame(columns=["Equipo", "Puntos", "Posicion"])
        )
        df_year = data[data["anio"] == year].copy()
        if df_year.empty:
            continue
        df_proc = enriquecer_partidos_baseline(df_year, prev, use_orp=use_orp)
        partidos[year] = df_proc
        ranking_anual = ranking_equipos_desde_partidos(df_proc)
        if ranking_total is None or ranking_total.empty:
            ranking_total = ranking_anual.copy()
        else:
            ranking_total = (
                pd.concat([ranking_total, ranking_anual], ignore_index=True)
                .groupby("Equipo", as_index=False)["Puntos"]
                .sum()
            )
            ranking_total = preparar_ranking_tabla(ranking_total)

    if ranking_total is None:
        ranking_total = pd.DataFrame(columns=["Posicion", "Equipo", "Puntos"])
    ranking_club_final = ranking_clubes_desde_equipos(ranking_total)
    return partidos, ranking_total, ranking_club_final
