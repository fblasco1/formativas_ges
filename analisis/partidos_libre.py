# -*- coding: utf-8 -*-
"""Análisis de partidos con equipo placeholder LIBRE en GES."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from analisis.Ranking.seasons import FOCUS_YEARS, resolve_partidos_consolidado
from pipelines.scrape_temporadas import TORNEOS

GES_BASE = "https://competicionescabb.gesdeportiva.es/competicion.aspx"


def url_torneo_ges(anio: int) -> str:
    info = TORNEOS.get(int(anio))
    if not info:
        return GES_BASE
    return info["url"]


def es_libre(nombre: str) -> bool:
    return str(nombre).strip().upper() == "LIBRE"


def cargar_partidos(path: Optional[Path] = None) -> pd.DataFrame:
    from utils.open_csv import leer_csv_con_encoding_detectado

    p = Path(path) if path else resolve_partidos_consolidado()
    df = leer_csv_con_encoding_detectado(str(p), ";")
    df["anio"] = pd.to_numeric(df["anio"], errors="coerce")
    return df


def filtrar_partidos_libre(df: pd.DataFrame) -> pd.DataFrame:
    loc = df["local"].astype(str).str.upper().eq("LIBRE")
    vis = df["visitante"].astype(str).str.upper().eq("LIBRE")
    return df[loc | vis].copy()


def _equipos_en_grupo(df: pd.DataFrame, row: pd.Series) -> set[str]:
    mask = (
        (df["anio"] == row["anio"])
        & (df["categoria"] == row["categoria"])
        & (df["zona"] == row["zona"])
        & (df["grupo"] == row["grupo"])
    )
    sub = df[mask]
    eq = set(sub["local"].astype(str)) | set(sub["visitante"].astype(str))
    return {e for e in eq if not es_libre(e)}


def _equipos_activos_fecha(df: pd.DataFrame, row: pd.Series) -> set[str]:
    mask = (
        (df["anio"] == row["anio"])
        & (df["categoria"] == row["categoria"])
        & (df["zona"] == row["zona"])
        & (df["grupo"] == row["grupo"])
        & (df["fecha"] == row["fecha"])
    )
    sub = df[mask]
    eq = set(sub["local"].astype(str)) | set(sub["visitante"].astype(str))
    return {e for e in eq if not es_libre(e)}


def inferir_candidato_libre_local(df: pd.DataFrame, row: pd.Series) -> str:
    """
    Si LIBRE es local, suele ser fecha libre del grupo: equipos del grupo que
    no aparecen ese día (excepto el visitante que sí jugó).
    """
    en_grupo = _equipos_en_grupo(df, row)
    activos = _equipos_activos_fecha(df, row)
    visitante = str(row["visitante"])
    candidatos = en_grupo - activos - {visitante}
    if len(candidatos) == 1:
        return next(iter(candidatos))
    if len(candidatos) == 0:
        return ""
    return f"Varios ({len(candidatos)}): " + ", ".join(sorted(candidatos)[:5])


def enriquecer_analisis_libre(df: pd.DataFrame) -> pd.DataFrame:
    lib = filtrar_partidos_libre(df)
    if lib.empty:
        return pd.DataFrame()

    filas = []
    for _, row in lib.iterrows():
        loc_es = es_libre(row["local"])
        vis_es = es_libre(row["visitante"])
        anio = int(row["anio"]) if pd.notna(row["anio"]) else 0
        filas.append(
            {
                "anio": anio,
                "fecha": row.get("fecha", ""),
                "categoria": row.get("categoria", ""),
                "fase": row.get("fase", ""),
                "ronda": row.get("ronda", ""),
                "zona": row.get("zona", ""),
                "grupo": row.get("grupo", ""),
                "jornada": row.get("jornada", ""),
                "local": row["local"],
                "ptsL": row.get("ptsL", ""),
                "visitante": row["visitante"],
                "ptsV": row.get("ptsV", ""),
                "libre_en": "local" if loc_es else "visitante",
                "equipo_conocido": row["visitante"] if loc_es else row["local"],
                "candidato_equipo_real": (
                    inferir_candidato_libre_local(df, row) if loc_es else ""
                ),
                "nota": (
                    "LIBRE local = cupo libre GES; revisar fixture del grupo en estadísticas"
                    if loc_es
                    else "LIBRE visitante = rival ausente / no presentación habitual"
                ),
                "url_torneo_ges": url_torneo_ges(anio),
            }
        )
    return pd.DataFrame(filas)


def resumen_por_rival(lib: pd.DataFrame) -> pd.DataFrame:
    if lib.empty:
        return pd.DataFrame()
    rows = []
    for lado in ("local", "visitante"):
        mask = lib["libre_en"] == lado
        col = "equipo_conocido"
        sub = lib[mask]
        if sub.empty:
            continue
        for eq, cnt in sub[col].value_counts().items():
            rows.append({"libre_en": lado, "equipo_conocido": eq, "partidos": int(cnt)})
    return pd.DataFrame(rows)
