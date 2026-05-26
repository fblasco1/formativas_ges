# -*- coding: utf-8 -*-
"""Consulta de partidos por equipo y clasificación de marcadores especiales GES."""

from __future__ import annotations

from typing import List, Optional, Tuple

import pandas as pd

from mapeos.loader import cargar_mapeo_equipos, normalizar_equipo

TIPOS_MARCADOR = (
    "Partido normal",
    "0-0",
    "20-0 a favor",
    "0-20 en contra",
)

FILTROS_ESPECIALES = ("Todos", "Solo especiales (0-0 / 20-0 / 0-20)", "Solo partidos normales") + TIPOS_MARCADOR


def _pts_enteros(val) -> int:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return -1


def clasificar_marcador_equipo(pts_propio: int, pts_rival: int) -> Tuple[str, bool, str]:
    """
    Devuelve (tipo, equipo_no_presenta, nota).

    En GES: 20-0 / 0-20 / 0-0 suelen indicar no presentación o partido sin juego real.
    """
    if pts_propio == 0 and pts_rival == 0:
        return "0-0", True, "Ambos en 0: revisar si hubo doble no presentación."
    if pts_propio == 20 and pts_rival == 0:
        return "20-0 a favor", False, "Rival en 0: tu equipo figura como presente (ganás por forfait)."
    if pts_propio == 0 and pts_rival == 20:
        return "0-20 en contra", True, "Tu equipo en 0: no presentación / no completó."
    return "Partido normal", False, "Marcador de partido jugado (regla FeBAMBA por diferencia)."


def partidos_de_equipo(
    df: pd.DataFrame,
    equipo: str,
    *,
    anio: Optional[int] = None,
    mapeo: Optional[dict] = None,
) -> pd.DataFrame:
    """Partidos donde participa el equipo (vista del jugador)."""
    mapeo = mapeo or cargar_mapeo_equipos()
    eq = normalizar_equipo(equipo, mapeo).upper()

    data = df.copy()
    data["anio"] = pd.to_numeric(data["anio"], errors="coerce")
    if anio is not None:
        data = data[data["anio"] == anio]
    data["local_n"] = data["local"].apply(lambda x: normalizar_equipo(x, mapeo).upper())
    data["visitante_n"] = data["visitante"].apply(lambda x: normalizar_equipo(x, mapeo).upper())

    mask = (data["local_n"] == eq) | (data["visitante_n"] == eq)
    sub = data[mask].copy()
    if sub.empty:
        return pd.DataFrame()

    filas: List[dict] = []
    for _, row in sub.iterrows():
        es_local = row["local_n"] == eq
        pts_propio = _pts_enteros(row["ptsL"] if es_local else row["ptsV"])
        pts_rival = _pts_enteros(row["ptsV"] if es_local else row["ptsL"])
        tipo, np, nota = clasificar_marcador_equipo(pts_propio, pts_rival)
        filas.append(
            {
                "fecha": row.get("fecha", ""),
                "temporada": int(row["anio"]) if pd.notna(row["anio"]) else "",
                "categoria": row.get("categoria", ""),
                "fase": row.get("fase", ""),
                "ronda": row.get("ronda", ""),
                "zona": row.get("zona", ""),
                "condicion": "Local" if es_local else "Visitante",
                "rival": row["visitante_n"] if es_local else row["local_n"],
                "pts_propio": pts_propio,
                "pts_rival": pts_rival,
                "marcador": f"{pts_propio}-{pts_rival}",
                "tipo_marcador": tipo,
                "no_presenta": "Sí" if np else "No",
                "nota": nota,
            }
        )

    out = pd.DataFrame(filas)
    return out.sort_values(["fecha", "categoria"], na_position="last").reset_index(drop=True)


def filtrar_por_tipo(partidos: pd.DataFrame, filtro: str) -> pd.DataFrame:
    if partidos.empty or filtro == "Todos":
        return partidos
    if filtro == "Solo especiales (0-0 / 20-0 / 0-20)":
        return partidos[partidos["tipo_marcador"] != "Partido normal"]
    if filtro == "Solo partidos normales":
        return partidos[partidos["tipo_marcador"] == "Partido normal"]
    return partidos[partidos["tipo_marcador"] == filtro]


def resumen_tipos(partidos: pd.DataFrame) -> pd.DataFrame:
    if partidos.empty:
        return pd.DataFrame(columns=["tipo_marcador", "cantidad"])
    return (
        partidos.groupby("tipo_marcador", as_index=False)
        .size()
        .rename(columns={"size": "cantidad"})
        .sort_values("cantidad", ascending=False)
    )
