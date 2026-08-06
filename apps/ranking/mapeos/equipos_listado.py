# -*- coding: utf-8 -*-
"""Listado y filtros de equipos por temporada (módulo liviano, sin cruce)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set

import pandas as pd

from mapeos.equipos_casos import club_base
from mapeos.loader import cargar_mapeo_equipos, normalizar_equipo

FOCUS_YEARS: tuple[int, ...] = (2023, 2024, 2025, 2026)


@dataclass
class NombreEnTemporada:
    anio: int
    nombre_raw: str
    nombre_norm: str
    partidos: int = 0
    en_mapeo: bool = False


def inventario_temporada(
    df: pd.DataFrame,
    mapeo: Optional[Dict[str, str]] = None,
) -> Dict[tuple[int, str], NombreEnTemporada]:
    mapeo = mapeo if mapeo is not None else cargar_mapeo_equipos()
    inv: Dict[tuple[int, str], NombreEnTemporada] = {}

    def _add(nombre: str, anio: int) -> None:
        if not isinstance(nombre, str) or not nombre.strip() or anio is None:
            return
        raw = nombre.strip()
        key = (anio, raw)
        norm = normalizar_equipo(raw, mapeo)
        if key not in inv:
            inv[key] = NombreEnTemporada(
                anio=anio,
                nombre_raw=raw,
                nombre_norm=norm,
                en_mapeo=raw.upper().strip() in mapeo,
            )
        inv[key].partidos += 1

    for _, row in df.iterrows():
        try:
            anio = int(row["anio"])
        except (TypeError, ValueError):
            continue
        _add(row.get("local"), anio)
        _add(row.get("visitante"), anio)

    return inv


def listado_por_temporada(
    df: pd.DataFrame,
    mapeo: Optional[Dict[str, str]] = None,
    years: Sequence[int] = FOCUS_YEARS,
) -> pd.DataFrame:
    mapeo = mapeo if mapeo is not None else cargar_mapeo_equipos()
    inv = inventario_temporada(df, mapeo)

    raw_a_anios: Dict[str, Set[int]] = {}
    norm_a_anios: Dict[str, Set[int]] = {}
    base_a_raws: Dict[str, Set[str]] = {}
    base_csv_a_raws: Dict[str, Set[str]] = {}

    for (anio, raw), item in inv.items():
        if anio not in years:
            continue
        raw_a_anios.setdefault(raw, set()).add(anio)
        norm_a_anios.setdefault(item.nombre_norm, set()).add(anio)
        base_a_raws.setdefault(club_base(item.nombre_norm), set()).add(raw)
        base_csv_a_raws.setdefault(club_base(item.nombre_raw), set()).add(raw)

    filas: List[dict] = []
    for (anio, raw), item in sorted(inv.items(), key=lambda x: (x[0][0], x[0][1].upper())):
        if anio not in years:
            continue
        base = club_base(item.nombre_norm)
        base_raw = club_base(item.nombre_raw)
        filas.append(
            {
                "temporada": anio,
                "nombre_csv": item.nombre_raw,
                "nombre_normalizado": item.nombre_norm,
                "club_base": base,
                "club_base_desde_csv": base_raw,
                "partidos": item.partidos,
                "en_mapa": item.en_mapeo,
                "destino_mapeo": mapeo.get(raw.upper().strip(), ""),
                "temporadas_con_mismo_csv": len(raw_a_anios.get(raw, set())),
                "temporadas_con_mismo_norm": len(norm_a_anios.get(item.nombre_norm, set())),
                "variantes_csv_mismo_club": len(base_a_raws.get(base, set())),
                "variantes_csv_mismo_club_csv": len(base_csv_a_raws.get(base_raw, set())),
                "solo_esta_temporada": len(raw_a_anios.get(raw, set())) == 1,
            }
        )

    out = pd.DataFrame(filas)
    if out.empty:
        return out
    out["_sort"] = out["nombre_csv"].str.upper()
    return (
        out.sort_values(["_sort", "temporada"], ascending=[True, True])
        .drop(columns="_sort")
        .reset_index(drop=True)
    )


def filtrar_listado(
    tabla: pd.DataFrame,
    *,
    temporada: Optional[int] = None,
    buscar: str = "",
    filtro_tipo: str = "todos",
) -> pd.DataFrame:
    out = tabla.copy()
    if temporada is not None:
        out = out[out["temporada"] == temporada]
    if buscar.strip():
        q = buscar.strip().upper()
        mask = (
            out["nombre_csv"].str.upper().str.contains(q, na=False)
            | out["nombre_normalizado"].str.upper().str.contains(q, na=False)
            | out["club_base"].str.upper().str.contains(q, na=False)
        )
        if "club_base_desde_csv" in out.columns:
            mask = mask | out["club_base_desde_csv"].str.upper().str.contains(q, na=False)
        out = out[mask]

    if filtro_tipo == "mismo_nombre_csv":
        out = out[out["temporadas_con_mismo_csv"] >= 2]
    elif filtro_tipo == "mismo_nombre_norm":
        out = out[out["temporadas_con_mismo_norm"] >= 2]
    elif filtro_tipo == "mismo_club_varios_nombres":
        out = out[out["variantes_csv_mismo_club"] >= 2]
    elif filtro_tipo == "solo_una_temporada":
        out = out[out["solo_esta_temporada"]]
    elif filtro_tipo == "sin_mapear":
        out = out[~out["en_mapa"]]
    elif filtro_tipo == "nombres_iguales_exactos":
        counts = out.groupby("nombre_csv")["temporada"].transform("count")
        out = out[counts >= 2]
    elif filtro_tipo == "un_nombre_por_temporada_distinto":
        bases = out.groupby("club_base").filter(
            lambda g: g["variantes_csv_mismo_club"].iloc[0] >= 2
            and g["solo_esta_temporada"].all()
        )["club_base"].unique()
        out = out[out["club_base"].isin(bases)]
    elif filtro_tipo == "un_nombre_por_temporada_club_csv":
        if "club_base_desde_csv" in out.columns:
            bases = out.groupby("club_base_desde_csv").filter(
                lambda g: g["variantes_csv_mismo_club_csv"].iloc[0] >= 2
                and g["solo_esta_temporada"].all()
            )["club_base_desde_csv"].unique()
            out = out[out["club_base_desde_csv"].isin(bases)]
    elif filtro_tipo == "club_nombre_distinto_por_temporada":
        if "club_base_desde_csv" in out.columns:

            def _cambia_entre_temporadas(g: pd.DataFrame) -> bool:
                if g["temporada"].nunique() < 2:
                    return False
                por_anio = g.groupby("temporada")["nombre_csv"].apply(
                    lambda s: "|".join(sorted(s.unique()))
                )
                return por_anio.nunique() >= 2

            bases = out.groupby("club_base_desde_csv").filter(_cambia_entre_temporadas)[
                "club_base_desde_csv"
            ].unique()
            out = out[out["club_base_desde_csv"].isin(bases)]

    return out.reset_index(drop=True)


__all__ = ["FOCUS_YEARS", "NombreEnTemporada", "filtrar_listado", "inventario_temporada", "listado_por_temporada"]
