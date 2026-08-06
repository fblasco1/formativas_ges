# -*- coding: utf-8 -*-
"""Motor de Power Ranking: basis points, ORP y pesos por año/fase/ronda/nivel."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union

import pandas as pd

PathLike = Union[str, Path]

from analisis.Ranking.seasons import (  # noqa: E402
    ACCUMULADO_DESDE,
    FOCUS_YEARS,
    anos_con_patron_ronda_clasico,
    filtrar_anios,
    peso_anio_configurado,
    ranking_acumulado_filename,
    resolve_partidos_consolidado,
)

DEFAULT_YEARS: Tuple[int, ...] = FOCUS_YEARS
DEFAULT_EXCLUDE_CATEGORIES: Tuple[str, ...] = ("MINI", "PREMINI")


def crear_ranking_base(data: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Normaliza equipos (equipos_map.json) y devuelve partidos + ranking base en cero."""
    from mapeos.loader import cargar_mapeo_equipos, normalizar_columna_equipos

    mapeo = cargar_mapeo_equipos()
    data = data.copy()
    data["local"] = normalizar_columna_equipos(data["local"], mapeo, upper=True)
    data["visitante"] = normalizar_columna_equipos(data["visitante"], mapeo, upper=True)
    data = data.dropna(subset=["local", "visitante"])
    libre = r"\bLIBRE\b"
    data = data[
        ~data["local"].astype(str).str.contains(libre, case=False, na=False, regex=True)
        & ~data["visitante"].astype(str).str.contains(libre, case=False, na=False, regex=True)
    ]
    ranking_base = pd.DataFrame({"Equipo": data["local"].unique(), "Puntos": 0})
    return data, ranking_base


def asignar_basis_points(row: pd.Series) -> Tuple[int, int]:
    """Basis points local y visitante según marcador (reglas FIBA-style)."""
    try:
        pts_l = int(row["ptsL"])
        pts_v = int(row["ptsV"])
    except (ValueError, TypeError, KeyError):
        return (0, 0)

    if pts_l == 20 and pts_v == 0:
        return (700, 0)
    if pts_l == 0 and pts_v == 20:
        return (0, 700)
    if pts_l == 0 and pts_v == 0:
        return (0, 0)

    diff = abs(pts_l - pts_v)
    if pts_l > pts_v:
        if diff >= 20:
            return (750, 250)
        if diff >= 10:
            return (700, 300)
        return (650, 350)
    if pts_v > pts_l:
        if diff >= 20:
            return (250, 750)
        if diff >= 10:
            return (300, 700)
        return (350, 650)
    return (0, 0)


def peso_por_anio(anio) -> float:
    return peso_anio_configurado(anio)


def peso_por_fase(fase, nivel) -> float:
    fase_u = str(fase).upper()
    nivel_s = str(nivel)
    if "FINAL FOUR" in fase_u:
        return 1
    if "PLAYOFF" in fase_u:
        if nivel_s in ["INTERCONFERENCIA", "INTERCONFERENCIA A", "INTERCONFERENCIA B"]:
            return 1
        return 0.75
    if "FASE REGULAR" in fase_u:
        return 0.65
    return 1


def peso_por_ronda(ronda, anio) -> float:
    ronda_u = str(ronda).upper()
    anio_i = int(anio)
    if ronda_u in ["1RA FASE"]:
        return 1
    if ronda_u in ["2DA FASE"]:
        return 2 if anos_con_patron_ronda_clasico(anio_i) else 1
    if ronda_u in ["3RA FASE"]:
        return 1 if anos_con_patron_ronda_clasico(anio_i) else 2
    if ronda_u == "OCTAVOS DE FINAL":
        return 3
    if ronda_u == "CUARTOS DE FINAL":
        return 4
    if ronda_u in ("SEMIFINAL", "FINAL"):
        return 6
    return 1


def peso_por_nivel(nivel) -> float:
    nivel_u = str(nivel).upper()
    if nivel_u in ["INTERCONFERENCIA A", "INTERCONFERENCIA"]:
        return 2
    if "INTERCONFERENCIA B" in nivel_u:
        return 1.5
    if nivel_u == "1":
        return 1
    if nivel_u == "2":
        return 0.85
    if nivel_u == "3":
        return 0.75
    return 1


def get_team_positions(ranking_df: pd.DataFrame) -> Dict[str, int]:
    return {row["Equipo"]: i + 1 for i, row in ranking_df.iterrows()}


def calculate_orp_vectorized(df: pd.DataFrame, prev_ranking: pd.DataFrame) -> pd.DataFrame:
    team_pos = get_team_positions(prev_ranking)
    n = len(prev_ranking)
    avg = (n + 1) / 2 if n > 0 else 0

    def orp_local(row):
        vis_pos = team_pos.get(row["visitante"], avg)
        return 1.5 * (avg - vis_pos)

    def orp_visit(row):
        loc_pos = team_pos.get(row["local"], avg)
        return 1.5 * (avg - loc_pos)

    df = df.copy()
    df["ORP_LOCAL"] = df.apply(orp_local, axis=1)
    df["ORP_VISITA"] = df.apply(orp_visit, axis=1)
    return df


