# -*- coding: utf-8 -*-
"""Extracción de club institucional desde nombre de equipo."""

from __future__ import annotations

import re

_SUFIJOS_COLOR = (
    " AMARILLO",
    " AZUL",
    " BLANCO",
    " NEGRO",
    " VERDE",
    " CELESTE",
    " ROJO",
)

_SUFIJOS_EQUIPO = re.compile(r"\s+[A-Z]$")


def club_desde_equipo(nombre: str) -> str:
    """
    Heurística: quita colores y letra de equipo (A/B/C) al final.
    Ej.: PEDRO ECHAGUE A → PEDRO ECHAGUE
    """
    if not isinstance(nombre, str):
        return ""
    n = nombre.upper().strip()
    for suf in _SUFIJOS_COLOR:
        if n.endswith(suf):
            n = n[: -len(suf)].strip()
    if _SUFIJOS_EQUIPO.search(n):
        n = _SUFIJOS_EQUIPO.sub("", n).strip()
    return n
