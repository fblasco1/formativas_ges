# -*- coding: utf-8 -*-
"""Contexto de hilo para parámetros que no caben en la firma del Extractor ABC."""

from __future__ import annotations

import threading
from typing import Optional

_tls = threading.local()


def set_comp_cat_argentina_id(value: Optional[int]) -> None:
    """``compCatId`` del handler CargarFixture (suele coincidir con id_categoria GES)."""
    _tls.comp_cat_argentina_id = value


def get_comp_cat_argentina_id(fallback: int) -> int:
    return int(getattr(_tls, "comp_cat_argentina_id", None) or fallback)
