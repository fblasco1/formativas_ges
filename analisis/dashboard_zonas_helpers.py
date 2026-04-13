# -*- coding: utf-8 -*-
"""Funciones de agregación para dashboard_zonas_dash (sin depender de Dash)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objs as go

GEO = frozenset({"SUR", "OESTE", "NORTE", "CENTRO"})
CATS_TABLA_INTER = ["PREINFANTILES", "INFANTILES", "CADETES", "JUVENILES"]


def inferir_region_equipo(df_all: pd.DataFrame) -> dict[str, str]:
    """Moda de zona geográfica en Fase Regular por club (aparece como local o visitante)."""
    sub = df_all[
        (df_all["fase"] == "FASE REGULAR") & (df_all["zona"].isin(GEO))
    ]
    parts = []
    for col in ("local", "visitante"):
        parts.append(sub[[col, "zona"]].rename(columns={col: "equipo"}))
    if not parts:
        return {}
    long_df = pd.concat(parts, ignore_index=True)
    out: dict[str, str] = {}
    for eq, g in long_df.groupby("equipo"):
        m = g["zona"].mode()
        if len(m) > 0 and m.iloc[0] in GEO:
            out[str(eq)] = str(m.iloc[0])
    return out


def filtrar_partidos(
    base: pd.DataFrame,
    temporada_sel: list | None,
    fase_sel: list | None,
    ronda_sel: list | None = None,
    nivel_sel: list | None = None,
    region_zona_sel: list | None = None,
) -> pd.DataFrame:
    out = base.copy()
    if temporada_sel and "TODAS" not in temporada_sel and "anio" in out.columns:
        out = out[out["anio"].astype(str).isin([str(t) for t in temporada_sel])]
    if fase_sel and "TODAS" not in fase_sel:
        out = out[out["fase"].isin(fase_sel)]
    if ronda_sel and "TODAS" not in ronda_sel:
        out = out[out["ronda"].astype(str).isin([str(r) for r in ronda_sel])]
    if nivel_sel and "TODOS" not in nivel_sel:
        out = out[out["nivel"].astype(str).isin([str(n) for n in nivel_sel])]
    if region_zona_sel and "TODAS" not in region_zona_sel:
        out = out[out["zona"].isin(region_zona_sel)]
    return out


def tabla_promedios_por_region(df_f: pd.DataFrame) -> list[dict[str, Any]]:
    if df_f.empty:
        return []
    d = df_f.copy()
    d["ganador_pts"] = d[["ptsL", "ptsV"]].max(axis=1)
    d["perdedor_pts"] = d[["ptsL", "ptsV"]].min(axis=1)
    d["diff"] = (d["ptsL"] - d["ptsV"]).abs()
    rows: list[dict[str, Any]] = []
    for (zona, cat), g in d.groupby(["zona", "categoria"]):
        rows.append(
            {
                "Región": str(zona),
                "Categoría": str(cat),
                "Prom. ganador": round(float(g["ganador_pts"].mean()), 2),
                "Prom. perdedor": round(float(g["perdedor_pts"].mean()), 2),
                "Prom. diferencia": round(float(g["diff"].mean()), 2),
            }
        )
    return rows


def tabla_interconferencia(
    df_inter: pd.DataFrame, equipo_a_region: dict[str, str]
) -> list[dict[str, Any]]:
    """Victorias por región geográfica y categoría (interconferencia, fase regular)."""
    vacia = [
        {"Región": r, **{c: 0 for c in CATS_TABLA_INTER}, "TOTALES": 0}
        for r in sorted(GEO)
    ]
    if df_inter.empty:
        return vacia
    rows_count: dict[str, dict[str, int]] = {
        r: {c: 0 for c in CATS_TABLA_INTER} for r in sorted(GEO)
    }
    for _, row in df_inter.iterrows():
        cat = str(row["categoria"]).strip().upper()
        if cat not in CATS_TABLA_INTER:
            continue
        try:
            pl, pv = int(row["ptsL"]), int(row["ptsV"])
        except (TypeError, ValueError):
            continue
        if pl > pv:
            w = str(row["local"]).strip().upper()
        elif pv > pl:
            w = str(row["visitante"]).strip().upper()
        else:
            continue
        reg = equipo_a_region.get(w)
        if reg in rows_count:
            rows_count[reg][cat] += 1
    out: list[dict[str, Any]] = []
    for r in sorted(GEO):
        tot = sum(rows_count[r].values())
        out.append(
            {
                "Región": r,
                **{c: rows_count[r][c] for c in CATS_TABLA_INTER},
                "TOTALES": tot,
            }
        )
    return out


def get_equipos_region_nivel_tabla(
    base: pd.DataFrame,
    region: str,
    temporada_sel: list | None,
    fase_sel: list | None,
    nivel_sel: list | None,
) -> list[dict[str, Any]]:
    df_f = filtrar_partidos(
        base, temporada_sel, fase_sel, None, nivel_sel, None
    )
    df_f = df_f[df_f["zona"] == region]
    equipos = sorted(set(df_f["local"]).union(set(df_f["visitante"])))
    rows: list[dict[str, Any]] = []
    for eq in equipos:
        sub = df_f[(df_f["local"] == eq) | (df_f["visitante"] == eq)]
        if sub.empty:
            continue
        nm = sub["nivel"].astype(str).mode()
        nivel_val = str(nm.iloc[0]) if len(nm) else str(sub["nivel"].iloc[0])
        anios = sorted(sub["anio"].astype(str).unique())
        temp_str = (
            ", ".join(anios) if len(anios) <= 4 else f"{anios[0]}–{anios[-1]}"
        )
        rows.append(
            {
                "Equipo": eq,
                "Región": region,
                "Nivel 1ra Fase": nivel_val,
                "Temporada": temp_str,
            }
        )
    return rows


def get_table_data(
    df_tot_local: pd.DataFrame,
    detalles_map: dict[str, list],
    ranking_map: dict[str, float],
    expanded_equipo: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pos = 1
    for _, row in df_tot_local.iterrows():
        eq = str(row["equipo"])
        pr = ranking_map.get(eq)
        marcador = "🔽" if expanded_equipo == eq else "▶️"
        base: dict[str, Any] = {
            "posicion": str(pos),
            "equipo": f"{marcador} {eq}",
            "pj": int(row["pj"]),
            "ganados": int(row["ganados"]),
            "perdidos": int(row["perdidos"]),
            "diferencia": int(row["diferencia"]),
            "power_ranking": (
                round(float(pr), 2) if pr is not None and pd.notna(pr) else ""
            ),
            "temporada": "TOTAL",
        }
        rows.append(base)
        if expanded_equipo == eq:
            for det in detalles_map.get(eq, []):
                rows.append(
                    {
                        "posicion": "",
                        "equipo": f"  {det['temporada']}",
                        "pj": int(det["pj"]),
                        "ganados": int(det["ganados"]),
                        "perdidos": int(det["perdidos"]),
                        "diferencia": int(det["diferencia"]),
                        "power_ranking": "",
                        "temporada": str(det["temporada"]),
                    }
                )
        pos += 1
    return rows


def figura_torta_interconferencia_vacia() -> go.Figure:
    fig = go.Figure(
        data=[
            go.Pie(
                labels=["Menos de 10", "Entre 10 y 20", "Más de 20", "Más de 40"],
                values=[1, 0, 0, 0],
                hole=0.3,
                marker=dict(colors=["#2ca02c", "#ff7f0e", "#1f77b4", "#d62728"]),
            )
        ]
    )
    fig.update_layout(
        title="Diferencias de puntos en Interconferencia",
        legend=dict(font=dict(size=14)),
        margin=dict(l=10, r=10, t=40, b=10),
        height=250,
    )
    return fig


def figura_torta_diferencias(diffs: pd.Series) -> go.Figure:
    mas_40 = int((diffs > 40).sum())
    mas_20 = int(((diffs > 20) & (diffs <= 40)).sum())
    entre_10_20 = int(((diffs > 10) & (diffs <= 20)).sum())
    menos_10 = int((diffs <= 10).sum())
    labels = ["Menos de 10", "Entre 10 y 20", "Más de 20", "Más de 40"]
    values = [menos_10, entre_10_20, mas_20, mas_40]
    if sum(values) == 0:
        return figura_torta_interconferencia_vacia()
    colores = ["#2ca02c", "#ff7f0e", "#1f77b4", "#d62728"]
    fig = go.Figure(
        data=[go.Pie(labels=labels, values=values, hole=0.3, marker=dict(colors=colores))]
    )
    fig.update_layout(
        title="Diferencias de puntos en Interconferencia",
        legend=dict(font=dict(size=14)),
        margin=dict(l=10, r=10, t=40, b=10),
        height=250,
    )
    return fig
