# -*- coding: utf-8 -*-
"""Identificadores de partido GES cuando el widget no expone token en el href."""

from __future__ import annotations

import hashlib
import re
from typing import Final

_PREFIX: Final[str] = "gesn_"


def _norm_text(s: str) -> str:
    t = (s or "").replace("\n", " ").strip()
    t = re.sub(r"\s+", " ", t)
    return t.upper()


def synthetic_partido_id(
    comp_id: int,
    categoria_id: int,
    fecha: str,
    local: str,
    visitante: str,
) -> str:
    """
    Clave estable sin ID GES: competencia + categoría + fecha (texto) + equipos.
    Prefijo ``gesn_`` para distinguirla de tokens reales del href.
    """
    raw = "|".join(
        (
            str(int(comp_id)),
            str(int(categoria_id)),
            _norm_text(fecha),
            _norm_text(local),
            _norm_text(visitante),
        )
    )
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:28]
    return f"{_PREFIX}{h}"


def es_id_sintetico(partido_id: str) -> bool:
    return bool(partido_id) and str(partido_id).startswith(_PREFIX)
