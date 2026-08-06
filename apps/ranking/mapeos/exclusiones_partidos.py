# -*- coding: utf-8 -*-
"""Reglas para excluir partidos del dataset (consolidado y rankings)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, List, Sequence, Tuple

import pandas as pd

from mapeos.loader import cargar_mapeo_equipos, normalizar_equipo

_EXCLUSIONES_PATH = Path(__file__).resolve().parent / "exclusiones_partidos.json"


def cargar_exclusiones() -> list[dict[str, Any]]:
    if not _EXCLUSIONES_PATH.is_file():
        return []
    with open(_EXCLUSIONES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def _pts(val) -> int:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return -1


def _nombre_equipo(nombre: str, mapeo: dict) -> str:
    return normalizar_equipo(nombre, mapeo).upper()


def _equipo_en_club(nombre: str, club: str, mapeo: dict) -> bool:
    return club.upper() in _nombre_equipo(nombre, mapeo)


def _marcador_especial(
    pts_l: int, pts_v: int, pares: Sequence[Sequence[int]]
) -> bool:
    return any(pts_l == a and pts_v == b for a, b in pares)


def _marcador_desde_equipo(
    row: pd.Series,
    equipo: str,
    marcador: Sequence[int],
    mapeo: dict,
) -> bool:
    """True si el equipo indicado tiene pts_propio-pts_rival = marcador."""
    objetivo = _nombre_equipo(equipo, mapeo)
    loc = _nombre_equipo(str(row.get("local", "")), mapeo)
    vis = _nombre_equipo(str(row.get("visitante", "")), mapeo)
    a, b = int(marcador[0]), int(marcador[1])
    if loc == objetivo:
        return _pts(row.get("ptsL")) == a and _pts(row.get("ptsV")) == b
    if vis == objetivo:
        return _pts(row.get("ptsV")) == a and _pts(row.get("ptsL")) == b
    return False


def fila_coincide_exclusion(
    row: pd.Series,
    regla: dict[str, Any],
    *,
    mapeo: dict | None = None,
) -> bool:
    mapeo = mapeo or cargar_mapeo_equipos()

    anio_regla = regla.get("anio")
    if anio_regla is not None:
        try:
            if int(float(row.get("anio", -1))) != int(anio_regla):
                return False
        except (TypeError, ValueError):
            return False

    ronda_pat = regla.get("ronda_contiene") or regla.get("ronda")
    if ronda_pat:
        ronda = str(row.get("ronda", ""))
        if ronda_pat not in ronda and not re.search(
            str(ronda_pat), ronda, flags=re.IGNORECASE
        ):
            return False

    equipo = regla.get("equipo", "")
    club = regla.get("club", "")
    if equipo:
        objetivo = _nombre_equipo(equipo, mapeo)
        loc = _nombre_equipo(str(row.get("local", "")), mapeo)
        vis = _nombre_equipo(str(row.get("visitante", "")), mapeo)
        if objetivo not in (loc, vis):
            return False
    elif club:
        if not (
            _equipo_en_club(str(row.get("local", "")), club, mapeo)
            or _equipo_en_club(str(row.get("visitante", "")), club, mapeo)
        ):
            return False

    marcador_equipo = regla.get("marcador_equipo")
    if marcador_equipo and equipo:
        if not _marcador_desde_equipo(row, equipo, marcador_equipo, mapeo):
            return False
    elif marcador_equipo:
        return False

    pares = regla.get("marcadores_especiales")
    if pares:
        pl, pv = _pts(row.get("ptsL")), _pts(row.get("ptsV"))
        if not _marcador_especial(pl, pv, pares):
            return False

    return True


def indices_a_excluir(
    df: pd.DataFrame,
    reglas: Iterable[dict[str, Any]] | None = None,
) -> List[int]:
    reglas = list(reglas or cargar_exclusiones())
    if not reglas:
        return []
    out: List[int] = []
    for idx, row in df.iterrows():
        if any(fila_coincide_exclusion(row, r) for r in reglas):
            out.append(int(idx))
    return out


def aplicar_exclusiones(
    df: pd.DataFrame,
    reglas: Iterable[dict[str, Any]] | None = None,
    *,
    inplace: bool = False,
) -> tuple[pd.DataFrame, int]:
    """Devuelve (dataframe sin filas excluidas, cantidad eliminada)."""
    idx = indices_a_excluir(df, reglas)
    if not idx:
        return (df if inplace else df.copy(), 0)
    if inplace:
        df.drop(index=idx, inplace=True)
        return df, len(idx)
    return df.drop(index=idx).reset_index(drop=True), len(idx)
