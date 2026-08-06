# -*- coding: utf-8 -*-
"""Reglas de zona/región para reportes (p. ej. CENTRO-OESTE 2024–2025)."""

from __future__ import annotations

from typing import Union

from mapeos.loader import clave_mapeo

# Temporadas con zona compuesta CENTRO-OESTE en GES
CENTRO_OESTE_ANIOS: tuple[int, ...] = (2024, 2025)

EQUIPOS_CENTRO_OESTE_OESTE: frozenset[str] = frozenset({"CLARIDAD"})


def es_centro_oeste(anio: Union[int, float], zona: str) -> bool:
    try:
        y = int(anio)
    except (TypeError, ValueError):
        return False
    return y in CENTRO_OESTE_ANIOS and str(zona).upper().strip() == "CENTRO-OESTE"


def zona_regional_equipo(anio: Union[int, float], zona_partido: str, equipo: str) -> str:
    """
    Zona para conteos por equipo.

    CENTRO-OESTE (2024–2025): CLARIDAD → OESTE; el resto → CENTRO.
    """
    if not es_centro_oeste(anio, zona_partido):
        return str(zona_partido).upper().strip()
    eq = clave_mapeo(equipo)
    if eq in EQUIPOS_CENTRO_OESTE_OESTE:
        return "OESTE"
    return "CENTRO"
