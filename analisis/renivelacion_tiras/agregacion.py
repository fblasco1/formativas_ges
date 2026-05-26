# -*- coding: utf-8 -*-
"""Agregación por Tira: puntos por categoría FeBAMBA y penalizaciones forfait."""

from __future__ import annotations

import pandas as pd

from analisis.renivelacion_tiras.categorias import (
    CATEGORIAS_COMPETITIVAS,
    PENALIZACION_FORFAIT_TIRA,
    columna_puntos,
    sufijo_columna,
)


def _puntos_tira_lado(df: pd.DataFrame, col_tira: str, col_pts: str) -> pd.DataFrame:
    return (
        df.groupby([col_tira, "bucket_renivelacion"], as_index=False)[col_pts]
        .sum()
        .rename(columns={col_tira: "Tira", col_pts: "Puntos"})
    )


def agregar_puntos_competitivos(
    df: pd.DataFrame,
    col_pts_local: str,
    col_pts_visita: str,
) -> pd.DataFrame:
    """
    Suma puntos solo de INFANTILES, CADETES, JUVENILES y LIGA PROXIMO por tira.
    """
    loc = df[df["es_competitivo"]].copy()
    vis = df[df["es_competitivo"]].copy()

    pl = _puntos_tira_lado(loc, "club_tira_local", col_pts_local)
    pv = _puntos_tira_lado(vis, "club_tira_visitante", col_pts_visita)

    todo = pd.concat([pl, pv], ignore_index=True)
    return (
        todo.groupby(["Tira", "bucket_renivelacion"], as_index=False)["Puntos"]
        .sum()
    )


def contar_forfaits_por_tira(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cuenta partidos forfait (0-20 en contra) por tira en TODAS las categorías.
    """
    sub_l = df[df["forfait_local"]][["club_tira_local"]].rename(
        columns={"club_tira_local": "Tira"}
    )
    sub_v = df[df["forfait_visitante"]][["club_tira_visitante"]].rename(
        columns={"club_tira_visitante": "Tira"}
    )
    ff = pd.concat([sub_l, sub_v], ignore_index=True)
    if ff.empty:
        return pd.DataFrame(columns=["Tira", "Cantidad_Forfaits"])
    return (
        ff.groupby("Tira", as_index=False)
        .size()
        .rename(columns={"size": "Cantidad_Forfaits"})
    )


def pivot_categorias(agg: pd.DataFrame, prefijo: str) -> pd.DataFrame:
    """Columnas Pts_Aportados_INFANTILES, Pts_Aportados_LIGA_PROXIMO, …"""
    if agg.empty:
        return pd.DataFrame(columns=["Tira"])

    wide = agg.pivot_table(
        index="Tira",
        columns="bucket_renivelacion",
        values="Puntos",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()

    renombres = {
        c: columna_puntos(prefijo, c)
        for c in wide.columns
        if c != "Tira" and c in CATEGORIAS_COMPETITIVAS
    }
    wide = wide.rename(columns=renombres)

    for cat in CATEGORIAS_COMPETITIVAS:
        col = columna_puntos(prefijo, cat)
        if col not in wide.columns:
            wide[col] = 0

    cols = ["Tira"] + [columna_puntos(prefijo, c) for c in CATEGORIAS_COMPETITIVAS]
    return wide[cols]


def columnas_ranking_export(df: pd.DataFrame) -> list[str]:
    """Columnas ordenadas para CSV / Streamlit."""
    cols_pts = [columna_puntos("Pts_Aportados", c) for c in CATEGORIAS_COMPETITIVAS]
    base = ["Tira"] + cols_pts + [
        "Cantidad_Forfaits",
        "Total_Penalizaciones",
        "Total_Renivelacion",
    ]
    return [c for c in base if c in df.columns]


def construir_ranking_renivelacion(df_partidos: pd.DataFrame) -> pd.DataFrame:
    agg = agregar_puntos_competitivos(
        df_partidos, "Pts_Reniv_Local", "Pts_Reniv_Visita"
    )
    agg = agg[agg["bucket_renivelacion"].isin(CATEGORIAS_COMPETITIVAS)]
    wide = pivot_categorias(agg, "Pts_Aportados")

    ff = contar_forfaits_por_tira(df_partidos)
    out = wide.merge(ff, on="Tira", how="left")
    out["Cantidad_Forfaits"] = out["Cantidad_Forfaits"].fillna(0).astype(int)
    out["Total_Penalizaciones"] = (
        out["Cantidad_Forfaits"] * PENALIZACION_FORFAIT_TIRA
    )
    cols_pts = [c for c in out.columns if c.startswith("Pts_Aportados_")]
    out["Total_Renivelacion"] = out[cols_pts].sum(axis=1) - out["Total_Penalizaciones"]
    out["Total_Renivelacion"] = out["Total_Renivelacion"].round(0).astype(int)
    for c in cols_pts:
        out[c] = out[c].round(0).astype(int)

    return out.sort_values("Total_Renivelacion", ascending=False).reset_index(drop=True)


def construir_ranking_baseline(df_partidos: pd.DataFrame) -> pd.DataFrame:
    agg = agregar_puntos_competitivos(
        df_partidos, "Pts_Baseline_Local", "Pts_Baseline_Visita"
    )
    agg = agg[agg["bucket_renivelacion"].isin(CATEGORIAS_COMPETITIVAS)]
    wide = pivot_categorias(agg, "Pts_Baseline")
    cols = [c for c in wide.columns if c.startswith("Pts_Baseline_")]
    wide["Total_Baseline"] = wide[cols].sum(axis=1).round(0).astype(int)
    return wide.sort_values("Total_Baseline", ascending=False).reset_index(drop=True)


def fusionar_acumulados(
    hist: pd.DataFrame,
    nuevo: pd.DataFrame,
) -> pd.DataFrame:
    cols_sum = sorted(
        {
            c
            for c in set(hist.columns) | set(nuevo.columns)
            if c.startswith("Pts_Aportados_") or c == "Cantidad_Forfaits"
        }
    )
    h = hist.set_index("Tira")
    n = nuevo.set_index("Tira")
    out = h.reindex(columns=cols_sum, fill_value=0).add(
        n.reindex(columns=cols_sum, fill_value=0), fill_value=0
    )
    out = out.reset_index()
    out["Cantidad_Forfaits"] = out["Cantidad_Forfaits"].astype(int)
    out["Total_Penalizaciones"] = (
        out["Cantidad_Forfaits"] * PENALIZACION_FORFAIT_TIRA
    )
    cols_pts = [c for c in out.columns if c.startswith("Pts_Aportados_")]
    out["Total_Renivelacion"] = (
        out[cols_pts].sum(axis=1) - out["Total_Penalizaciones"]
    ).round(0).astype(int)
    for c in cols_pts:
        out[c] = out[c].round(0).astype(int)
    return out.sort_values("Total_Renivelacion", ascending=False).reset_index(drop=True)