def _aplicar_pesos_y_puntos(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["peso_nivel"] = df["nivel"].apply(peso_por_nivel)
    df["peso_anio"] = df["anio"].apply(peso_por_anio)
    df["peso_ronda"] = df.apply(lambda row: peso_por_ronda(row["ronda"], row["anio"]), axis=1)
    df["peso_fase"] = df.apply(lambda row: peso_por_fase(row["fase"], row["nivel"]), axis=1)
    factor = df["peso_fase"] * df["peso_ronda"] * df["peso_anio"] * df["peso_nivel"]
    df["LocalSuma"] = factor * (df["BP_LOCAL"] + df["ORP_LOCAL"])
    df["VisitaSuma"] = factor * (df["BP_VISITA"] + df["ORP_VISITA"])
    return df


def _ranking_desde_partidos(df: pd.DataFrame) -> pd.DataFrame:
    local = (
        df.groupby("local")
        .agg({"LocalSuma": "sum"})
        .reset_index()
        .rename(columns={"local": "Equipo", "LocalSuma": "Puntos"})
    )
    visitante = (
        df.groupby("visitante")
        .agg({"VisitaSuma": "sum"})
        .reset_index()
        .rename(columns={"visitante": "Equipo", "VisitaSuma": "Puntos"})
    )
    ranking = pd.concat([local, visitante]).groupby("Equipo", as_index=False).agg({"Puntos": "sum"})
    return ranking.sort_values(by="Puntos", ascending=False).reset_index(drop=True)


def process_year(
    data: pd.DataFrame,
    prev_ranking: pd.DataFrame,
    year: int,
    *,
    use_orp: bool = True,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Calcula ranking de un año; ORP usa ``prev_ranking`` si ``use_orp``."""
    df = data[data["anio"] == year].copy()
    bp = df.apply(asignar_basis_points, axis=1, result_type="expand")
    df["BP_LOCAL"], df["BP_VISITA"] = bp[0], bp[1]
    if use_orp:
        df = calculate_orp_vectorized(df, prev_ranking)
    else:
        df["ORP_LOCAL"] = 0
        df["ORP_VISITA"] = 0
    df = _aplicar_pesos_y_puntos(df)
    return df, _ranking_desde_partidos(df)


def preparar_ranking_tabla(ranking: pd.DataFrame) -> pd.DataFrame:
    """Ordena por puntos, asigna posición y deja puntos como enteros (sin decimales)."""
    if ranking.empty:
        return pd.DataFrame(columns=["Posicion", "Equipo", "Puntos"])
    out = ranking.sort_values(by="Puntos", ascending=False).reset_index(drop=True)
    out["Posicion"] = range(1, len(out) + 1)
    out["Puntos"] = out["Puntos"].round(0).astype(int)
    return out[["Posicion", "Equipo", "Puntos"]]


def process_all_years(
    data: pd.DataFrame,
    years: Iterable[int],
    ranking_init: Optional[pd.DataFrame] = None,
    *,
    output_dir: Optional[PathLike] = None,
    verbose: bool = True,
) -> Tuple[Dict[int, Tuple[pd.DataFrame, pd.DataFrame]], pd.DataFrame]:
    """
    Procesa años en orden acumulando ranking total.

    Si ``output_dir`` está definido, escribe ``{year}.csv``, ``Ranking{year}.csv``
    y ``Ranking{desde}-{year}.csv`` acumulado (desde ``ACCUMULADO_DESDE``) en ese directorio.
    """
    years_list = list(years)
    rankings: Dict[int, Tuple[pd.DataFrame, pd.DataFrame]] = {}
    ranking_total = ranking_init.copy() if ranking_init is not None else None
    out_path = Path(output_dir) if output_dir else None
    if out_path:
        out_path.mkdir(parents=True, exist_ok=True)

    for i, year in enumerate(years_list):
        if verbose:
            print(f"Procesando año {year}...")
        use_orp = i > 0 and ranking_total is not None
        prev = ranking_total if use_orp else pd.DataFrame({"Equipo": [], "Puntos": []})
        df, ranking = process_year(data, prev, year, use_orp=use_orp)
        rankings[year] = (df, ranking)

        if ranking_total is None:
            ranking_total = ranking.copy()
        else:
            ranking_total = (
                pd.concat([ranking_total, ranking])
                .groupby("Equipo", as_index=False)
                .agg({"Puntos": "sum"})
            )
            ranking_total = ranking_total.sort_values(by="Puntos", ascending=False).reset_index(drop=True)

        if out_path:
            df.to_csv(out_path / f"{year}.csv", index=False)
            preparar_ranking_tabla(ranking).to_csv(
                out_path / f"Ranking{year}.csv", index=False
            )
            preparar_ranking_tabla(ranking_total).to_csv(
                out_path / ranking_acumulado_filename(year), index=False
            )

    if ranking_total is None:
        ranking_total = pd.DataFrame(columns=["Equipo", "Puntos"])
    return rankings, ranking_total


def filtrar_categorias(
    data: pd.DataFrame,
    exclude: Iterable[str] = DEFAULT_EXCLUDE_CATEGORIES,
) -> pd.DataFrame:
    excl = {c.strip().upper() for c in exclude}
    if "categoria" not in data.columns or not excl:
        return data
    return data[~data["categoria"].str.upper().isin(excl)]


def cargar_partidos_csv(path: PathLike, sep: str = ";") -> pd.DataFrame:
    from utils.open_csv import leer_csv_con_encoding_detectado

    return leer_csv_con_encoding_detectado(str(path), sep)


def preparar_datos_ranking(
    path: PathLike,
    *,
    sep: str = ";",
    exclude_categories: Iterable[str] = DEFAULT_EXCLUDE_CATEGORIES,
    years: Optional[Iterable[int]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Carga CSV consolidado, filtra categorías/temporadas y devuelve (partidos, ranking_base)."""
    data = cargar_partidos_csv(path, sep=sep)
    if years is not None:
        data = filtrar_anios(data, years)
    from mapeos.exclusiones_partidos import aplicar_exclusiones  # noqa: E402

    data, _ = aplicar_exclusiones(data)
    data, ranking_base = crear_ranking_base(data)
    data = filtrar_categorias(data, exclude_categories)
    return data, ranking_base
