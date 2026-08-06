# -*- coding: utf-8 -*-
"""Algoritmo institucional: baseline GES + factor de tira P_tira por jornada."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

from analisis.Ranking.core import preparar_ranking_tabla
from analisis.ranking_comparativo.baseline import (
    enriquecer_partidos_baseline,
    ranking_clubes_desde_equipos,
    ranking_equipos_desde_partidos,
)
from analisis.ranking_comparativo.categorias_u import (
    bandas_obligatorias_tira,
    penalizacion_por_banda_faltante,
)
from analisis.ranking_comparativo.clubes import club_desde_equipo


def _id_jornada(df: pd.DataFrame) -> pd.Series:
    """Clave de jornada: fecha + club local + club visitante (orden institucional)."""
    return (
        df["fecha_norm"].astype(str)
        + "|"
        + df["club_local"].astype(str)
        + "|"
        + df["club_visitante"].astype(str)
    )


def factor_tira_club(
    club: str,
    bandas_presentes: set[str],
    *,
    bandas_requeridas: Optional[set[str]] = None,
) -> float:
    """
    P_tira inicia en 1.0; resta penalizaciones por cada banda U obligatoria ausente.
    """
    requeridas = bandas_requeridas or bandas_obligatorias_tira()
    p = 1.0
    for banda in sorted(requeridas):
        if banda not in bandas_presentes:
            p -= penalizacion_por_banda_faltante(banda)
    return max(0.0, p)


def _bandas_presentes_por_club_jornada(
    df: pd.DataFrame,
    df_presencia: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Por (jornada_id, club): bandas U presentes en la jornada.

    ``df_presencia`` puede incluir MINI/PREMINI solo para detectar U9/U11 sin
    sumar BP de esas categorías.
    """
    filas: List[dict] = []
    src = df_presencia if df_presencia is not None else df
    src = src.copy()
    src["jornada_id"] = _id_jornada(src)

    for jid, grp in src.groupby("jornada_id", sort=False):
        clubs = {grp["club_local"].iloc[0], grp["club_visitante"].iloc[0]}
        for club in clubs:
            sub = grp[(grp["club_local"] == club) | (grp["club_visitante"] == club)]
            bandas = set(sub["banda_u"].dropna().unique()) & bandas_obligatorias_tira()
            filas.append({"jornada_id": jid, "club": club, "bandas_presentes": bandas})

    return pd.DataFrame(filas)


