# -*- coding: utf-8 -*-
"""
Identificación de Tira (club + división A/B/C).

La Tira NO es el club institucional: PEDRO ECHAGUE A y PEDRO ECHAGUE B son
tiras distintas y no deben mezclarse puntos ni forfaits.
"""

from __future__ import annotations

import re

from mapeos.loader import cargar_mapeo_equipos, normalizar_equipo

_SUFIJOS_COLOR = (
    " AMARILLO",
    " AZUL",
    " BLANCO",
    " NEGRO",
    " VERDE",
    " CELESTE",
    " ROJO",
)


def tira_desde_equipo(nombre: str, mapeo: dict | None = None) -> str:
    """
    Nombre canónico de tira tras equipos_map.json.

    Conserva la letra de división (A/B/C); solo quita sufijos de color
    redundantes si el mapeo no los unificó ya.
    """
    mapeo = mapeo or cargar_mapeo_equipos()
    n = normalizar_equipo(nombre, mapeo).upper().strip()
    for suf in _SUFIJOS_COLOR:
        if n.endswith(suf):
            n = n[: -len(suf)].strip()
    return n


def institucion_desde_tira(tira: str) -> str:
    """Club padre sin letra final (solo para reportes, no para acumular puntos)."""
    if not tira:
        return ""
    if re.search(r"\s+[A-Z]$", tira):
        return re.sub(r"\s+[A-Z]$", "", tira).strip()
    return tira
