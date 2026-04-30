# -*- coding: utf-8 -*-
"""Reglas por temporada: portal argentina.basketball vs legado GES widget."""

from __future__ import annotations

import re
from typing import Optional


def year_from_temporada(temporada: str) -> int:
    t = (temporada or "").strip()
    m = re.search(r"(\d{4})", t)
    if m:
        return int(m.group(1))
    return 2024


def ingesta_usa_portal_argentina(temporada: Optional[str]) -> bool:
    """Temporada >= 2026: fixture y boxscore vía argentina.basketball (sin widgetscab)."""
    if not temporada:
        return False
    return year_from_temporada(temporada) >= 2026


def historico_antes_portal_argentina(temporada: Optional[str]) -> bool:
    """2024–2025 y anteriores: flujo histórico con widget GES para calendario y acta."""
    if not temporada:
        return True
    return year_from_temporada(temporada) < 2026
