# -*- coding: utf-8 -*-
"""BP, ORP y puntos por partido (baseline y renivelación)."""

from __future__ import annotations

from typing import Dict

import pandas as pd

from analisis.Ranking.core import asignar_basis_points, get_team_positions
from analisis.renivelacion_tiras.categorias import es_forfait_perdedor
from analisis.renivelacion_tiras.pesos import (
    peso_anio,
    peso_etapa_renivelacion,
    peso_fase_baseline,
    peso_nivel_baseline,
    peso_nivel_renivelacion,
    peso_ronda_baseline,
)


def calcular_orp(df: pd.DataFrame, ranking_prev: pd.DataFrame) -> pd.DataFrame:
    """ORP por fila usando ranking de tiras del año anterior."""
    out = df.copy()
    if ranking_prev.empty:
        out["ORP_LOCAL"] = 0.0
        out["ORP_VISITA"] = 0.0
        return out

    r = ranking_prev.copy()
    if "Tira" in r.columns and "Equipo" not in r.columns:
        r = r.rename(columns={"Tira": "Equipo"})
    col_pts = "Puntos" if "Puntos" in r.columns else "Total_Renivelacion"
    r = r.sort_values(col_pts, ascending=False).reset_index(drop=True)
    pos = get_team_positions(r[["Equipo", col_pts]].rename(columns={col_pts: "Puntos"}))
    n = len(ranking_prev)
    avg = (n + 1) / 2 if n > 0 else 0.0

    def orp_local(row):
        p = pos.get(row["club_tira_visitante"], avg)
        return 1.5 * (avg - p)

    def orp_vis(row):
        p = pos.get(row["club_tira_local"], avg)
        return 1.5 * (avg - p)

    out["ORP_LOCAL"] = out.apply(orp_local, axis=1)
    out["ORP_VISITA"] = out.apply(orp_vis, axis=1)
    return out


def enriquecer_partidos(
    df: pd.DataFrame,
    ranking_prev: pd.DataFrame,
    *,
    usar_orp: bool,
) -> pd.DataFrame:
    out = df.copy()
    bp = out.apply(asignar_basis_points, axis=1, result_type="expand")
    out["BP_LOCAL"], out["BP_VISITA"] = bp[0], bp[1]

    if usar_orp:
        out = calcular_orp(out, ranking_prev)
    else:
        out["ORP_LOCAL"] = 0.0
        out["ORP_VISITA"] = 0.0

    pa = out["anio"].map(peso_anio)
    pf = out.apply(lambda r: peso_fase_baseline(r["fase"], r["nivel"]), axis=1)
    pr = out.apply(lambda r: peso_ronda_baseline(r["ronda"], int(r["anio"])), axis=1)
    pn = out["nivel"].map(peso_nivel_baseline)
    factor_b = pa * pf * pr * pn
    out["Pts_Baseline_Local"] = factor_b * (out["BP_LOCAL"] + out["ORP_LOCAL"])
    out["Pts_Baseline_Visita"] = factor_b * (out["BP_VISITA"] + out["ORP_VISITA"])

    pe = out.apply(
        lambda r: peso_etapa_renivelacion(r["fase"], r["ronda"], int(r["anio"])),
        axis=1,
    )
    pnr = out.apply(
        lambda r: peso_nivel_renivelacion(r["nivel"], r["ronda"], int(r["anio"])),
        axis=1,
    )
    factor_r = pa * pe * pnr
    out["Pts_Reniv_Local"] = 0.0
    out["Pts_Reniv_Visita"] = 0.0
    comp = out["es_competitivo"]
    out.loc[comp, "Pts_Reniv_Local"] = (
        factor_r[comp] * (out.loc[comp, "BP_LOCAL"] + out.loc[comp, "ORP_LOCAL"])
    )
    out.loc[comp, "Pts_Reniv_Visita"] = (
        factor_r[comp] * (out.loc[comp, "BP_VISITA"] + out.loc[comp, "ORP_VISITA"])
    )

    pl = pd.to_numeric(out["ptsL"], errors="coerce")
    pv = pd.to_numeric(out["ptsV"], errors="coerce")

    def _ff(pp, pr):
        try:
            return es_forfait_perdedor(int(pp), int(pr))
        except (TypeError, ValueError):
            return False

    out["forfait_local"] = [_ff(a, b) for a, b in zip(pl, pv)]
    out["forfait_visitante"] = [_ff(b, a) for a, b in zip(pl, pv)]

    return out


def ranking_tiras_desde_puntos(
    df_long: pd.DataFrame,
    col_puntos: str,
) -> pd.DataFrame:
    """Ranking ordenado por columna de puntos acumulados."""
    r = df_long.sort_values(col_puntos, ascending=False).reset_index(drop=True)
    r["Posicion"] = range(1, len(r) + 1)
    return r