def aplicar_penalizacion_tira(
    df: pd.DataFrame,
    df_presencia: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Calcula P_tira por club y jornada; reparte puntos de fila según contribución del club.
    """
    out = df.copy()
    out["jornada_id"] = _id_jornada(out)

    presencia = _bandas_presentes_por_club_jornada(out, df_presencia)
    presencia["P_tira"] = presencia.apply(
        lambda r: factor_tira_club(r["club"], r["bandas_presentes"]), axis=1
    )
    p_lookup = presencia.rename(
        columns={"club": "club_key", "P_tira": "P_tira_key"}
    )

    out = out.merge(
        p_lookup[["jornada_id", "club_key", "P_tira_key"]],
        left_on=["jornada_id", "club_local"],
        right_on=["jornada_id", "club_key"],
        how="left",
    )
    out.rename(columns={"P_tira_key": "P_tira_local"}, inplace=True)
    out.drop(columns=["club_key"], inplace=True)

    out = out.merge(
        p_lookup[["jornada_id", "club_key", "P_tira_key"]],
        left_on=["jornada_id", "club_visitante"],
        right_on=["jornada_id", "club_key"],
        how="left",
    )
    out.rename(columns={"P_tira_key": "P_tira_visitante"}, inplace=True)
    out.drop(columns=["club_key"], inplace=True)

    out["P_tira_local"] = out["P_tira_local"].fillna(1.0)
    out["P_tira_visitante"] = out["P_tira_visitante"].fillna(1.0)

    out["Puntos_local_inst"] = out["LocalSuma"] * out["P_tira_local"]
    out["Puntos_visitante_inst"] = out["VisitaSuma"] * out["P_tira_visitante"]
    return out


def ranking_clubes_institucional(df: pd.DataFrame) -> pd.DataFrame:
    """Suma puntos institucionales por club (local + visitante)."""
    loc = (
        df.groupby("club_local", as_index=False)["Puntos_local_inst"]
        .sum()
        .rename(columns={"club_local": "Club", "Puntos_local_inst": "Puntos"})
    )
    vis = (
        df.groupby("club_visitante", as_index=False)["Puntos_visitante_inst"]
        .sum()
        .rename(columns={"club_visitante": "Club", "Puntos_visitante_inst": "Puntos"})
    )
    agg = (
        pd.concat([loc, vis], ignore_index=True)
        .groupby("Club", as_index=False)["Puntos"]
        .sum()
    )
    agg = agg.sort_values("Puntos", ascending=False).reset_index(drop=True)
    agg["Posicion"] = range(1, len(agg) + 1)
    agg["Puntos"] = agg["Puntos"].round(0).astype(int)
    return agg[["Posicion", "Club", "Puntos"]]


def resumen_jornadas_tira(
    df: pd.DataFrame,
    df_presencia: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Tabla auxiliar: jornada, club, P_tira, bandas presentes/faltantes."""
    presencia = _bandas_presentes_por_club_jornada(df, df_presencia)
    req = bandas_obligatorias_tira()

    def _faltantes(bandas: set) -> str:
        return ",".join(sorted(req - bandas)) if req - bandas else ""

    presencia["P_tira"] = presencia.apply(
        lambda r: factor_tira_club(r["club"], r["bandas_presentes"]), axis=1
    )
    presencia["bandas_ok"] = presencia["bandas_presentes"].map(
        lambda b: ",".join(sorted(b))
    )
    presencia["bandas_faltantes"] = presencia["bandas_presentes"].map(_faltantes)
    return presencia[
        ["jornada_id", "club", "P_tira", "bandas_ok", "bandas_faltantes"]
    ]


def procesar_institucional_anual(
    data: pd.DataFrame,
    years: Iterable[int],
    ranking_prev_equipos: Optional[pd.DataFrame] = None,
    *,
    data_presencia: pd.DataFrame | None = None,
) -> Tuple[Dict[int, pd.DataFrame], pd.DataFrame]:
    """
    Misma cadena ORP que el baseline; aplica tira al acumular puntos por club.
    """
    years_list = list(years)
    partidos: Dict[int, pd.DataFrame] = {}
    acum_club: Optional[pd.DataFrame] = None
    ranking_prev = ranking_prev_equipos

    for i, year in enumerate(years_list):
        use_orp = i > 0 and ranking_prev is not None and not ranking_prev.empty
        prev = (
            ranking_prev
            if use_orp
            else pd.DataFrame(columns=["Equipo", "Puntos", "Posicion"])
        )
        df_year = data[data["anio"] == year].copy()
        if df_year.empty:
            continue

        base = enriquecer_partidos_baseline(df_year, prev, use_orp=use_orp)
        pres_year = None
        if data_presencia is not None:
            pres_year = data_presencia[data_presencia["anio"] == year]
        inst = aplicar_penalizacion_tira(base, pres_year)
        partidos[year] = inst

        ranking_equipos = ranking_equipos_desde_partidos(base)
        ranking_prev = ranking_equipos

        club_anual = ranking_clubes_institucional(inst)
        if acum_club is None:
            acum_club = club_anual.copy()
        else:
            acum_club = (
                pd.concat([acum_club, club_anual], ignore_index=True)
                .groupby("Club", as_index=False)["Puntos"]
                .sum()
            )
            acum_club = acum_club.sort_values("Puntos", ascending=False).reset_index(
                drop=True
            )
            acum_club["Posicion"] = range(1, len(acum_club) + 1)

    if acum_club is None:
        acum_club = pd.DataFrame(columns=["Posicion", "Club", "Puntos"])
    return partidos, acum_club


def procesar_institucional_acumulado_global(
    partidos_por_anio: Dict[int, pd.DataFrame],
) -> pd.DataFrame:
    """Recalcula ranking club institucional sobre todos los partidos ya penalizados."""
    if not partidos_por_anio:
        return pd.DataFrame(columns=["Posicion", "Club", "Puntos"])
    todo = pd.concat(partidos_por_anio.values(), ignore_index=True)
    return ranking_clubes_institucional(todo)
