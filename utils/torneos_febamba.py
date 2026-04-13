# -*- coding: utf-8 -*-
"""Filtro de torneos FeBAMBA Formativas e inferencia de año desde el nombre."""

from __future__ import annotations

import re
from typing import Any

FEDERACIONES_FEBAMBA: frozenset[str] = frozenset(
    {"FEDERACION DE BASQUETBOL DEL AREA METROPOLITANA DE BUENOS AIRES"}
)
KEYWORDS_FORMATIVAS: tuple[str, ...] = ("formativas", "formativa")


def inferir_anio(nombre_torneo: str) -> int | None:
    """Extrae el año (20xx) del título del torneo. gesdeportiva.json no trae Anio fiable."""
    match = re.search(r"(20\d{2})", nombre_torneo or "")
    return int(match.group(1)) if match else None


def es_torneo_formativas_febamba(entry: dict[str, Any]) -> bool:
    """True si la competencia es FeBAMBA y el nombre sugiere torneo formativas."""
    es_febamba = entry.get("federacion", "") in FEDERACIONES_FEBAMBA
    torneo = (entry.get("torneo") or "").lower()
    es_formativas = any(k in torneo for k in KEYWORDS_FORMATIVAS)
    return es_febamba and es_formativas
