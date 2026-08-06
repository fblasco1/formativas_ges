# -*- coding: utf-8 -*-
"""Lectura y limpieza de CSV de partidos para el motor comparativo."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Tuple

import pandas as pd

from analisis.Ranking.core import crear_ranking_base, filtrar_categorias
from analisis.Ranking.seasons import FOCUS_YEARS, filtrar_anios, resolve_partidos_consolidado
from analisis.ranking_comparativo.clubes import club_desde_equipo
from analisis.ranking_comparativo.categorias_u import banda_u_desde_categoria
from mapeos.exclusiones_partidos import aplicar_exclusiones

COLUMNAS_RENOMBRE = {
    "equipo_local": "local",
    "equipo_visitante": "visitante",
    "pts_local": "ptsL",
    "pts_visitante": "ptsV",
    "año": "anio",
}


def normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    renombres_directos = {str(c).strip(): str(c).strip() for c in out.columns}
    for col in list(out.columns):
        cl = col.strip().lower()
        if cl in ("ptsl", "pts_local", "puntos_local"):
            renombres_directos[col] = "ptsL"
        elif cl in ("ptsv", "pts_visitante", "puntos_visitante"):
            renombres_directos[col] = "ptsV"
        elif cl in ("año", "ano"):
            renombres_directos[col] = "anio"
        elif cl == "equipo_local":
            renombres_directos[col] = "local"
        elif cl == "equipo_visitante":
            renombres_directos[col] = "visitante"
    out = out.rename(columns=renombres_directos)
    for vieja, nueva in COLUMNAS_RENOMBRE.items():
        if vieja in out.columns and nueva not in out.columns:
            out = out.rename(columns={vieja: nueva})
    return out


def cargar_partidos(
    path: Optional[Path] = None,
    *,
    sep: str = ";",
    years: Iterable[int] = FOCUS_YEARS,
    exclude_mini_premini: bool = True,
) -> pd.DataFrame:
    """
    Carga CSV, aplica exclusiones, normaliza equipos y enriquece columnas derivadas.
    """
    from utils.open_csv import leer_csv_con_encoding_detectado

    csv_path = Path(path) if path else resolve_partidos_consolidado()
    if not csv_path.is_file():
        raise FileNotFoundError(f"No existe el archivo de partidos: {csv_path}")

    raw = leer_csv_con_encoding_detectado(str(csv_path), sep)
    raw = normalizar_columnas(raw)
    raw, _ = aplicar_exclusiones(raw)
    data, _ = crear_ranking_base(raw)

    if exclude_mini_premini:
        data = filtrar_categorias(data, ("MINI", "PREMINI"))
    data = filtrar_anios(data, years)

    data = data.copy()
    data["fecha_norm"] = data["fecha"].astype(str).str.strip()
    data["club_local"] = data["local"].map(club_desde_equipo)
    data["club_visitante"] = data["visitante"].map(club_desde_equipo)
    data["banda_u"] = data["categoria"].map(banda_u_desde_categoria)
    data["anio"] = pd.to_numeric(data["anio"], errors="coerce").astype("Int64")

    requeridas = {
        "fecha",
        "local",
        "visitante",
        "categoria",
        "ptsL",
        "ptsV",
        "fase",
        "ronda",
        "nivel",
        "anio",
    }
    faltan = requeridas - set(data.columns)
    if faltan:
        raise ValueError(f"Columnas faltantes en el CSV: {sorted(faltan)}")

    return data.reset_index(drop=True)


def validar_datos(df: pd.DataFrame) -> Tuple[int, int]:
    """Devuelve (filas inválidas de marcador, filas sin banda U)."""
    pts_ok = pd.to_numeric(df["ptsL"], errors="coerce").notna() & pd.to_numeric(
        df["ptsV"], errors="coerce"
    ).notna()
    sin_banda = df["banda_u"].isna()
    return int((~pts_ok).sum()), int(sin_banda.sum())
