"""
Factor de etapa S = w_fase × w_ronda × w_nivel (texto del pipeline, búsqueda por subcadena).
"""

from __future__ import annotations

import re
from typing import Any

_DEFAULT_WEIGHT = 1.0


def _norm(s: Any) -> str:
    t = str(s).strip().upper()
    t = re.sub(r"\s+", " ", t)
    return t


def _lookup_phase(fase: str, nivel: Any = None) -> float:
    u = _norm(fase)
    nu = _norm(nivel) if nivel is not None else ""
    if "FINAL FOUR" in u:
        return 1.0
    if "PLAYOFF" in u:
        if nu in ("INTERCONFERENCIA", "INTERCONFERENCIA A", "INTERCONFERENCIA B") or "INTERCONFERENCIA" in nu:
            return 1.0
        return 0.75
    if "FASE REGULAR" in u:
        return 0.65
    return _DEFAULT_WEIGHT


def _lookup_round(ronda: str, anio: int | None) -> float:
    u = _norm(ronda)
    if u in ("1RA FASE", "1ª FASE"):
        return 1.0
    if u in ("2DA FASE", "2ª FASE"):
        if anio in (2019, 2022, 2023):
            return 2.0
        return 1.0
    if u in ("3RA FASE", "3ª FASE"):
        if anio in (2019, 2022, 2023):
            return 1.0
        return 2.0
    if "OCTAVO" in u:
        return 3.0
    if "CUARTO" in u:
        return 4.0
    if "SEMIFINAL" in u:
        return 6.0
    if u == "FINAL" or "FINAL " in u:
        return 6.0
    return _DEFAULT_WEIGHT


def _lookup_level(nivel: str) -> float:
    u = _norm(nivel)
    if u in ("INTERCONFERENCIA A", "INTERCONFERENCIA"):
        return 2.0
    if "INTERCONFERENCIA B" in u:
        return 1.5
    if u == "1" or u.startswith("NIVEL 1"):
        return 1.0
    if u == "2" or u.startswith("NIVEL 2"):
        return 0.85
    if u == "3" or u.startswith("NIVEL 3"):
        return 0.75
    return _DEFAULT_WEIGHT


def stage_multiplier(
    fase: Any,
    ronda: Any,
    nivel: Any,
    anio: int | None = None,
) -> float:
    """
    S = w_fase(fase) × w_ronda(ronda, anio) × w_nivel(nivel).
    `anio` afecta solo pesos de ronda donde el calendario FeBAMBA cambió entre temporadas.
    """
    wf = _lookup_phase(fase, nivel)
    wr = _lookup_round(ronda, anio)
    wn = _lookup_level(nivel)
    return float(wf * wr * wn)
