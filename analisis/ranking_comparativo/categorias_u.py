# -*- coding: utf-8 -*-
"""Mapeo categoría FeBAMBA → banda institucional U para jornada de tira."""

from __future__ import annotations

import re
from typing import Optional, Set

# Bandas evaluadas en la tira institucional (excluye Mini/Premini del ranking base,
# pero U9/U11 siguen siendo obligatorias en la penalización de tira).
BANDAS_TIRA: tuple[str, ...] = ("U9", "U11", "U13", "U15", "U17", "U19")
PENALIZACION_U9_U11 = 0.20
PENALIZACION_U13_U19 = 0.15

_ALIAS_CATEGORIA: dict[str, str] = {
    "PREMINI": "U9",
    "PRE MINI": "U9",
    "MINI": "U11",
    "PREINFANTILES": "U13",
    "PREINFANTILES MASCULINO": "U13",
    "INFANTILES": "U15",
    "INFANTILES MASCULINO": "U15",
    "CADETES": "U17",
    "CADETES MASCULINO": "U17",
    "JUVENILES": "U19",
    "JUVENILES MASCULINO": "U19",
    "LIGA PROXIMO MASCULINO": "U21",
}


def banda_u_desde_categoria(categoria: str) -> Optional[str]:
    """Devuelve U9…U21 o None si no se reconoce la categoría."""
    if not isinstance(categoria, str) or not categoria.strip():
        return None
    cat = categoria.upper().strip()
    if cat in _ALIAS_CATEGORIA:
        return _ALIAS_CATEGORIA[cat]
    m = re.search(r"\bU\s*-?\s*(\d+)\b", cat, re.IGNORECASE)
    if m:
        return f"U{int(m.group(1))}"
    return None


def bandas_obligatorias_tira() -> Set[str]:
    return set(BANDAS_TIRA)


def penalizacion_por_banda_faltante(banda: str) -> float:
    if banda in ("U9", "U11"):
        return PENALIZACION_U9_U11
    if banda in ("U13", "U15", "U17", "U19"):
        return PENALIZACION_U13_U19
    return 0.0
