# -*- coding: utf-8 -*-
"""
Regla de plantilla MINI: >= 12 jugadores con al menos 10:00 min de juego.

Clasificación (Equipo A = local, Equipo B = visitante):

A:NP / B:NP — el equipo no cumple (menos de 12 jugadores con >=10:00 min).

ESPECIAL (regla de cambios / boxscore contradice fixture):
  20-0  + B gana boxscore
  0-20  + A gana boxscore
  0-0   + hay ganador en boxscore (ej. A gana box y B no cumple -> ESPECIAL + B:NP)
"""

from __future__ import annotations

from typing import Dict, List, Optional

MIN_JUGADORES_REGLA = 12
MIN_SEGUNDOS_REGLA = 10 * 60  # 10:00


def parse_minutos_a_segundos(value: object) -> Optional[int]:
    s = ("" if value is None else str(value)).strip()
    if not s:
        return None
    parts = s.split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 2:
        mm, ss = nums
        return mm * 60 + ss
    if len(nums) == 3:
        hh, mm, ss = nums
        return hh * 3600 + mm * 60 + ss
    return None


def jugador_cumple_regla(value: object) -> bool:
    sec = parse_minutos_a_segundos(value)
    return sec is not None and sec >= MIN_SEGUNDOS_REGLA


def cuenta_jugadores_regla(jugadores: List[Dict[str, object]]) -> int:
    return sum(1 for j in jugadores if jugador_cumple_regla(j.get("min")))


def cumple_regla_equipo(jugadores: List[Dict[str, object]]) -> bool:
    return cuenta_jugadores_regla(jugadores) >= MIN_JUGADORES_REGLA


def ganador_boxscore(pl: Optional[int], pv: Optional[int]) -> Optional[str]:
    if pl is None or pv is None:
        return None
    if pl > pv:
        return "local"
    if pv > pl:
        return "visitante"
    return None


def dif_boxscore_abs(pl_box: Optional[int], pv_box: Optional[int]) -> Optional[int]:
    if pl_box is None or pv_box is None:
        return None
    return abs(pl_box - pv_box)


def clasificar_np(*, ok_local: bool, ok_visit: bool) -> tuple[bool, bool]:
    """NP si el equipo no alcanza 12 jugadores con >=10:00 min."""
    return not ok_local, not ok_visit


def clasificar_especial(
    *,
    pl_fix: Optional[int],
    pv_fix: Optional[int],
    ganador: Optional[str],
) -> bool:
    if pl_fix == 20 and pv_fix == 0:
        return ganador == "visitante"
    if pl_fix == 0 and pv_fix == 20:
        return ganador == "local"
    if pl_fix == 0 and pv_fix == 0:
        return ganador in ("local", "visitante")
    return False


def format_flags(np_local: bool, np_visit: bool, especial: bool) -> str:
    parts: List[str] = []
    if np_local:
        parts.append("A:NP")
    if np_visit:
        parts.append("B:NP")
    if especial:
        parts.append("Regla de cambios Q3 u otros")
    return " | ".join(parts)


def analizar_partido(
    *,
    pl_fix: Optional[int],
    pv_fix: Optional[int],
    pl_box: Optional[int],
    pv_box: Optional[int],
    jug_local: List[Dict[str, object]],
    jug_visit: List[Dict[str, object]],
) -> Dict[str, object]:
    j_reg_local = cuenta_jugadores_regla(jug_local)
    j_reg_visit = cuenta_jugadores_regla(jug_visit)
    ok_local = j_reg_local >= MIN_JUGADORES_REGLA
    ok_visit = j_reg_visit >= MIN_JUGADORES_REGLA
    ganador = ganador_boxscore(pl_box, pv_box)

    np_local, np_visit = clasificar_np(ok_local=ok_local, ok_visit=ok_visit)
    especial = clasificar_especial(
        pl_fix=pl_fix,
        pv_fix=pv_fix,
        ganador=ganador,
    )
    dif_box = dif_boxscore_abs(pl_box, pv_box)

    return {
        "JUG_REG_LOCAL": j_reg_local,
        "JUG_REG_VISITANTE": j_reg_visit,
        "CUMPLE_LOCAL": ok_local,
        "CUMPLE_VISITANTE": ok_visit,
        "NO_CUMPLE_LOCAL": not ok_local,
        "NO_CUMPLE_VISITANTE": not ok_visit,
        "GANADOR_BOX": ganador or "",
        "NP_LOCAL": np_local,
        "NP_VISITANTE": np_visit,
        "ESPECIAL": especial,
        "FLAGS": format_flags(np_local, np_visit, especial),
        "DIF_BOX": dif_box,
    }


def observaciones_regla(j_reg_local: int, j_reg_visit: int) -> str:
    obs: List[str] = []
    if j_reg_local < MIN_JUGADORES_REGLA:
        obs.append(f"A (local): {j_reg_local}/{MIN_JUGADORES_REGLA} con >=10:00")
    if j_reg_visit < MIN_JUGADORES_REGLA:
        obs.append(f"B (visit.): {j_reg_visit}/{MIN_JUGADORES_REGLA} con >=10:00")
    return "; ".join(obs)
