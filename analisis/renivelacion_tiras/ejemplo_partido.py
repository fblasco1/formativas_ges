# -*- coding: utf-8 -*-
"""Ejemplo didáctico: desglose de puntos de renivelación en un partido."""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from analisis.Ranking.seasons import peso_anio_configurado
from analisis.renivelacion_tiras.ingesta import cargar_partidos_anios
from analisis.renivelacion_tiras.pesos import peso_etapa_renivelacion, peso_nivel_renivelacion
from analisis.renivelacion_tiras.pipeline import _procesar_anios_secuencial


def ejemplo_partido_reniv(
  years_prev: tuple[int, ...] = (2025, 2026),
) -> Optional[dict[str, Any]]:
    """
    Devuelve un partido competitivo 2026 con BP, ORP y pesos calculados.
    """
    years = tuple(sorted(set(years_prev)))
    if 2026 not in years:
        years = tuple(sorted(set(years) | {2026}))

    raw = cargar_partidos_anios(years)
    if raw.empty:
        return None

    proc, _ = _procesar_anios_secuencial(raw, years)
    sub = proc[(proc["anio"] == 2026) & (proc["es_competitivo"])].copy()
    pl = pd.to_numeric(sub["ptsL"], errors="coerce")
    pv = pd.to_numeric(sub["ptsV"], errors="coerce")
    sub = sub[(pl > 0) & (pv > 0) & (pl != 20) & (pv != 20)]
    if sub.empty:
        return None

    row = sub.iloc[0]
    anio = int(row["anio"])
    pa = float(peso_anio_configurado(anio))
    pe = float(peso_etapa_renivelacion(row["fase"], row["ronda"], anio))
    pn = float(peso_nivel_renivelacion(row["nivel"], row["ronda"], anio))
    factor = pa * pe * pn

    bp_l = int(row["BP_LOCAL"])
    bp_v = int(row["BP_VISITA"])
    orp_l = float(row["ORP_LOCAL"])
    orp_v = float(row["ORP_VISITA"])
    pts_l = round(float(row["Pts_Reniv_Local"]), 1)
    pts_v = round(float(row["Pts_Reniv_Visita"]), 1)

    return {
        "fecha": row.get("fecha", ""),
        "categoria": row.get("categoria", ""),
        "bucket": row.get("bucket_renivelacion", ""),
        "fase": row.get("fase", ""),
        "ronda": row.get("ronda", ""),
        "nivel": row.get("nivel", ""),
        "zona": row.get("zona", ""),
        "local": row["club_tira_local"],
        "visitante": row["club_tira_visitante"],
        "ptsL": int(row["ptsL"]),
        "ptsV": int(row["ptsV"]),
        "bp_local": bp_l,
        "bp_visitante": bp_v,
        "orp_local": orp_l,
        "orp_visitante": orp_v,
        "peso_anio": pa,
        "peso_etapa": pe,
        "peso_nivel": pn,
        "factor": factor,
        "pts_reniv_local": pts_l,
        "pts_reniv_visitante": pts_v,
    }
