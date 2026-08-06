# -*- coding: utf-8 -*-
"""Carga incremental de CSV de partidos."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

from analisis.Ranking.seasons import DATA_DIR, FOCUS_YEARS, filtrar_anios
from analisis.renivelacion_tiras.categorias import (
    bucket_renivelacion,
    es_categoria_competitiva,
)
from analisis.renivelacion_tiras.tiras import tira_desde_equipo
from mapeos.exclusiones_partidos import aplicar_exclusiones
from mapeos.loader import cargar_mapeo_equipos, normalizar_columna_equipos
from utils.open_csv import leer_csv_con_encoding_detectado

HISTORICO_YEARS = (2023, 2024, 2025)
ANIO_DINAMICO = 2026


def _renombrar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    mapping = {}
    for col in out.columns:
        c = str(col).strip()
        cl = c.lower()
        if cl in ("ptsl", "pts_local", "puntos_local"):
            mapping[c] = "ptsL"
        elif cl in ("ptsv", "pts_visitante", "puntos_visitante"):
            mapping[c] = "ptsV"
        elif cl in ("año", "ano"):
            mapping[c] = "anio"
        elif cl == "equipo_local":
            mapping[c] = "local"
        elif cl == "equipo_visitante":
            mapping[c] = "visitante"
        else:
            mapping[c] = c
    out = out.rename(columns=mapping)
    return out


def _detect_sep(path: Path) -> str:
    sample = path.read_bytes()[:4000].decode("utf-8", errors="replace")
    return ";" if sample.count(";") > sample.count(",") else ","


def cargar_partidos_anios(
    years: Iterable[int],
    *,
    data_dir: Path = DATA_DIR,
) -> pd.DataFrame:
    mapeo = cargar_mapeo_equipos()
    partes: list[pd.DataFrame] = []

    for year in years:
        path = data_dir / f"partidos_{year}.csv"
        if not path.is_file():
            continue
        sep = _detect_sep(path)
        chunk = leer_csv_con_encoding_detectado(str(path), sep)
        chunk = _renombrar_columnas(chunk)
        if "anio" not in chunk.columns:
            chunk["anio"] = year
        partes.append(chunk)

    if not partes:
        return pd.DataFrame()

    df = pd.concat(partes, ignore_index=True)
    df, _ = aplicar_exclusiones(df)
    df = filtrar_anios(df, years)

    df["local"] = normalizar_columna_equipos(df["local"], mapeo, upper=True)
    df["visitante"] = normalizar_columna_equipos(df["visitante"], mapeo, upper=True)
    df = df.dropna(subset=["local", "visitante"])
    libre = r"\bLIBRE\b"
    df = df[
        ~df["local"].astype(str).str.contains(libre, case=False, na=False, regex=True)
        & ~df["visitante"].astype(str).str.contains(libre, case=False, na=False, regex=True)
    ]

    df["anio"] = pd.to_numeric(df["anio"], errors="coerce").astype("Int64")
    df["fecha_norm"] = df["fecha"].astype(str).str.strip()
    df["club_tira_local"] = df["local"].map(lambda x: tira_desde_equipo(x, mapeo))
    df["club_tira_visitante"] = df["visitante"].map(lambda x: tira_desde_equipo(x, mapeo))
    df["bucket_renivelacion"] = df.apply(
        lambda r: bucket_renivelacion(r["categoria"], r["anio"]), axis=1
    )
    df["es_competitivo"] = df["bucket_renivelacion"].notna()

    return df.reset_index(drop=True)


def cargar_historico() -> pd.DataFrame:
    return cargar_partidos_anios(HISTORICO_YEARS)


def cargar_dinamico_2026() -> pd.DataFrame:
    return cargar_partidos_anios([ANIO_DINAMICO])
